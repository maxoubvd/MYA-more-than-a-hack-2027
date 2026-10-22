"""High-performance data loading utilities for the challenge — Team MYA.

This module provides ergonomic and optimized loaders for:
1. Official Ground Truth (public 5-min window or full dataset).
2. Smart Tagging tactical metadata and annotations (SportsCode XML -> pandas DataFrame).
3. Camera-to-pitch homography matrices (3x3 tensors, reprojection errors, validity masks).
4. Anonymized tracking player slot mappings to teams (Home 'H' vs Away 'A').
5. Automatic Tracking Data (ATD) with automatic binary caching (NPZ) reducing loading
   times from minutes down to < 0.5 second.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. GROUND TRUTH LOADERS
# ==============================================================================

def load_ground_truth(
    path: Optional[Path] = None,
    public_window_only: bool = False,
) -> pd.DataFrame:
    """Loads the ground truth file as a pandas DataFrame.

    Args:
        path: Optional path to the ground truth CSV file.
              Defaults to config.GT_PUBLIC_CSV.
        public_window_only: If True, filters to only keep the evaluated frames
                            from the public validation window (frames 11,185 to 18,684).

    Returns:
        pd.DataFrame with columns ['frame', 'label'].
    """
    gt_path = path or config.GT_PUBLIC_CSV
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    df = pd.read_csv(gt_path)

    if public_window_only:
        start_frame, end_frame = config.PUBLIC_WINDOW_SPAN
        mask = (df["frame"] >= start_frame) & (df["frame"] <= end_frame)
        df = df[mask].reset_index(drop=True)

    return df


def load_ground_truth_meta(path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads official ground truth metadata (JSON)."""
    meta_path = path or config.GT_PUBLIC_META_JSON
    if not meta_path.exists():
        raise FileNotFoundError(f"Ground truth metadata not found: {meta_path}")

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# 2. SMART TAGGING LOADER (XML -> DATAFRAME)
# ==============================================================================

