# ⚽ More than a Hack 2027 — Team MYA
### Phase 1: Dense Sequential Prediction of Ball Possession (FC Barcelona vs Athletic Club)

Official repository of team **MYA** for the international competition **[More than a Hack 2027](https://landing.mobileworldcapital.com/more-than-a-hack-2027)**, organized jointly by **[Metrica Sports](https://metrica-sports.com)**, **[Barça Innovation Hub (FC Barcelona)](https://www.fcbarcelona.com)**, and the **[Mobile World Capital Barcelona](https://www.mwcbarcelona.com)**.

---

## 👥 The MYA Team
- **Ali ABOUHACHIM-ALAMI**
- **Youssef BENADDI**
- **Maxime BENDAVID**

---

## 🎯 Task & Competition Overview

The challenge is to perform dense frame-by-frame prediction of ball possession for an entire LaLiga EA Sports match (FC Barcelona vs Athletic Club, 2024-2025 season):
- **Input Data**: 199,319 video frames at 25 fps (~2 h 12 min), with 158,857 evaluated game frames (~105 min 54 s).
- **Target Alphabet**: 4 discrete states:
  - `H`: Home team in possession with ball in play (**FC Barcelona**).
  - `A`: Away team in possession with ball in play (**Athletic Club**).
  - `D`: Dead ball (ball out of play, stoppages, fouls, goals, substitutions).
  - `X`: System abstention / non-evaluated periods (pre-match, halftime, post-match).
- **Primary Metric**: **`spellF1`** (Temporal Action Segmentation IoU with bijective Hungarian matching averaged across 5 overlap thresholds $\theta \in \{0.3, 0.4, 0.5, 0.6, 0.7\}$).
- **Tie-break Metric**: **`macroF1`** (unweighted frame-level macro F1 across classes $H, A, D$).
- **Official Reference Baseline to Beat**: `baseline_smooth50` (`spellF1 = 0.2433` / `macroF1 = 0.6724`).

---

## 💻 Environment Setup & Quickstart Guide (Onboarding Team MYA)

Ce guide pas-à-pas détaille l'installation complète pour reproduire l'environnement d'ingénierie et exécuter les scripts et notebooks de l'équipe MYA.

### Étape 1 : Structure du Workspace Parent
Le projet repose sur deux dépôts Git frères situés dans un même dossier de travail racine (ex: `More than a hack 2027/`) :
```text
More than a hack 2027/               # Dossier racine du workspace
├── more-than-a-hack-2027/           # Dépôt officiel (données du challenge & scripts d'évaluation)
└── MYA-more-than-a-hack-2027/       # Dépôt de l'équipe MYA (notre pipeline, modèles, notebooks)
```

Créez le dossier racine et placez-vous dedans :
```bash
mkdir -p "More than a hack 2027"
cd "More than a hack 2027"
```

---

### Étape 2 : Cloner le Dépôt Officiel du Challenge
Clonez le dépôt officiel fourni par les organisateurs :
```bash
git clone https://github.com/metrica-sports/more-than-a-hack-2027.git
```

> [!NOTE]
> Les scripts d'évaluation officiels (`evaluation/run_evaluation.py`, `evaluation/possession_metrics.py`) et la vérité terrain publique (`evaluation/gt/BAR-ATH_possession_gt_public.csv`) sont déjà inclus dans ce dépôt.

---

### Étape 3 : Installer les Données Téléchargées dans `more-than-a-hack-2027/data/`
Téléchargez les fichiers bruts du challenge (lien fourni par l'organisation) et placez-les rigoureusement dans `more-than-a-hack-2027/data/` en respectant l'arborescence suivante :

```text
more-than-a-hack-2027/data/
├── tactical/                                # Caméra Tactique (Référence officielle de prédiction)
│   ├── BAR-ATH_tactical_atd.txt             # Tracking optique des 46 slots joueurs + ballon (195 Mo)
│   ├── BAR-ATH_tactical_atd.xml             # Métadonnées EPTS & correspondances équipes
│   ├── BAR-ATH_tactical_homography.csv      # Matrices homographiques 3x3 & reprojection_error
│   ├── BAR-ATH_tactical_smart_tagging.xml   # 638 annotations tactiques SportsCode XML
│   └── BAR-ATH_tactical-002.mp4             # Vidéo tactique haute résolution (4.9 Go, optionnelle)
│
└── broadcast/                               # Caméra Broadcast (Vue multi-angles complémentaire)
    ├── BAR-ATH_broadcast_atd.txt            # Tracking optique broadcast (136 Mo)
    ├── BAR-ATH_broadcast_atd.xml            # Métadonnées EPTS broadcast
    ├── BAR-ATH_broadcast_homography.csv     # Homographies broadcast & validité
    └── BAR-ATH_broadcast-001.mp4            # Vidéo broadcast (14 Go, optionnelle)
```

---

### Étape 4 : Cloner le Dépôt de Code de l'Équipe MYA
Depuis le dossier racine `More than a hack 2027/`, clonez notre dépôt d'équipe à côté du dépôt officiel :
```bash
git clone https://github.com/maxoubvd/MYA-more-than-a-hack-2027.git
cd MYA-more-than-a-hack-2027
```

---

### Étape 5 : Créer et Activer l'Environnement Virtuel
Depuis la racine de `MYA-more-than-a-hack-2027/` :

```bash
# Création de l'environnement virtuel
python3 -m venv .venv
```

**Activation :**
- **Linux / macOS :**
  ```bash
  source .venv/bin/activate
  ```
- **Windows (PowerShell) :**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Windows (Command Prompt) :**
  ```cmd
  .venv\Scripts\activate.bat
  ```

---

### Étape 6 : Installer les Dépendances
Assurez-vous que l'environnement virtuel est activé, puis installez les dépendances :
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Étape 7 : Valider l'Installation & la Détection des Données
Vérifiez immédiatement que la configuration centrale détecte tous les dossiers et assets de données brutes :
```bash
python3 src/config.py
```

**Sortie attendue :**
```text
✅ WORKSPACE_ROOT : .../More than a hack 2027
✅ CHALLENGE_DIR  : .../More than a hack 2027/more-than-a-hack-2027
✅ MYA_DIR        : .../More than a hack 2027/MYA-more-than-a-hack-2027
✅ CACHE_DIR      : .../More than a hack 2027/MYA-more-than-a-hack-2027/.cache

🔍 Vérification des assets :
  - tactical_atd_txt               : ✅ Trouvé
  - tactical_atd_xml               : ✅ Trouvé
  - tactical_homography_csv        : ✅ Trouvé
  - tactical_smart_tagging_xml     : ✅ Trouvé
  - broadcast_atd_txt              : ✅ Trouvé
  - broadcast_atd_xml              : ✅ Trouvé
  - broadcast_homography_csv       : ✅ Trouvé
  - ground_truth_public_csv        : ✅ Trouvé
  - ground_truth_public_meta_json  : ✅ Trouvé
```

---

### Étape 8 : Utilisation Rapide des Chargeurs & du Notebook d'Exploration

#### Utilisation dans un script Python :
```python
from src import config
from src.utils import (
    load_atd,
    load_ground_truth,
    load_homography,
    load_smart_tagging,
    load_team_mapping,
)

# Chargement de la vérité terrain (5 min publiques)
df_gt = load_ground_truth(public_window_only=True)

# Chargement instantané du tracking ATD (avec cache NPZ automatique)
atd = load_atd(source="tactical")
print(f"Tracking players: {atd['players'].shape}")  # (199319, 46, 3)
```

#### Lancement du Notebook d'Exploration :
Le notebook complet d'EDA empirique est disponible à l'emplacement [`analysis/data_exploration.ipynb`](analysis/data_exploration.ipynb) :
1. Ouvrez le notebook dans VS Code ou JupyterLab.
2. Cliquez sur **Select Kernel** en haut à droite.
3. Choisissez **Python Environments...** et sélectionnez `.venv` (`.venv/bin/python`).
4. Toutes les cellules s'exécutent de manière autonome grâce à la résolution dynamique des chemins de `config.py`.

---

## 🏗️ Project Architecture & Repository Structure

The project follows a modular, reproducible engineering structure separating data exploration, implementation planning, modular source components, and generated submissions:

```text
MYA-more-than-a-hack-2027/
├── analysis/                                     # Exploratory analysis & documentation
│   ├── data_exploration.ipynb                    # 100% empirical EDA on raw match data
│   ├── Implementation_Plan.md                    # 7-milestone roadmap (26 operational steps)
│   └── Gemini : Analyse et Benchmark ... .pdf    # Reference modeling and technical report
│
├── src/                                          # Core modular technical pipeline
│   ├── __init__.py
│   ├── config.py                                 # Global pitch dimensions (105.3x68m), frame limits, paths
│   ├── pipeline.py                               # End-to-end execution runner and CLI orchestrator
│   │
│   ├── hygiene/                                  # [Jalon 0] Temporal hygiene & contractual masking
│   │   ├── __init__.py
│   │   ├── masking.py                            # Non-evaluated frame masking (X: 40,462 frames) & 2HT dead zone (D: 2,934 frames)
│   │   ├── guards.py                             # Anti-X guard policy in active play (forward-fill fallback)
│   │   └── validator.py                          # Contractual submission validation (199,319 rows, strict schema)
│   │
│   ├── preprocessing/                            # [Jalon 1] Binary caching, coordinate normalization & filtering
│   │   ├── __init__.py
│   │   ├── atd_parser.py                         # Streaming raw ATD parser (player slots, scalar speeds, ball status)
│   │   ├── cache_manager.py                      # High-speed binary serialization / loading (Parquet / NPZ)
│   │   ├── coordinates.py                        # Metric projection (105.3m x 68.0m) & canonical offensive direction flip
│   │   ├── player_denoising.py                   # Savitzky-Golay / Butterworth low-pass filters & (vx, vy, ax, ay) derivations
│   │   └── smart_tagging.py                      # XML tactical tagging sync (frame = sec * 25), throw-in team resolution
│   │
│   ├── imputation/                               # [Jalon 2] Ball trajectory reconstruction & dead ball detection
│   │   ├── __init__.py
│   │   ├── gap_analyzer.py                       # Functional gap segmentation (micro <=15, medium 16-50, long >50 frames)
│   │   ├── kalman_rts.py                         # PCHIP interpolation & constant acceleration Kalman-RTS smoothing
│   │   ├── broadcast_fusion.py                   # Broadcast multi-view fusion (H^-1 inverse homography & Chamfer alignment)
│   │   └── deadball_detector.py                  # Out-of-bounds trajectory & homography reprojection_error spike detector (D)
│   │
│   ├── features/                                 # [Jalon 3] Permutation-invariant, kinematic & physical features
│   │   ├── __init__.py
│   │   ├── team_assignment.py                    # Dynamic XML mapping of 46 tracking slots to Home (0) vs Away (1)
│   │   ├── k_nearest.py                          # Dynamic K=5 nearest players sorting per team (slot permutation invariance)
│   │   ├── relative_kinematics.py                # Relative distances, approach velocities, Time-To-Interception (TTI, ΔTTI)
│   │   ├── pitch_control.py                      # Fernandez & Bornn / Spearman physical pitch control model (PC_ball)
│   │   ├── collective_dynamics.py                # Team centroids, spatial compactness, defensive/offensive lines
│   │   ├── context_features.py                   # Homography reprojection_error dynamics & smart tagging event proximity
│   │   └── builder.py                            # End-to-end feature matrix extraction and builder
│   │
│   ├── models/                                   # [Jalon 4] Frame-by-frame classification & probability calibration
│   │   ├── __init__.py
│   │   ├── anchors.py                            # High-confidence pseudo-labeling (>98% pure anchors for H, A, D)
│   │   ├── dataset.py                            # Temporal GroupKFold split (15-min blocks) and tabular loaders
│   │   ├── tabular.py                            # Multi-class LightGBM / CatBoost model training & inference
│   │   └── calibration.py                        # Posterior probability calibration (Isotonic Regression / Platt Scaling)
│   │
│   ├── sequential/                               # [Jalon 5] Constrained temporal decoding (TAS)
│   │   ├── __init__.py
│   │   ├── dynamic_matrix.py                     # Kinematic-dependent dynamic transition matrix T(t) with physical rules
│   │   ├── viterbi.py                            # Inhomogeneous dynamic programming Viterbi decoder
│   │   └── hsmm.py                               # Explicit-duration Hidden Semi-Markov Model (HSMM) decoder
│   │
│   ├── refinement/                               # [Jalon 6] Multi-stage convolutional refinement & post-processing
│   │   ├── __init__.py
│   │   ├── mstcn.py                              # PyTorch MS-TCN++ multi-stage dilated temporal convolutions
│   │   ├── smoothing_loss.py                     # Truncated Mean Squared Error (T-MSE) temporal smoothness loss
│   │   ├── spell_filter.py                       # Spurious micro-spell pruning (>=18 frames for H/A, >=10 frames for D)
│   │   └── exporter.py                           # Submission packaging (199,319 frames CSV) & local metric scoring
│   │
│   └── utils/                                    # Shared utilities & evaluation
│       ├── __init__.py
│       ├── loaders.py                            # High-level clean data loaders (ATD, homography, XML, ground truth)
│       ├── metrics.py                            # Official spellF1 (Hungarian bipartite IoU matching) & macroF1
│       ├── pitch.py                              # Pitch coordinate utilities and tactical pitch plotting
│       └── io.py                                 # Safe atomic file I/O and serialization helpers
│
├── requirements.txt                              # Python package dependencies
└── README.md                                     # Project documentation
```

---

## 📚 Key Project References
- Detailed Roadmap & Step-by-Step Guide: [`analysis/Implementation_Plan.md`](analysis/Implementation_Plan.md)
- Exploratory Data Analysis Notebook: [`analysis/data_exploration.ipynb`](analysis/data_exploration.ipynb)
- Technical Report: [`analysis/Gemini : Analyse et Benchmark Possession Football.pdf`](analysis/Gemini%20:%20Analyse%20et%20Benchmark%20Possession%20Football.pdf)
- Official Challenge Repository: [metrica-sports/more-than-a-hack-2027](https://github.com/metrica-sports/more-than-a-hack-2027)
