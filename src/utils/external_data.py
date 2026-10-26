"""Pinned DFL ingestion with separate observation and target archives.

No Kloppy defaults are used to derive targets: missing status/owner stays X.
Only x/y, observation masks, anonymous slots and public geometry/timeline enter
the model-facing interface. Ball state, ownership, Z and identities never do.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np

from src import config
from src.preprocessing.atd_parser import DataValidationError
from src.refinement.exporter import sha256_file

PARSER_VERSION = "dfl-strict-v1"
SECTIONS = {"firstHalf": 1, "secondHalf": 2}
INPUT_KEYS = {"players_xy_normalized", "ball_xy_normalized", "players_observed", "ball_observed",
              "team_mapping", "frame_ids", "period_ids", "fps", "pitch_dims"}


def settings(name):
    return json.loads((config.MYA_DIR / "configs" / name).read_text(encoding="utf-8"))


def dataset_root():
    return config.CACHE_DIR / "external" / "dfl" / "28196177" / "v1"


def match_role(match_id, *, allow_final_test=False):
    protocol = settings("external_protocol.json")
    roles = [role for role, ids in protocol["splits"].items() if match_id in ids]
    if len(roles) != 1:
        raise ValueError("Unregistered or multiply assigned external match")
    if roles[0] == "test" and not allow_final_test:
        raise PermissionError("Final test match is locked; no development download, ingestion or scoring")
    return roles[0]


def md5_file(path):
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(asset, directory, *, progress=None):
    """Verify both cached and new files; never replace with an incomplete download."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = asset["name"]
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Asset must have a safe leaf filename")
    path = directory / name
    if path.is_file() and path.stat().st_size == asset["size"] and md5_file(path) == asset["computed_md5"]:
        return path
    if not asset["download_url"].startswith("https://ndownloader.figshare.com/files/"):
        raise ValueError("Only the pinned Figshare download host is allowed")
    fd, temporary = tempfile.mkstemp(prefix=name + ".", suffix=".part", dir=directory)
    try:
        count, digest, last = 0, hashlib.md5(), time.monotonic()
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(asset["download_url"], timeout=45) as response:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > asset["size"]:
                    raise DataValidationError("Download exceeds pinned size")
                output.write(chunk)
                digest.update(chunk)
                if progress and time.monotonic() - last > 5:
                    progress(f"Downloading {count // 1048576}/{asset['size'] // 1048576} MiB")
                    last = time.monotonic()
            output.flush()
            os.fsync(output.fileno())
        if count != asset["size"] or digest.hexdigest() != asset["computed_md5"]:
            raise DataValidationError("Download size/MD5 differs from pinned Figshare metadata")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def fetch_match(match_id, *, progress=None):
    from src.source_policy import require_use
    role = match_role(match_id)
    require_use(f"dfl_{match_id}", "training" if role == "train" else "external_validation")
    manifest = settings("dfl_manifest.json")
    assets = manifest["matches"][match_id]
    return {kind: download_asset(asset, dataset_root() / "raw", progress=progress) for kind, asset in assets.items()}


