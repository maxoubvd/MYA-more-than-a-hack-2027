"""Utilitaires de chargement haute performance des données du challenge — Équipe MYA.

Ce module fournit des fonctions ergonomiques et optimisées pour charger :
1. La Vérité Terrain officielle (publique 5 min ou fichier complet).
2. Les métadonnées et annotations tactiques Smart Tagging (SportsCode XML -> DataFrame pandas).
3. Les homographies caméra-terrain (matrices 3x3, erreurs de reprojection, masques de validité).
4. La cartographie des slots joueurs vers les équipes (Home 'H' vs Away 'A').
5. L'Automatic Tracking Data (ATD) avec mise en cache binaire automatique (NPZ) pour un
   temps de chargement passant de plusieurs minutes à < 0.5 seconde.
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
# 1. CHARGEMENT DE LA VÉRITÉ TERRAIN (GROUND TRUTH)
# ==============================================================================

def load_ground_truth(
    path: Optional[Path] = None,
    public_window_only: bool = False,
) -> pd.DataFrame:
    """Charge le fichier de vérité terrain sous forme de DataFrame pandas.

    Args:
        path: Chemin optionnel vers le fichier CSV de vérité terrain.
              Par défaut : config.GT_PUBLIC_CSV.
        public_window_only: Si True, filtre pour ne conserver que les frames évaluées
                            de la fenêtre publique (frames 11 185 à 18 684).

    Returns:
        pd.DataFrame avec les colonnes ['frame', 'label'].
    """
    gt_path = path or config.GT_PUBLIC_CSV
    if not gt_path.exists():
        raise FileNotFoundError(f"Fichier de vérité terrain introuvable : {gt_path}")

    df = pd.read_csv(gt_path)

    if public_window_only:
        start_frame, end_frame = config.PUBLIC_WINDOW_SPAN
        mask = (df["frame"] >= start_frame) & (df["frame"] <= end_frame)
        df = df[mask].reset_index(drop=True)

    return df


def load_ground_truth_meta(path: Optional[Path] = None) -> Dict[str, Any]:
    """Charge les métadonnées officielles de la vérité terrain (JSON)."""
    meta_path = path or config.GT_PUBLIC_META_JSON
    if not meta_path.exists():
        raise FileNotFoundError(f"Métadonnées GT introuvables : {meta_path}")

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# 2. CHARGEMENT DU SMART TAGGING (XML -> DATAFRAME)
# ==============================================================================

def load_smart_tagging(
    path: Optional[Path] = None,
    fps: float = config.FPS,
) -> pd.DataFrame:
    """Parse le fichier XML SportsCode de Smart Tagging en DataFrame pandas structuré.

    Args:
        path: Chemin optionnel vers le fichier XML de Smart Tagging.
              Par défaut : config.TACTICAL_SMART_TAGGING_XML.
        fps: Fréquence vidéo pour convertir les secondes en numéros de frames.

    Returns:
        pd.DataFrame contenant :
            - code : Catégorie d'événement tactique (ex: 'SET PIECES', 'OFFENSIVE PLAY')
            - start_s, end_s : Début et fin en secondes
            - start_frame, end_frame : Début et fin convertis en frames
            - duration_s, duration_frames : Durée de la phase
            - team : Équipe identifiée ('Barcelona', 'Atletic Club', ou None)
            - team_code : Code équipe ('H', 'A', ou None)
            - half : Mi-temps ('1st Half', '2nd Half', ou None)
            - phase_type : Sous-type (ex: 'Throw In', 'Corner', 'Build Up')
            - raw_tags : Dictionnaire complet des tags bruts
    """
    xml_path = path or config.TACTICAL_SMART_TAGGING_XML
    if not xml_path.exists():
        raise FileNotFoundError(f"Fichier Smart Tagging introuvable : {xml_path}")

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
# 3. CHARGEMENT DES HOMOGRAPHIES
# ==============================================================================

def load_homography(
    source: str = "tactical",
    path: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Charge les données d'homographie pour une source donnée.

    Args:
        source: 'tactical' ou 'broadcast'.
        path: Chemin personnalisé éventuel.

    Returns:
        Tuple composé de :
            - matrices : Tenseur NumPy (N, 3, 3) des matrices homographiques (NaN si non valide)
            - reprojection_error : Vecteur 1D (N,) de l'erreur de reprojection en pixels
            - valid : Vecteur booléen 1D (N,) indiquant si la frame possède une matrice valide
            - df : DataFrame brut complet
    """
    if path is not None:
        csv_path = path
    elif source == "tactical":
        csv_path = config.TACTICAL_HOMOGRAPHY_CSV
    elif source == "broadcast":
        csv_path = config.BROADCAST_HOMOGRAPHY_CSV
    else:
        raise ValueError(f"Source inconnue '{source}'. Utiliser 'tactical' ou 'broadcast'.")

    if not csv_path.exists():
        raise FileNotFoundError(f"Fichier homographie introuvable : {csv_path}")

    df = pd.read_csv(csv_path)

    matrix_cols = [f"h{r}{c}" for r in range(3) for c in range(3)]
    missing = [c for c in matrix_cols + ["reprojection_error", "valid"] if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path}: colonnes manquantes {missing}")

    matrices = df[matrix_cols].values.astype(np.float64).reshape(-1, 3, 3)
    reprojection_error = df["reprojection_error"].values.astype(np.float32)
    valid = df["valid"].values.astype(bool)

    return matrices, reprojection_error, valid, df