def load_smart_tagging(
    path: Optional[Path] = None,
    fps: float = config.FPS,
) -> pd.DataFrame:
    """Parses SportsCode Smart Tagging XML into a structured pandas DataFrame.

    Args:
        path: Optional path to the Smart Tagging XML file.
              Defaults to config.TACTICAL_SMART_TAGGING_XML.
        fps: Video framerate used to convert seconds into frame numbers.

    Returns:
        pd.DataFrame containing:
            - code: Tactical event category (e.g., 'SET PIECES', 'OFFENSIVE PLAY')
            - start_s, end_s: Start and end timestamps in seconds
            - start_frame, end_frame: Start and end converted to video frame indices
            - duration_s, duration_frames: Duration of the phase
            - team: Identified team name ('Barcelona', 'Atletic Club', or None)
            - team_code: Normalized team code ('H', 'A', or None)
            - half: Match half ('1st Half', '2nd Half', or None)
            - phase_type: Sub-type (e.g., 'Throw In', 'Corner', 'Build Up')
            - raw_tags: Complete dictionary of parsed XML group-text labels
    """
    xml_path = path or config.TACTICAL_SMART_TAGGING_XML
    if not xml_path.exists():
        raise FileNotFoundError(f"Smart Tagging XML file not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    rows = []
    for instance in root.iter("instance"):
        code = instance.findtext("code") or ""
        start_s = float(instance.findtext("start") or 0.0)
        end_s = float(instance.findtext("end") or 0.0)

        start_frame = int(round(start_s * fps))
        end_frame = int(round(end_s * fps))

        tags: Dict[str, str] = {}
        for label in instance.findall("label"):
            group = label.findtext("group")
            text = label.findtext("text")
            if group and text:
                tags[group] = text

        team_raw = tags.get("Team")
        team_code = None
        if team_raw == "Barcelona":
            team_code = config.HOME_TEAM_LABEL
        elif team_raw in ("Atletic Club", "Athletic Club"):
            team_code = config.AWAY_TEAM_LABEL

        half_raw = tags.get("Half")
        type_raw = tags.get("Type")

        rows.append({
            "code": code,
            "start_s": start_s,
            "end_s": end_s,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_s": end_s - start_s,
            "duration_frames": end_frame - start_frame,
            "team": team_raw,
            "team_code": team_code,
            "half": half_raw,
            "phase_type": type_raw,
            "raw_tags": tags,
        })

    df = pd.DataFrame(rows)
    return df


# ==============================================================================
# 3. HOMOGRAPHY LOADERS
# ==============================================================================

def load_homography(
    source: str = "tactical",
    path: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Loads homography data for a specified camera recording source.

    Args:
        source: 'tactical' or 'broadcast'.
        path: Optional custom CSV file path.

    Returns:
        Tuple consisting of:
            - matrices: NumPy tensor of shape (N, 3, 3) (NaN where invalid)
            - reprojection_error: 1D NumPy array (N,) of reprojection errors in pixels
            - valid: 1D boolean NumPy array (N,) indicating whether the frame has a valid matrix
            - df: Complete raw pandas DataFrame
    """
    if path is not None:
        csv_path = path
    elif source == "tactical":
        csv_path = config.TACTICAL_HOMOGRAPHY_CSV
    elif source == "broadcast":
        csv_path = config.BROADCAST_HOMOGRAPHY_CSV
    else:
        raise ValueError(f"Unknown camera source '{source}'. Choose 'tactical' or 'broadcast'.")

    if not csv_path.exists():
        raise FileNotFoundError(f"Homography file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    matrix_cols = [f"h{r}{c}" for r in range(3) for c in range(3)]
    missing = [c for c in matrix_cols + ["reprojection_error", "valid"] if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path}: missing required columns {missing}")

    matrices = df[matrix_cols].values.astype(np.float64).reshape(-1, 3, 3)
    reprojection_error = df["reprojection_error"].values.astype(np.float32)
    valid = df["valid"].values.astype(bool)

    return matrices, reprojection_error, valid, df


# ==============================================================================
# 4. PLAYER SLOT TO TEAM MAPPING (EPTS XML)
# ==============================================================================

def load_team_mapping(path: Optional[Path] = None) -> Dict[int, str]:
    """Extracts anonymized player slot index (0..45) -> Team label ('H' or 'A') from ATD XML.

    Args:
        path: Optional path to the ATD metadata XML file.
              Defaults to config.TACTICAL_ATD_XML.

    Returns:
        Dictionary mapping {slot_index: 'H' or 'A'} for all 46 tracking slots.
    """
    xml_path = path or config.TACTICAL_ATD_XML
    if not xml_path.exists():
        raise FileNotFoundError(f"ATD metadata XML not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    slot_to_team: Dict[int, str] = {}
    player_idx = 0

    for elem in root.iter():
        if elem.tag.endswith("Player"):
            team_id = elem.get("teamId")
            if team_id == config.HOME_TEAM_ID:
                team_label = config.HOME_TEAM_LABEL  # 'H'
            elif team_id == config.AWAY_TEAM_ID:
                team_label = config.AWAY_TEAM_LABEL  # 'A'
            else:
                team_label = "U"  # Unknown

            slot_to_team[player_idx] = team_label
            player_idx += 1

    return slot_to_team


# ==============================================================================
# 5. HIGH-PERFORMANCE ATD LOADER (WITH BINARY NPZ CACHE)
# ==============================================================================

def _parse_raw_atd_file(
    file_path: Path,
    num_frames: int,
    num_slots: int = config.NUM_SLOTS,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Parses raw text ATD file in an optimized single streaming pass."""
    players = np.full((num_frames, num_slots, 3), np.nan, dtype=np.float32)
    ball = np.full((num_frames, 3), np.nan, dtype=np.float32)
    frame_ids = np.zeros(num_frames, dtype=np.int32)
    video_frames = np.zeros(num_frames, dtype=np.int32)

    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= num_frames:
                break

            line = line.strip()
            if not line:
                continue

            p0 = line.find(":")
            p1 = line.rfind(":")

            frame_id = int(line[:p0])
            frame_ids[idx] = frame_id
            video_frames[idx] = frame_id - 1

            # Extract player tracking coordinates
            players_part = line[p0 + 1 : p1]
            slots = players_part.split(";")
            for s_idx, s in enumerate(slots):
                if s != "NaN,NaN,NaN" and s:
                    c1 = s.find(",")
                    c2 = s.rfind(",")
                    x_str = s[:c1]
                    y_str = s[c1 + 1 : c2]
                    sp_str = s[c2 + 1 :]
                    players[idx, s_idx, 0] = float(x_str) if x_str != "NaN" else np.nan
                    players[idx, s_idx, 1] = float(y_str) if y_str != "NaN" else np.nan
                    players[idx, s_idx, 2] = float(sp_str) if sp_str != "NaN" else np.nan

            # Extract ball tracking coordinates
            ball_part = line[p1 + 1 :]
            if ball_part != "NaN,NaN,NaN" and ball_part:
                c1 = ball_part.find(",")
                c2 = ball_part.rfind(",")
                bx_str = ball_part[:c1]
                by_str = ball_part[c1 + 1 : c2]
                bs_str = ball_part[c2 + 1 :]
                ball[idx, 0] = float(bx_str) if bx_str != "NaN" else np.nan
                ball[idx, 1] = float(by_str) if by_str != "NaN" else np.nan
                ball[idx, 2] = float(bs_str) if bs_str != "NaN" else np.nan

    return players, ball, frame_ids, video_frames


def load_atd(
    source: str = "tactical",
    max_frames: Optional[int] = None,
    use_cache: bool = True,
    save_cache: bool = True,
) -> Dict[str, Any]:
    """Loads ATD tracking data (players and ball) with optional high-speed binary caching.

    If a compressed .npz cache exists in CACHE_DIR, it loads in < 0.5s.
    Otherwise, the text file is parsed in streaming mode and the cache is created.

    Args:
        source: 'tactical' or 'broadcast'.
        max_frames: Optional number of frames to load (e.g., 5000 for rapid testing).
        use_cache: If True, attempts to load from existing .npz cache file.
        save_cache: If True and max_frames is None, automatically saves parsed data to .npz cache.

    Returns:
        Dictionary containing:
            - 'players': np.ndarray (N, 46, 3) (x, y, scalar speed) normalized in [0, 1]
            - 'ball': np.ndarray (N, 3) (x, y, speed/status) normalized in [0, 1]
            - 'frame_ids': np.ndarray (N,) 1-indexed
            - 'video_frames': np.ndarray (N,) 0-indexed
            - 'team_mapping': Dict[int, str] mapping slot -> 'H' or 'A'
            - 'source': Camera source name ('tactical' or 'broadcast')
    """
    if source == "tactical":
        txt_path = config.TACTICAL_ATD_TXT
        cache_path = config.TACTICAL_ATD_CACHE_NPZ
        expected_frames = config.TOTAL_FRAMES
    elif source == "broadcast":
        txt_path = config.BROADCAST_ATD_TXT
        cache_path = config.BROADCAST_ATD_CACHE_NPZ
        expected_frames = config.BROADCAST_TOTAL_FRAMES
    else:
        raise ValueError(f"Invalid camera source: '{source}'. Choose 'tactical' or 'broadcast'.")

    team_mapping = load_team_mapping()

    # Attempt to load from binary NPZ cache
    if use_cache and cache_path.exists() and max_frames is None:
        logger.info(f"⚡ Loading from binary NPZ cache: {cache_path}")
        loaded = np.load(cache_path)
        return {
            "players": loaded["players"],
            "ball": loaded["ball"],
            "frame_ids": loaded["frame_ids"],
            "video_frames": loaded["video_frames"],
            "team_mapping": team_mapping,
            "source": source,
        }

    # Direct parsing of the raw text file
    num_to_parse = max_frames if max_frames is not None else expected_frames
    logger.info(f"📖 Parsing raw text ATD file ({num_to_parse} frames): {txt_path}")
    t0 = time.time()

    players, ball, frame_ids, video_frames = _parse_raw_atd_file(
        txt_path, num_frames=num_to_parse, num_slots=config.NUM_SLOTS
    )
    t_parse = time.time() - t0
    logger.info(f"✅ Parsing completed in {t_parse:.2f}s")

    # Save to binary cache for future instantaneous loads
    if save_cache and max_frames is None:
        logger.info(f"💾 Saving binary NPZ cache: {cache_path}")
        np.savez_compressed(
            cache_path,
            players=players,
            ball=ball,
            frame_ids=frame_ids,
            video_frames=video_frames,
        )

    return {
        "players": players,
        "ball": ball,
        "frame_ids": frame_ids,
        "video_frames": video_frames,
        "team_mapping": team_mapping,
        "source": source,
    }