def metadata_from_xml(path, match_id):
    root = ET.parse(path).getroot()
    general, environment = root.find(".//General"), root.find(".//Environment")
    if general is None or general.get("MatchId") != f"DFL-MAT-{match_id}" or environment is None:
        raise DataValidationError("DFL metadata match identity is inconsistent")
    try:
        pitch = float(environment.get("PitchX")), float(environment.get("PitchY"))
    except (TypeError, ValueError):
        raise DataValidationError("Invalid DFL pitch dimensions") from None
    if not np.isfinite(pitch).all() or min(pitch) <= 0:
        raise DataValidationError("Invalid DFL pitch dimensions")
    players, teams, refs = {}, {}, {e.get("PersonId") for e in root.iter("Referee")}
    for team in root.findall(".//Teams/Team"):
        role, key = team.get("Role"), team.get("TeamId")
        label = {"home": "H", "guest": "A"}.get(role)
        if label is None or not key or key in teams:
            raise DataValidationError("Ambiguous DFL team roles")
        teams[key] = label
        for player in team.findall(".//Players/Player"):
            key = player.get("PersonId")
            if not key or key in players:
                raise DataValidationError("Duplicate/missing DFL player identity")
            players[key] = label
    if set(teams.values()) != {"H", "A"} or len(teams) != 2 or not players:
        raise DataValidationError("DFL must identify two teams and players")
    other = root.find(".//OtherGameInformation")
    durations = {}
    if other is not None:
        try:
            durations = {period: float(other.get(key))/1000 for period, key in
                         ((1, "TotalTimeFirstHalf"), (2, "TotalTimeSecondHalf"))}
        except (TypeError, ValueError):
            raise DataValidationError("Invalid DFL period duration metadata") from None
        if any(not np.isfinite(value) or value <= 0 for value in durations.values()):
            raise DataValidationError("Invalid DFL period duration metadata")
    return {"pitch_dims": pitch, "players": players, "teams": teams, "referees": refs, "durations": durations}


def target_label(status, owner):
    """Strict enum mapping: unknown never silently becomes away or dead."""
    if status == "0":
        return "D"
    if status == "1":
        return {"1": "H", "2": "A"}.get(owner, "X")
    return "X"


def iter_records(path):
    stack, current = [], None
    try:
        for event, elem in ET.iterparse(path, events=("start", "end")):
            if event == "start":
                stack.append(elem)
                if elem.tag == "FrameSet":
                    current = dict(elem.attrib)
            else:
                if elem.tag == "Frame" and current is not None:
                    yield current, dict(elem.attrib)
                if elem.tag == "FrameSet":
                    current = None
                if len(stack) > 1:
                    stack[-2].remove(elem)
                elem.clear()
                stack.pop()
    except ET.ParseError:
        raise DataValidationError("Malformed DFL XML") from None


def record_identity(frameset, row, metadata, match_id):
    if frameset.get("MatchId") != f"DFL-MAT-{match_id}":
        raise DataValidationError("DFL positions refer to another match")
    period = SECTIONS.get(frameset.get("GameSection"))
    if period is None:
        raise DataValidationError("Unexpected DFL game section")
    team_id, person = frameset.get("TeamId"), frameset.get("PersonId")
    if team_id == "referee" or person in metadata["referees"]:
        return None
    object_id = "ball" if team_id == "BALL" else person
    if object_id != "ball":
        if object_id not in metadata["players"] or metadata["teams"].get(team_id) != metadata["players"][object_id]:
            raise DataValidationError("Unknown DFL player/team reference")
    try:
        frame_id = int(row["N"])
    except (KeyError, ValueError):
        raise DataValidationError("Invalid DFL frame identifier") from None
    if frame_id < 0:
        raise DataValidationError("Negative DFL frame identifier")
    return period, object_id, frame_id


def parse_xy(row):
    result = []
    for key in ("X", "Y"):
        value = row.get(key)
        if value in (None, "", "NaN", "nan"):
            result.append(np.nan)
            continue
        try:
            number = float(value)
        except ValueError:
            raise DataValidationError("Invalid DFL coordinate") from None
        if not np.isfinite(number):
            raise DataValidationError("Infinite DFL coordinate")
        result.append(number)
    return result


@dataclass(frozen=True)
class ExternalInputs:
    """Only fields in the versioned allowlist may cross into prediction code."""
    players_xy_normalized: np.ndarray
    ball_xy_normalized: np.ndarray
    players_observed: np.ndarray
    ball_observed: np.ndarray
    team_mapping: np.ndarray
    frame_ids: np.ndarray
    period_ids: np.ndarray
    fps: float
    pitch_dims: tuple[float, float]

    def feature_dict(self):
        return {name: getattr(self, name) for name in sorted(INPUT_KEYS)}


