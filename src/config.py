"""Central configuration and Single Source of Truth (SSOT) — Team MYA.

This module centralizes:
1. Dynamic path resolution for workspace, raw data, and team working directories.
2. Geometric pitch specifications and match kinematic constants.
3. Contractual segmentation boundaries (evaluated frames, non-evaluated 'X' masks, 2HT dead zone 'D').
4. Team identifiers, target label alphabet, and official metadata.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Final, List, Tuple

# ==============================================================================
# 1. DYNAMIC PATH RESOLUTION (FULL PORTABILITY)
# ==============================================================================

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Detects the root workspace directory containing both competition git repositories."""
    current = (start_path or Path(__file__)).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "more-than-a-hack-2027").exists() and (parent / "MYA-more-than-a-hack-2027").exists():
            return parent
        if (parent / "more-than-a-hack-2027").exists():
            return parent
    # Default fallback based on standard tree depth
    return current.parent.parent.parent


# Global workspace root
WORKSPACE_ROOT: Final[Path] = find_workspace_root()

# Repository roots
CHALLENGE_DIR: Final[Path] = WORKSPACE_ROOT / "more-than-a-hack-2027"
MYA_DIR: Final[Path] = WORKSPACE_ROOT / "MYA-more-than-a-hack-2027"
SRC_DIR: Final[Path] = MYA_DIR / "src"

# Data directory (configurable via MTAH_DATA_DIR environment variable)
DATA_DIR: Final[Path] = Path(os.environ.get("MTAH_DATA_DIR", CHALLENGE_DIR / "data"))
TACTICAL_DIR: Final[Path] = DATA_DIR / "tactical"
BROADCAST_DIR: Final[Path] = DATA_DIR / "broadcast"

# Official evaluation directories
EVAL_DIR: Final[Path] = CHALLENGE_DIR / "evaluation"
GT_DIR: Final[Path] = EVAL_DIR / "gt"
RESULTS_DIR: Final[Path] = EVAL_DIR / "results"

# Team MYA working directories (created automatically if needed)
CACHE_DIR: Final[Path] = MYA_DIR / ".cache"
SUBMISSIONS_DIR: Final[Path] = MYA_DIR / "submissions"
MODELS_DIR: Final[Path] = MYA_DIR / "models"
REPORTS_DIR: Final[Path] = MYA_DIR / "reports"