# ==============================================================================
# 4. CARTOGRAPHIE DES JOUEURS & SLOTS (XML EPTS)
# ==============================================================================

def load_team_mapping(path: Optional[Path] = None) -> Dict[int, str]:
    """Extrait l'association slot anonyme (0..45) -> Équipe ('H' ou 'A') depuis l'XML ATD.

    Args:
        path: Chemin vers le fichier XML de métadonnées ATD.
              Par défaut : config.TACTICAL_ATD_XML.

    Returns:
        Dictionnaire {slot_index: 'H' ou 'A'} pour les 46 slots.
    """
    xml_path = path or config.TACTICAL_ATD_XML
    if not xml_path.exists():
        raise FileNotFoundError(f"Fichier métadonnées ATD XML introuvable : {xml_path}")

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
                team_label = "U"  # Inconnu

            slot_to_team[player_idx] = team_label
            player_idx += 1

    return slot_to_team


# ==============================================================================
# 5. CHARGEMENT HAUTE PERFORMANCE DE L'ATD (AVEC CACHE BINAIRE NPZ)
# ==============================================================================

def _parse_raw_atd_file(
    file_path: Path,
    num_frames: int,
    num_slots: int = config.NUM_SLOTS,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Parse le fichier texte brut ATD en un passage streaming rapide."""
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

            # Extraction coordonnées joueurs
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

            # Extraction coordonnées ballon
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
    """Charge les données de tracking ATD (joueurs et ballon) de manière optimisée.

    Si un cache compressé .npz existe dans CACHE_DIR, il est chargé en < 0.5s.
    Sinon, le fichier texte est parsé en streaming et le cache est généré.

    Args:
        source: 'tactical' ou 'broadcast'.
        max_frames: Nombre optionnel de frames à charger (ex: 5000 pour tests rapides).
        use_cache: Si True, tente d'utiliser le fichier cache .npz s'il existe.
        save_cache: Si True et max_frames est None, sauvegarde automatiquement le cache .npz.

    Returns:
        Dictionnaire contenant :
            - 'players' : np.ndarray (N, 46, 3) (x, y, vitesse scalaire) normalisés dans [0, 1]
            - 'ball' : np.ndarray (N, 3) (x, y, vitesse/statut) normalisés dans [0, 1]
            - 'frame_ids' : np.ndarray (N,) 1-indexé
            - 'video_frames' : np.ndarray (N,) 0-indexé
            - 'team_mapping' : Dict[int, str] mapping slot -> 'H' ou 'A'
            - 'source' : Nom de la source ('tactical' ou 'broadcast')
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
        raise ValueError(f"Source invalide : '{source}'. Choisir 'tactical' ou 'broadcast'.")

    team_mapping = load_team_mapping()

    # Tentative de chargement via le cache binaire NPZ
    if use_cache and cache_path.exists() and max_frames is None:
        logger.info(f"⚡ Chargement depuis le cache binaire NPZ : {cache_path}")
        loaded = np.load(cache_path)
        return {
            "players": loaded["players"],
            "ball": loaded["ball"],
            "frame_ids": loaded["frame_ids"],
            "video_frames": loaded["video_frames"],
            "team_mapping": team_mapping,
            "source": source,
        }

    # Chargement et parsing direct du fichier texte
    num_to_parse = max_frames if max_frames is not None else expected_frames
    logger.info(f"📖 Parsing du fichier texte ATD ({num_to_parse} frames) : {txt_path}")
    t0 = time.time()

    players, ball, frame_ids, video_frames = _parse_raw_atd_file(
        txt_path, num_frames=num_to_parse, num_slots=config.NUM_SLOTS
    )
    t_parse = time.time() - t0
    logger.info(f"✅ Parsing terminé en {t_parse:.2f}s")

    # Sauvegarde dans le cache si demandé pour un chargement instantané futur
    if save_cache and max_frames is None:
        logger.info(f"💾 Sauvegarde dans le cache NPZ : {cache_path}")
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