@dataclass(frozen=True)
class ExternalTargets:
    labels: np.ndarray
    frame_ids: np.ndarray
    period_ids: np.ndarray


def parse_match(metadata_path, positions_path, match_id):
    metadata = metadata_from_xml(metadata_path, match_id)
    timeline = {1: set(), 2: set()}
    for frameset, row in iter_records(positions_path):
        identity = record_identity(frameset, row, metadata, match_id)
        if identity:
            period, _, frame_id = identity
            timeline[period].add(frame_id)
    if any(not frames for frames in timeline.values()):
        raise DataValidationError("Both complete DFL periods are required")
    for frames in timeline.values():
        if len(frames) != max(frames) - min(frames) + 1:
            raise DataValidationError("DFL timeline has missing complete frames")
    for period, duration in metadata["durations"].items():
        if abs((len(timeline[period])-1)/25 - duration) > 1/25:
            raise DataValidationError("DFL period length differs from match metadata")
    keys = [(period, frame) for period in (1, 2) for frame in sorted(timeline[period])]
    frame_index = {key: index for index, key in enumerate(keys)}
    player_ids = sorted(metadata["players"])
    slots = {key: i for i, key in enumerate(player_ids)}
    n, count = len(keys), len(slots)
    players = np.full((n, count, 2), np.nan, dtype=np.float32)
    ball = np.full((n, 2), np.nan, dtype=np.float32)
    player_seen, ball_seen = np.zeros((n, count), dtype=bool), np.zeros(n, dtype=bool)
    labels = np.full(n, "X", dtype="<U1")
    last_ids, last_times, quality = {}, {}, Counter()
    for frameset, row in iter_records(positions_path):
        identity = record_identity(frameset, row, metadata, match_id)
        if identity is None:
            continue
        period, object_id, frame_id = identity
        index, series = frame_index[(period, frame_id)], (period, object_id)
        if frame_id <= last_ids.get(series, -1):
            raise DataValidationError("DFL records are duplicated or unordered within a track")
        previous = last_ids.get(series)
        last_ids[series] = frame_id
        xy = parse_xy(row)
        if object_id == "ball":
            if ball_seen[index]:
                raise DataValidationError("Duplicate DFL ball frame")
            ball_seen[index], ball[index] = True, xy
            labels[index] = target_label(row.get("BallStatus"), row.get("BallPossession"))
            quality["unknown_status"] += row.get("BallStatus") not in ("0", "1")
            quality["unknown_owner_while_alive"] += row.get("BallStatus") == "1" and row.get("BallPossession") not in ("1", "2")
            try:
                stamp = datetime.fromisoformat(row["T"])
            except (KeyError, ValueError):
                raise DataValidationError("Missing/invalid DFL ball timestamp") from None
            if series in last_times and abs((stamp-last_times[series]).total_seconds() - (frame_id-previous)/25) > .002:
                raise DataValidationError("DFL timestamps do not agree with 25 Hz frame IDs")
            last_times[series] = stamp
        else:
            slot = slots[object_id]
            if player_seen[index, slot]:
                raise DataValidationError("Duplicate DFL player frame")
            player_seen[index, slot], players[index, slot] = True, xy
    quality["missing_ball_records"] = int((~ball_seen).sum())
    # Sportec: centred metres, y upwards. Metrica: corner origin, y downwards.
    # Keep actual source dimensions: rescaling to BAR-ATH would distort physics.
    pitch = np.asarray(metadata["pitch_dims"], dtype=np.float32)
    for array in (players, ball):
        array[..., 0] = array[..., 0] / pitch[0] + .5
        array[..., 1] = .5 - array[..., 1] / pitch[1]
    frame_ids = np.array([key[1] for key in keys], dtype=np.int32)
    period_ids = np.array([key[0] for key in keys], dtype=np.int8)
    inputs = ExternalInputs(players, ball, np.isfinite(players).all(axis=-1), np.isfinite(ball).all(axis=-1),
                            np.array([metadata["players"][key] for key in player_ids]), frame_ids, period_ids, 25., tuple(pitch.tolist()))
    targets = ExternalTargets(labels, frame_ids.copy(), period_ids.copy())
    return inputs, targets, {"quality": dict(quality), "period_duration_metadata_checked": bool(metadata["durations"]),
                             "coordinate_convention": "Metrica normalized; actual source pitch in metres",
                             "raw_speed_unit": "km/h (DFL specification); not exposed to predictors",
                             "units_policy": "no supplied speed used; future derivatives must respect periods, gaps and track fragments"}