for _dir in [CACHE_DIR, SUBMISSIONS_DIR, MODELS_DIR, REPORTS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------------------
# Raw Data Files
# ------------------------------------------------------------------------------

# Tactical Feed (Official challenge prediction reference)
TACTICAL_ATD_TXT: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_atd.txt"
TACTICAL_ATD_XML: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_atd.xml"
TACTICAL_HOMOGRAPHY_CSV: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_homography.csv"
TACTICAL_SMART_TAGGING_XML: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_smart_tagging.xml"
TACTICAL_VIDEO_MP4: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical-002.mp4"

# Broadcast Feed (Complementary multi-angle tracking)
BROADCAST_ATD_TXT: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_atd.txt"
BROADCAST_ATD_XML: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_atd.xml"
BROADCAST_HOMOGRAPHY_CSV: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_homography.csv"
BROADCAST_VIDEO_MP4: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast-001.mp4"

# Public Ground Truth (5 minutes of official evaluation labels)
GT_PUBLIC_CSV: Final[Path] = GT_DIR / "BAR-ATH_possession_gt_public.csv"
GT_PUBLIC_META_JSON: Final[Path] = GT_DIR / "BAR-ATH_possession_gt_public_meta.json"

# High-performance binary cache files (Milestone 1)
TACTICAL_ATD_CACHE_NPZ: Final[Path] = CACHE_DIR / "tactical_atd.npz"
BROADCAST_ATD_CACHE_NPZ: Final[Path] = CACHE_DIR / "broadcast_atd.npz"
TACTICAL_HOMOGRAPHY_CACHE_PARQUET: Final[Path] = CACHE_DIR / "tactical_homography.parquet"
BROADCAST_HOMOGRAPHY_CACHE_PARQUET: Final[Path] = CACHE_DIR / "broadcast_homography.parquet"
SMART_TAGGING_CACHE_PARQUET: Final[Path] = CACHE_DIR / "smart_tagging.parquet"


# ==============================================================================
# 2. PITCH GEOMETRIC & KINEMATIC CONSTANTS
# ==============================================================================

GAME: Final[str] = "BAR-ATH"

# Real metric pitch dimensions (Camp Nou / reference LaLiga stadium)
PITCH_LENGTH: Final[float] = 105.3  # Length in meters (X axis)
PITCH_WIDTH: Final[float] = 68.0   # Width in meters (Y axis)
PITCH_DIMS: Final[Tuple[float, float]] = (PITCH_LENGTH, PITCH_WIDTH)

# Video & Kinematic sampling
FPS: Final[float] = 25.0
DT: Final[float] = 1.0 / FPS       # 0.04 second per frame

# Number of anonymized tracking player slots in ATD
NUM_SLOTS: Final[int] = 46


# ==============================================================================
# 3. TEMPORAL SPECIFICATIONS & FRAME COUNTS
# ==============================================================================

# Exact frame counts
TOTAL_FRAMES: Final[int] = 199319                  # Total tactical video frames (0 to 199,318)
BROADCAST_TOTAL_FRAMES: Final[int] = 164488        # Total broadcast video frames
EVALUATED_FRAMES_COUNT: Final[int] = 158857        # In-play evaluated frames
NON_EVALUATED_FRAMES_COUNT: Final[int] = 40462     # Out-of-play frames (must be labeled 'X')


# ==============================================================================
# 4. CONTRACTUAL INTERVALS & MILESTONE 0 (INCLUSIVE BOUNDS [start, end])
# ==============================================================================

# 1. Pre-match (11,185 frames) -> Strict contractual label 'X'
PRE_MATCH_SPAN: Final[Tuple[int, int]] = (0, 11184)

# 2. First half evaluated play (79,467 frames)
FIRST_HALF_SPAN: Final[Tuple[int, int]] = (11185, 90651)

# 3. Halftime break (20,156 frames) -> Strict contractual label 'X'
HALFTIME_SPAN: Final[Tuple[int, int]] = (90652, 110807)

# 4. Second half evaluated play (79,390 frames)
SECOND_HALF_SPAN: Final[Tuple[int, int]] = (110808, 190197)

# 5. Post-match (9,121 frames) -> Strict contractual label 'X'
POST_MATCH_SPAN: Final[Tuple[int, int]] = (190198, 199318)

# 6. Dead Zone pre-2HT kickoff (2,934 frames) -> Deterministic forced 'D'
# Official 2nd half block starts at 110,808, but actual kickoff is at 113,742.
DEAD_ZONE_2HT_SPAN: Final[Tuple[int, int]] = (110808, 113741)

# Effective match kickoffs
KICKOFF_1ST_HALF: Final[int] = 11185
KICKOFF_2ND_HALF: Final[int] = 113742

# Halftime canonical flip frame
HALFTIME_FLIP_FRAME: Final[int] = 110808

# Public validation window (7,500 frames / 5 minutes)
PUBLIC_WINDOW_SPAN: Final[Tuple[int, int]] = (11185, 18684)
PUBLIC_WINDOW_COUNT: Final[int] = 7500


# ==============================================================================
# 5. TEAMS, MAPPINGS & TARGET ALPHABET
# ==============================================================================

HOME_TEAM_NAME: Final[str] = "Barcelona"
HOME_TEAM_LABEL: Final[str] = "H"
HOME_TEAM_ID: Final[str] = "MET_user_team_o4Hossvb8M"

AWAY_TEAM_NAME: Final[str] = "Atletic Club"
AWAY_TEAM_LABEL: Final[str] = "A"
AWAY_TEAM_ID: Final[str] = "MET_user_team_x7C4FFX2HF"

DEAD_BALL_LABEL: Final[str] = "D"
NON_EVALUATED_LABEL: Final[str] = "X"

LABELS: Final[Tuple[str, ...]] = ("H", "A", "D", "X")
ACTIVE_LABELS: Final[Tuple[str, ...]] = ("H", "A", "D")

LABEL_TO_ID: Final[Dict[str, int]] = {"H": 0, "A": 1, "D": 2, "X": 3}
ID_TO_LABEL: Final[Dict[int, str]] = {0: "H", 1: "A", 2: "D", 3: "X"}


# ==============================================================================
# 6. ENVIRONMENT VERIFICATION UTILITY
# ==============================================================================

def check_data_assets() -> Dict[str, bool]:
    """Checks the physical presence of key raw data assets on disk."""
    assets = {
        "tactical_atd_txt": TACTICAL_ATD_TXT.exists(),
        "tactical_atd_xml": TACTICAL_ATD_XML.exists(),
        "tactical_homography_csv": TACTICAL_HOMOGRAPHY_CSV.exists(),
        "tactical_smart_tagging_xml": TACTICAL_SMART_TAGGING_XML.exists(),
        "broadcast_atd_txt": BROADCAST_ATD_TXT.exists(),
        "broadcast_atd_xml": BROADCAST_ATD_XML.exists(),
        "broadcast_homography_csv": BROADCAST_HOMOGRAPHY_CSV.exists(),
        "ground_truth_public_csv": GT_PUBLIC_CSV.exists(),
        "ground_truth_public_meta_json": GT_PUBLIC_META_JSON.exists(),
    }
    return assets


if __name__ == "__main__":
    print(f"✅ WORKSPACE_ROOT : {WORKSPACE_ROOT}")
    print(f"✅ CHALLENGE_DIR  : {CHALLENGE_DIR}")
    print(f"✅ MYA_DIR        : {MYA_DIR}")
    print(f"✅ CACHE_DIR      : {CACHE_DIR}")
    print("\n🔍 Checking data assets:")
    for asset_name, exists in check_data_assets().items():
        status = "✅ Found" if exists else "❌ Missing"
        print(f"  - {asset_name:30s} : {status}")
