"""Strict streaming parser for the delivered EPTS text and its XML column schema.

Errors name the record/field, never echo a private record. Explicit NaNs are
observations missing at source; malformed fields, infinity and missing rows fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

PARSER_VERSION = "mya-atd-1.0"


class DataValidationError(ValueError):
    """An input does not satisfy its source contract."""


def local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def child_text(element, name):
    return next((c.text or "" for c in element if local_name(c) == name), "").strip()


def read_xml(path):
    try:
        return ET.parse(path).getroot()
    except ET.ParseError:
        raise DataValidationError("Malformed XML (contents withheld)") from None


@dataclass(frozen=True)
class ATDMetadata:
    team_mapping: dict[int, str]
    num_slots: int
    num_frames: int
    fps: float
    speed_unit: str


def parse_metadata(path: Path, num_frames: int, num_slots: int, fps: float) -> ATDMetadata:
    root = read_xml(path)
    elements = list(root.iter())
    teams = [e for e in elements if local_name(e) == "Team"]
    names = {"barcelona": "H", "fc barcelona": "H", "atletic club": "A", "athletic club": "A"}
    team_ids = {}
    for team in teams:
        team_id = team.get("id")
        label = names.get(child_text(team, "Name").casefold())
        if not team_id or team_id in team_ids or label is None:
            raise DataValidationError("Ambiguous XML team identity/name")
        team_ids[team_id] = label
    if len(team_ids) != 2 or set(team_ids.values()) != {"H", "A"}:
        raise DataValidationError("XML must identify the two match teams")
    players = {}
    for element in elements:
        if local_name(element) == "Player":
            player_id, team_id = element.get("id"), element.get("teamId")
            if not player_id or player_id in players or team_id not in team_ids:
                raise DataValidationError("Invalid XML player/team reference")
            players[player_id] = team_ids[team_id]
    if len(players) != num_slots:
        raise DataValidationError("XML player count differs from source slot count")
    channels = {}
    for element in elements:
        if local_name(element) == "PlayerChannel":
            key = element.get("id")
            if not key or key in channels or element.get("playerId") not in players:
                raise DataValidationError("Invalid XML player channel")
            channels[key] = (element.get("playerId"), element.get("channelId"))
    formats = [e for e in elements if local_name(e) == "DataFormatSpecification"]
    if len(formats) != 1:
        raise DataValidationError("Expected one constant XML data format")
    fmt = formats[0]
    try:
        bounds = int(fmt.get("startFrame", "")), int(fmt.get("endFrame", ""))
        rates = [float(e.text) for e in elements if local_name(e) == "FrameRate"]
    except (ValueError, TypeError):
        raise DataValidationError("Invalid XML frame metadata") from None
    if bounds != (1, num_frames) or rates != [fps] or fmt.get("separator") != ":":
        raise DataValidationError("XML frame range/rate/separator differs from source")
    registers = list(fmt)
    if (len(registers) != 3 or local_name(registers[0]) != "StringRegister"
            or registers[1].get("separator") != ";" or registers[2].get("separator") != ","):
        raise DataValidationError("Unsupported XML record layout")
    slot_registers = list(registers[1])
    if len(slot_registers) != num_slots:
        raise DataValidationError("XML columns differ from source slot count")
    mapping, ordered_players = {}, []
    channel_order = None
    for index, register in enumerate(slot_registers):
        refs = list(register)
        if (register.get("separator") != "," or len(refs) != 3
                or any(local_name(ref) != "PlayerChannelRef" for ref in refs)):
            raise DataValidationError("Unsupported XML player triple")
        resolved = [channels.get(ref.get("playerChannelId")) for ref in refs]
        if any(ref is None for ref in resolved) or len({ref[0] for ref in resolved}) != 1:
            raise DataValidationError("XML columns reference different/unknown players")
        ids = tuple(ref[1] for ref in resolved)
        if len(set(ids)) != 3 or (channel_order is not None and ids != channel_order):
            raise DataValidationError("Inconsistent XML x/y/speed column order")
        channel_order = ids
        ordered_players.append(resolved[0][0])
        mapping[index] = players[resolved[0][0]]
    if len(set(ordered_players)) != num_slots or set(ordered_players) != set(players):
        raise DataValidationError("XML player columns are duplicated/incomplete")
    # Resolve channel semantics, rather than trusting arbitrary channel identifiers.
    channel_definitions = {e.get("id"): (child_text(e, "Name").casefold().replace("_", " "), child_text(e, "Unit").casefold())
                           for e in elements if local_name(e) == "Channel"}
    semantics = [channel_definitions.get(key) for key in channel_order]
    if any(s is None for s in semantics):
        raise DataValidationError("XML channel definition is missing")
    unit_key = re.sub(r"[^a-z0-9]", "", semantics[2][1])
    speed_units = {key: "m/s" for key in ("ms", "ms1", "mps", "meterssecond", "metressecond")}
    speed_units.update({key: "km/h" for key in ("kph", "kmh", "kmh1")})
    if (semantics[0][0] not in ("x", "position x") or semantics[1][0] not in ("y", "position y")
            or "speed" not in semantics[2][0]
            or semantics[0][1] != "normalized" or semantics[1][1] != "normalized"
            or unit_key not in speed_units):
        raise DataValidationError("Unsupported XML coordinate/speed channel semantics")
    ball_refs = list(registers[2])
    if len(ball_refs) != 3 or any(local_name(ref) != "BallChannelRef" for ref in ball_refs):
        raise DataValidationError("Unsupported XML ball triple")
    if tuple(ref.get("channelId") for ref in ball_refs) != channel_order:
        raise DataValidationError("XML ball/player coordinate conventions differ")
    return ATDMetadata(mapping, num_slots, num_frames, fps, speed_units[unit_key])


def parse_atd(file_path: Path, num_frames: int, num_slots: int, *, max_frames=None):
    """Validate the WHOLE file, even for a preview; allocate only requested rows."""
    if num_frames < 1 or num_slots < 1:
        raise ValueError("Positive dimensions required")
    if max_frames is not None and (type(max_frames) is not int or not 1 <= max_frames <= num_frames):
        raise ValueError("max_frames must be an integer within the source range")
    count_to_store = num_frames if max_frames is None else max_frames
    players = np.empty((count_to_store, num_slots, 3), dtype=np.float32)
    ball = np.empty((count_to_store, 3), dtype=np.float32)
    count = 0
    with Path(file_path).open(encoding="utf-8-sig") as handle:
        for row, line in enumerate(handle):
            count += 1
            if row >= num_frames:
                raise DataValidationError("ATD has extra records")
            parts = line.strip().split(":")
            if len(parts) != 3:
                raise DataValidationError(f"ATD record {row + 1}: expected two colons")
            try:
                frame_id = int(parts[0])
            except ValueError:
                raise DataValidationError(f"ATD record {row + 1}: invalid frame id") from None
            if frame_id != row + 1:
                raise DataValidationError(f"ATD record {row + 1}: frame ids must be consecutive from 1")
            slots = parts[1].split(";")
            # EPTS allows one optional terminal separator, not empty observations.
            if slots[-1] == "":
                slots.pop()
            if len(slots) != num_slots:
                raise DataValidationError(f"ATD record {row + 1}: wrong player slot count")
            triples = slots + [parts[2].removesuffix(";")]
            values = []
            for field, triple in enumerate(triples):
                components = triple.split(",")
                if len(components) != 3 or any(not c.strip() for c in components):
                    raise DataValidationError(f"ATD record {row + 1}, field {field}: malformed triple")
                try:
                    values.extend(float(c) for c in components)
                except ValueError:
                    raise DataValidationError(f"ATD record {row + 1}, field {field}: invalid number") from None
            with np.errstate(over="ignore"):
                array = np.asarray(values, dtype=np.float32).reshape(num_slots + 1, 3)
            if np.isinf(array).any():
                raise DataValidationError(f"ATD record {row + 1}: infinity/float32 overflow")
            if row < count_to_store:
                players[row], ball[row] = array[:-1], array[-1]
    if count != num_frames:
        raise DataValidationError("ATD is truncated: record count differs from source")
    frame_ids = np.arange(1, count_to_store + 1, dtype=np.int32)
    return players, ball, frame_ids, frame_ids - 1