def atomic_npz(path, **arrays):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_match(match_id, *, progress=None):
    role = match_role(match_id)
    paths = fetch_match(match_id, progress=progress)
    inputs, targets, report = parse_match(paths["metadata"], paths["positions"], match_id)
    folder = dataset_root() / "prepared" / match_id
    payload = inputs.feature_dict()
    atomic_npz(folder / "inputs.npz", **payload)
    atomic_npz(folder / "targets.npz", labels=targets.labels, frame_ids=targets.frame_ids, period_ids=targets.period_ids)
    manifest = {"match_id": match_id, "role": role, "parser_version": PARSER_VERSION, "label_policy": settings("external_protocol.json")["label_policy"],
                "sources": {kind: {"path": str(path.resolve()), "sha256": sha256_file(path), "md5": md5_file(path)} for kind, path in paths.items()},
                "protocol_sha256": sha256_file(config.MYA_DIR / "configs/external_protocol.json"),
                "inputs_sha256": sha256_file(folder / "inputs.npz"), "targets_sha256": sha256_file(folder / "targets.npz"),
                "frame_count": len(inputs.frame_ids), "slot_count": len(inputs.team_mapping), "pitch_dims": inputs.pitch_dims,
                "label_counts": {label: int((targets.labels == label).sum()) for label in ("H", "A", "D", "X")}, **report}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return inputs, targets, manifest


def load_inputs(match_id):
    match_role(match_id)
    folder = dataset_root() / "prepared" / match_id
    manifest = json.loads((folder / "manifest.json").read_text())
    path = folder / "inputs.npz"
    if sha256_file(path) != manifest["inputs_sha256"] or manifest["parser_version"] != PARSER_VERSION:
        raise DataValidationError("Stale/corrupt external input archive")
    if manifest["protocol_sha256"] != sha256_file(config.MYA_DIR / "configs/external_protocol.json"):
        raise DataValidationError("External protocol changed; re-prepare and document the new experiment")
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != INPUT_KEYS:
            raise DataValidationError("Input archive violates the feature allowlist")
        return ExternalInputs(**{name: (tuple(archive[name].tolist()) if name == "pitch_dims" else float(archive[name]) if name == "fps" else archive[name]) for name in INPUT_KEYS})


def load_targets(match_id, *, purpose):
    role = match_role(match_id)
    allowed = {"training": {"train"}, "validation": {"validation"}, "smoke": {"train"}}
    if purpose not in allowed or role not in allowed[purpose]:
        raise PermissionError("Target purpose does not match the frozen match split")
    folder = dataset_root() / "prepared" / match_id
    manifest = json.loads((folder / "manifest.json").read_text())
    if (sha256_file(folder / "targets.npz") != manifest["targets_sha256"]
            or manifest["parser_version"] != PARSER_VERSION
            or manifest["protocol_sha256"] != sha256_file(config.MYA_DIR / "configs/external_protocol.json")):
        raise DataValidationError("Corrupt external target archive")
    with np.load(folder / "targets.npz", allow_pickle=False) as archive:
        if set(archive.files) != {"labels", "frame_ids", "period_ids"}:
            raise DataValidationError("Unexpected target archive fields")
        return ExternalTargets(**{name: archive[name] for name in archive.files})
