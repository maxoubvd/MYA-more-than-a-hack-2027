"""Central source contracts and paths. Importing this module never writes files.

Roots follow the package location, even if this checkout is renamed. Environment
overrides are read at process start. Inclusive legacy *_SPAN constants remain
compatible; new *_INTERVALS use half-open video indices.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, Final, Tuple

MYA_DIR: Final[Path] = Path(__file__).resolve().parent.parent
SRC_DIR: Final[Path] = MYA_DIR / "src"
WORKSPACE_ROOT: Final[Path] = MYA_DIR.parent


def find_workspace_root(start_path=None):
    """Legacy alias; the package location is authoritative, not a folder name."""
    return WORKSPACE_ROOT


def _root_from_env(name, default):
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


CHALLENGE_DIR: Final[Path] = _root_from_env("MTAH_CHALLENGE_DIR", WORKSPACE_ROOT / "more-than-a-hack-2027")
DATA_DIR: Final[Path] = _root_from_env("MTAH_DATA_DIR", CHALLENGE_DIR / "data")
CACHE_DIR: Final[Path] = _root_from_env("MTAH_CACHE_DIR", MYA_DIR / ".cache")
TACTICAL_DIR = DATA_DIR / "tactical"
BROADCAST_DIR = DATA_DIR / "broadcast"
EVAL_DIR = CHALLENGE_DIR / "evaluation"
GT_DIR = EVAL_DIR / "gt"
RESULTS_DIR = EVAL_DIR / "results"
SUBMISSIONS_DIR = MYA_DIR / "submissions"
MODELS_DIR = MYA_DIR / "models"
REPORTS_DIR = MYA_DIR / "reports"

TACTICAL_ATD_TXT = TACTICAL_DIR / "BAR-ATH_tactical_atd.txt"
TACTICAL_ATD_XML = TACTICAL_DIR / "BAR-ATH_tactical_atd.xml"
TACTICAL_HOMOGRAPHY_CSV = TACTICAL_DIR / "BAR-ATH_tactical_homography.csv"
TACTICAL_SMART_TAGGING_XML = TACTICAL_DIR / "BAR-ATH_tactical_smart_tagging.xml"
TACTICAL_VIDEO_MP4 = TACTICAL_DIR / "BAR-ATH_tactical-002.mp4"
BROADCAST_ATD_TXT = BROADCAST_DIR / "BAR-ATH_broadcast_atd.txt"
BROADCAST_ATD_XML = BROADCAST_DIR / "BAR-ATH_broadcast_atd.xml"
BROADCAST_HOMOGRAPHY_CSV = BROADCAST_DIR / "BAR-ATH_broadcast_homography.csv"
BROADCAST_VIDEO_MP4 = BROADCAST_DIR / "BAR-ATH_broadcast-001.mp4"
GT_PUBLIC_CSV = GT_DIR / "BAR-ATH_possession_gt_public.csv"
GT_PUBLIC_META_JSON = GT_DIR / "BAR-ATH_possession_gt_public_meta.json"
TACTICAL_ATD_CACHE_NPZ = CACHE_DIR / "tactical_atd.npz"
BROADCAST_ATD_CACHE_NPZ = CACHE_DIR / "broadcast_atd.npz"
TACTICAL_HOMOGRAPHY_CACHE_PARQUET = CACHE_DIR / "tactical_homography.parquet"
BROADCAST_HOMOGRAPHY_CACHE_PARQUET = CACHE_DIR / "broadcast_homography.parquet"
SMART_TAGGING_CACHE_PARQUET = CACHE_DIR / "smart_tagging.parquet"


def ensure_workdirs():
    """Explicit opt-in for callers that need all output directories."""
    for folder in (CACHE_DIR, SUBMISSIONS_DIR, MODELS_DIR, REPORTS_DIR):
        folder.mkdir(parents=True, exist_ok=True)

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
NON_EVALUATED_FRAMES_COUNT: Final[int] = 40462     # Non-evaluated frames (X by our output convention)


# ==============================================================================
# 4. CONTRACTUAL INTERVALS & MILESTONE 0 (INCLUSIVE BOUNDS [start, end])
# ==============================================================================

# 1. Pre-match (11,185 frames) -> X by our output convention; ignored by scorer
PRE_MATCH_SPAN: Final[Tuple[int, int]] = (0, 11184)

# 2. First half evaluated play (79,467 frames)
FIRST_HALF_SPAN: Final[Tuple[int, int]] = (11185, 90651)

# 3. Halftime break (20,156 frames) -> X by our output convention; ignored by scorer
HALFTIME_SPAN: Final[Tuple[int, int]] = (90652, 110807)

# 4. Second half evaluated play (79,390 frames)
SECOND_HALF_SPAN: Final[Tuple[int, int]] = (110808, 190197)

# 5. Post-match (9,121 frames) -> X by our output convention; ignored by scorer
POST_MATCH_SPAN: Final[Tuple[int, int]] = (190198, 199318)

# 6. Dead Zone pre-2HT kickoff (2,934 frames) -> Deterministic forced 'D'
# Official 2nd half block starts at 110,808, but actual kickoff is at 113,742.
DEAD_ZONE_2HT_SPAN: Final[Tuple[int, int]] = (110808, 113741)

# Effective match kickoffs
KICKOFF_1ST_HALF: Final[int] = 11185
KICKOFF_2ND_HALF: Final[int] = 113742

# Halftime canonical flip frame
HALFTIME_FLIP_FRAME: Final[int] = 110808

# Public diagnostic-only window (7,500 frames / 5 minutes)
PUBLIC_WINDOW_SPAN: Final[Tuple[int, int]] = (11185, 18684)
PUBLIC_WINDOW_COUNT: Final[int] = 7500


# ==============================================================================
# 5. TEAMS, MAPPINGS & TARGET ALPHABET
# ==============================================================================

HOME_TEAM_NAME: Final[str] = "Barcelona"
HOME_TEAM_LABEL: Final[str] = "H"

AWAY_TEAM_NAME: Final[str] = "Atletic Club"
AWAY_TEAM_LABEL: Final[str] = "A"

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



# These public boundaries come from games.py/FAQ at official-revision.txt, not
# from manual annotations of this match. Half-open equivalents for new code.
EVALUATED_INTERVALS = ((11185, 90652), (110808, 190198))
NON_EVALUATED_INTERVALS = ((0, 11185), (90652, 110808), (190198, 199319))
DEAD_ZONE_2HT_INTERVAL = (110808, 113742)
PUBLIC_DIAGNOSTIC_INTERVAL = (11185, 18685)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    num_frames: int
    num_slots: int
    txt_path: Path
    xml_path: Path
    homography_path: Path
    video_path: Path
    cache_path: Path


def get_source(source: str) -> SourceSpec:
    if source == "tactical":
        return SourceSpec(source, TOTAL_FRAMES, 46, TACTICAL_ATD_TXT, TACTICAL_ATD_XML,
                          TACTICAL_HOMOGRAPHY_CSV, TACTICAL_VIDEO_MP4, TACTICAL_ATD_CACHE_NPZ)
    if source == "broadcast":
        return SourceSpec(source, BROADCAST_TOTAL_FRAMES, 51, BROADCAST_ATD_TXT, BROADCAST_ATD_XML,
                          BROADCAST_HOMOGRAPHY_CSV, BROADCAST_VIDEO_MP4, BROADCAST_ATD_CACHE_NPZ)
    raise ValueError("Unknown source: expected tactical or broadcast")


if __name__ == "__main__":
    print(f"✅ WORKSPACE_ROOT : {WORKSPACE_ROOT}")
    print(f"✅ CHALLENGE_DIR  : {CHALLENGE_DIR}")
    print(f"✅ MYA_DIR        : {MYA_DIR}")
    print(f"✅ CACHE_DIR      : {CACHE_DIR}")
    print("\n🔍 Checking data assets:")
    for asset_name, exists in check_data_assets().items():
        status = "✅ Found" if exists else "❌ Missing"
        print(f"  - {asset_name:30s} : {status}")

    if not all(check_data_assets().values()):
        raise SystemExit(1)
