"""Configuration centrale et Source Unique de Vérité (Single Source of Truth) — Équipe MYA.

Ce module centralise :
1. La résolution dynamique des chemins d'accès au workspace, aux données brutes et aux répertoires de travail.
2. Les spécifications géométriques du terrain et les constantes temporelles du match.
3. Les bornes contractuelles de découpage (frames évaluées, intervalles masqués en 'X', zone morte en 'D').
4. Les identifiants des équipes, l'alphabet cible des labels et les métadonnées officielles.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Final, List, Tuple

# ==============================================================================
# 1. RÉSOLUTION DYNAMIQUE DES CHEMINS (PORTABILITÉ TOTALE)
# ==============================================================================

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Détecte la racine du workspace (contenant les dépôts git du challenge)."""
    current = (start_path or Path(__file__)).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "more-than-a-hack-2027").exists() and (parent / "MYA-more-than-a-hack-2027").exists():
            return parent
        if (parent / "more-than-a-hack-2027").exists():
            return parent
    # Fallback par défaut basé sur l'arborescence standard
    return current.parent.parent.parent


# Racine du workspace global
WORKSPACE_ROOT: Final[Path] = find_workspace_root()

# Dépôts respectifs
CHALLENGE_DIR: Final[Path] = WORKSPACE_ROOT / "more-than-a-hack-2027"
MYA_DIR: Final[Path] = WORKSPACE_ROOT / "MYA-more-than-a-hack-2027"
SRC_DIR: Final[Path] = MYA_DIR / "src"

# Répertoire des données (configurable via variable d'environnement MTAH_DATA_DIR)
DATA_DIR: Final[Path] = Path(os.environ.get("MTAH_DATA_DIR", CHALLENGE_DIR / "data"))
TACTICAL_DIR: Final[Path] = DATA_DIR / "tactical"
BROADCAST_DIR: Final[Path] = DATA_DIR / "broadcast"

# Répertoires d'évaluation officielle
EVAL_DIR: Final[Path] = CHALLENGE_DIR / "evaluation"
GT_DIR: Final[Path] = EVAL_DIR / "gt"
RESULTS_DIR: Final[Path] = EVAL_DIR / "results"

# Répertoires de travail de l'équipe MYA (créés automatiquement si nécessaire)
CACHE_DIR: Final[Path] = MYA_DIR / "data" / "cache"
SUBMISSIONS_DIR: Final[Path] = MYA_DIR / "submissions"
MODELS_DIR: Final[Path] = MYA_DIR / "data" / "models"
REPORTS_DIR: Final[Path] = MYA_DIR / "reports"

for _dir in [CACHE_DIR, SUBMISSIONS_DIR, MODELS_DIR, REPORTS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------------------
# Fichiers de données brutes
# ------------------------------------------------------------------------------

# Flux Tactique (Référence officielle du challenge)
TACTICAL_ATD_TXT: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_atd.txt"
TACTICAL_ATD_XML: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_atd.xml"
TACTICAL_HOMOGRAPHY_CSV: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_homography.csv"
TACTICAL_SMART_TAGGING_XML: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical_smart_tagging.xml"
TACTICAL_VIDEO_MP4: Final[Path] = TACTICAL_DIR / "BAR-ATH_tactical-002.mp4"

# Flux Broadcast (Multi-vues synchronisable)
BROADCAST_ATD_TXT: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_atd.txt"
BROADCAST_ATD_XML: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_atd.xml"
BROADCAST_HOMOGRAPHY_CSV: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast_homography.csv"
BROADCAST_VIDEO_MP4: Final[Path] = BROADCAST_DIR / "BAR-ATH_broadcast-001.mp4"

# Vérité Terrain Publique (5 minutes d'évaluation officielle)
GT_PUBLIC_CSV: Final[Path] = GT_DIR / "BAR-ATH_possession_gt_public.csv"
GT_PUBLIC_META_JSON: Final[Path] = GT_DIR / "BAR-ATH_possession_gt_public_meta.json"

# Fichiers de cache binaire haute performance (Jalon 1)
TACTICAL_ATD_CACHE_NPZ: Final[Path] = CACHE_DIR / "tactical_atd.npz"
BROADCAST_ATD_CACHE_NPZ: Final[Path] = CACHE_DIR / "broadcast_atd.npz"
TACTICAL_HOMOGRAPHY_CACHE_PARQUET: Final[Path] = CACHE_DIR / "tactical_homography.parquet"
BROADCAST_HOMOGRAPHY_CACHE_PARQUET: Final[Path] = CACHE_DIR / "broadcast_homography.parquet"
SMART_TAGGING_CACHE_PARQUET: Final[Path] = CACHE_DIR / "smart_tagging.parquet"


# ==============================================================================
# 2. CONSTANTES GÉOMÉTRIQUES & CINÉMATIQUES DU TERRAIN
# ==============================================================================

GAME: Final[str] = "BAR-ATH"

# Dimensions réelles métriques du terrain (Camp Nou / Stade LaLiga de référence)
PITCH_LENGTH: Final[float] = 105.3  # Longueur en mètres (axe X)
PITCH_WIDTH: Final[float] = 68.0   # Largeur en mètres (axe Y)
PITCH_DIMS: Final[Tuple[float, float]] = (PITCH_LENGTH, PITCH_WIDTH)

# Échantillonnage vidéo & cinématique
FPS: Final[float] = 25.0
DT: Final[float] = 1.0 / FPS       # 0.04 seconde par frame

# Nombre de slots anonymisés joueurs dans le tracking ATD
NUM_SLOTS: Final[int] = 46


# ==============================================================================
# 3. SPÉCIFICATIONS TEMPORELLES & VOLUMÉTRIE
# ==============================================================================

# Nombre exact de frames
TOTAL_FRAMES: Final[int] = 199319                  # Frames de la vidéo tactique (0 à 199 318)
BROADCAST_TOTAL_FRAMES: Final[int] = 164488        # Frames de la vidéo broadcast
EVALUATED_FRAMES_COUNT: Final[int] = 158857        # Frames en jeu évaluées
NON_EVALUATED_FRAMES_COUNT: Final[int] = 40462     # Frames hors-jeu (doivent porter le label X)

# ==============================================================================
# 4. INTERVALLES CONTRACTUELS & JALON 0 (BORNES INCLUSIVES [start, end])
# ==============================================================================

# 1. Avant-match (11 185 frames) -> Label contractuel strict 'X'
PRE_MATCH_SPAN: Final[Tuple[int, int]] = (0, 11184)

# 2. Première mi-temps évaluée (79 467 frames)
FIRST_HALF_SPAN: Final[Tuple[int, int]] = (11185, 90651)

# 3. Pause mi-temps (20 156 frames) -> Label contractuel strict 'X'
HALFTIME_SPAN: Final[Tuple[int, int]] = (90652, 110807)

# 4. Seconde mi-temps évaluée (79 390 frames)
SECOND_HALF_SPAN: Final[Tuple[int, int]] = (110808, 190197)

# 5. Après-match (9 121 frames) -> Label contractuel strict 'X'
POST_MATCH_SPAN: Final[Tuple[int, int]] = (190198, 199318)

# 6. « Zone Morte » début 2nde mi-temps (2 934 frames) -> Forçage déterministe 'D'
# La 2MT commence contractuellement à 110 808 mais le coup d'envoi n'a lieu qu'à 113 742.
DEAD_ZONE_2HT_SPAN: Final[Tuple[int, int]] = (110808, 113741)

# Coups d'envois effectifs
KICKOFF_1ST_HALF: Final[int] = 11185
KICKOFF_2ND_HALF: Final[int] = 113742

# Frame de bascule du sens offensif (mi-temps)
HALFTIME_FLIP_FRAME: Final[int] = 110808

# Fenêtre publique d'évaluation (7 500 frames / 5 minutes)
PUBLIC_WINDOW_SPAN: Final[Tuple[int, int]] = (11185, 18684)
PUBLIC_WINDOW_COUNT: Final[int] = 7500


# ==============================================================================
# 5. ÉQUIPES, MAPPING & ALPHABET OFFICIEL
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
# 6. UTILITAIRE DE VÉRIFICATION DE L'ENVIRONNEMENT
# ==============================================================================

def check_data_assets() -> Dict[str, bool]:
    """Vérifie la présence physique des principaux assets de données sur disque."""
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
    print("\n🔍 Vérification des assets :")
    for asset_name, exists in check_data_assets().items():
        status = "✅ Trouvé" if exists else "❌ Manquant"
        print(f"  - {asset_name:30s} : {status}")
