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
- **Primary Metric**: **`spellF1`** (Temporal Action Segmentation IoU with greedy one-to-one matching in descending IoU order averaged across 5 overlap thresholds $\theta \in \{0.3, 0.4, 0.5, 0.6, 0.7\}$).
- **Tie-break Metric**: **`macroF1`** (unweighted frame-level macro F1 across classes $H, A, D$).
- **Official Reference Baseline to Beat**: `baseline_smooth50` (`spellF1 = 0.2433` / `macroF1 = 0.6724`).

---

## 💻 Environment Setup & Quickstart Guide (Onboarding Team MYA)

Le projet est vérifié avec Python 3.12.6 et utilise par défaut deux dépôts voisins. Sous Windows, les commandes ci-dessous sont à exécuter dans PowerShell. L'environnement virtuel évite d'installer les dépendances dans le Python global.

### Étape 1 : Préparer les deux dépôts

Organisation utilisée pour cette installation :

```text
Bureau/
├── more-than-a-hack-2027/       # Dépôt officiel : chargeurs, références, évaluation
└── MYA-more-than-a-hack-2027/   # Dépôt de l'équipe : sources et environnement .venv
```

```powershell
$workspace = [Environment]::GetFolderPath('Desktop')
$officialRepo = Join-Path $workspace 'more-than-a-hack-2027'
$teamRepo = Join-Path $workspace 'MYA-more-than-a-hack-2027'

if (-not (Test-Path -LiteralPath $officialRepo)) {
    git clone https://github.com/metrica-sports/more-than-a-hack-2027.git $officialRepo
}
if (-not (Test-Path -LiteralPath $teamRepo)) {
    git clone https://github.com/maxoubvd/MYA-more-than-a-hack-2027.git $teamRepo
}
Set-Location $teamRepo
```

Le document partagé utilise désormais un nom compatible Windows : `analysis/Gemini - Analyse et Benchmark Possession Football.pdf`. Son contenu est conservé à l’identique.

Les métriques, les CSV de référence et les cinq minutes d'annotations publiques sont dans le dépôt officiel. Le paquet `possession_metrics` ne doit pas être installé depuis PyPI : le notebook importe le module du dossier `evaluation/` officiel.

### Étape 2 : Préparer les données dans Téléchargements

Les données sont téléchargées séparément. Dans l'installation locale, elles restent dans `Téléchargements/Projet foot`. Extraire les XML, TXT et CSV des archives dans les sous-dossiers de leur caméra :

```text
Téléchargements/Projet foot/
├── tactical/
│   ├── BAR-ATH_tactical_atd.txt
│   ├── BAR-ATH_tactical_atd.xml
│   ├── BAR-ATH_tactical_homography.csv
│   ├── BAR-ATH_tactical_smart_tagging.xml
│   ├── BAR-ATH_tactical-002.mp4
│   └── BAR-ATH_tactical.mp4
├── broadcast/
│   ├── BAR-ATH_broadcast_atd.txt
│   ├── BAR-ATH_broadcast_atd.xml
│   ├── BAR-ATH_broadcast_homography.csv
│   ├── BAR-ATH_broadcast-001.mp4
│   └── BAR-ATH_broadcast.mp4
├── BAR-ATH_tactical-002.mp4       # Vidéo téléchargée à son emplacement initial
├── BAR-ATH_broadcast-001.mp4      # Vidéo téléchargée à son emplacement initial
└── ...                          # Archives originales conservées
```

Les noms vidéo avec suffixe correspondent aux fichiers livrés ; les noms sans suffixe sont ceux attendus par les outils officiels. Pour éviter de copier les vidéos, les entrées des sous-dossiers peuvent être des liens physiques NTFS vers les fichiers téléchargés. L'installation locale préparée utilise ces liens : plusieurs noms désignent le même contenu, sans recopier les octets des vidéos.

### Étape 3 : Relier les données au dépôt officiel

Créer des jonctions de dossiers pour conserver les données dans Téléchargements tout en respectant l'arborescence attendue par `config.py` et par le notebook :

```powershell
$dataRoot = Join-Path $env:USERPROFILE 'Downloads\Projet foot'
$officialData = Join-Path $officialRepo 'data'

foreach ($camera in @('tactical', 'broadcast')) {
    $target = Join-Path $dataRoot $camera
    $link = Join-Path $officialData $camera
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Dossier de donnees manquant : $target"
    }
    if (-not (Test-Path -LiteralPath $link)) {
        New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    }
}
```

Si un dossier existe déjà à la place d'une jonction, vérifier son contenu et sa destination avant toute modification. Les fichiers de données sont exclus de Git par le dépôt officiel.

Le notebook et les chargeurs partagent maintenant `src/config.py`. Les jonctions
restent utilisables ; il est aussi possible de configurer les racines pour la
session PowerShell, sans déplacer les données :

```powershell
$env:MTAH_DATA_DIR = Join-Path $env:USERPROFILE 'Downloads\Projet foot'
$env:MTAH_CHALLENGE_DIR = $officialRepo
# Optionnel : $env:MTAH_CACHE_DIR = 'D:\cache-mya'
```

La racine du dépôt MYA est déduite du package et reste correcte si le dossier
est renommé. Aucun dossier n’est créé au simple import de la configuration.

### Étape 4 : Créer l'environnement Python

Avec le Python 3.12 installé dans le dossier utilisateur Windows :

```powershell
$basePython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
& $basePython -m venv .venv
$python = Join-Path $teamRepo '.venv\Scripts\python.exe'
```

Si Python est installé ailleurs, adapter `$basePython`. Utiliser directement `$python` permet de travailler sans modifier la politique d'exécution PowerShell ni activer l'environnement dans tout le système. L'activation classique reste possible : `.\.venv\Scripts\Activate.ps1`.

### Étape 5 : Installer les dépendances et le noyau de notebook

```powershell
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-notebook.txt
& $python -m pip check
& $python -m ipykernel install --prefix (Join-Path $teamRepo '.venv') --name mya-foot --display-name 'Python (MYA foot)'
```

`requirements.txt` fixe le socle minimal (NumPy/Pandas) ;
`requirements-notebook.txt` ajoute les outils du notebook ;
`requirements-bonus.txt` réserve les dépendances des futures expériences.
`requirements-windows-py312.lock.txt` fige tout l’environnement Windows testé.
Pour reproduire exactement cet environnement Windows, installer ce dernier fichier.

La révision officielle est figée dans `official-revision.txt`. Après le clonage,
se placer sur cette révision (ne pas écraser des modifications locales du dépôt officiel) :

```powershell
$officialRevision = (Get-Content official-revision.txt).Trim()
git -C $officialRepo checkout $officialRevision
```

L’import du scoreur vérifie cette révision et l’absence de modifications locales
de ses sources et documents de référence.

### Étape 6 : Vérifier la configuration et les imports

```powershell
& $python -X utf8 src/config.py
& $python -c "import numpy, pandas, matplotlib, kloppy, nbformat, nbclient, ipykernel, jupyterlab; from src.utils import load_atd; print('Imports OK')"
```

La vérification doit trouver les neuf fichiers non vidéo : les quatre fichiers tactiques, les trois fichiers TV, le CSV public et son JSON de métadonnées. Les fichiers vidéo sont facultatifs pour charger le tracking et calculer les références.

Pour vérifier le chargeur tactique sans afficher les données du match :

```python
from src.utils import load_atd

atd = load_atd(source="tactical")
print(atd["players"].shape)  # (199319, 46, 3)
print(atd["ball"].shape)     # (199319, 3)
```

Ce contrôle technique n'entraîne aucun modèle. Les labels des cinq minutes publiques servent uniquement à vérifier le fonctionnement ; ne pas les utiliser pour apprendre ou régler des paramètres.

### Étape 7 : Ouvrir le notebook

Depuis le dépôt MYA :

```powershell
& $python -m jupyterlab analysis/data_exploration.ipynb
```

Dans JupyterLab, sélectionner le noyau **Python (MYA foot)**. Dans VS Code, choisir l'interpréteur `.venv\Scripts\python.exe`. Le dossier de travail doit être le dépôt MYA ou son sous-dossier `analysis/`, afin que le notebook puisse importer le package MYA.

L'installation locale préparée ajoute aussi **`Ouvrir_Notebook.cmd`** à la racine du dépôt : un double-clic ouvre JupyterLab avec le bon Python. Ce lanceur est exclu localement de Git. Les sorties détaillées du notebook peuvent contenir des données privées : les retirer avant publication.

### Étape 8 : Vérifier les références officielles

```powershell
& $python (Join-Path $officialRepo 'evaluation\run_evaluation.py')
```

Cette commande utilise les annotations publiques et les références déjà fournies ; elle ne nécessite pas les vidéos ni un GPU. L'installation des bibliothèques et l'accès aux fichiers ne signifient pas que les jalons de modélisation sont déjà implémentés.

Sur Linux/macOS, conserver le même principe de dépôts voisins, créer `.venv` avec `python3 -m venv .venv`, utiliser `.venv/bin/python` et remplacer les jonctions Windows par des liens de dossiers adaptés.

---



## Jalons 0 et 1 : règles et ingestion

Le [protocole](docs/protocole.md) et le [registre des sources](docs/sources.json)
séparent diagnostic public, entrées automatiques et futures données externes.
Les labels publics sont refusés pour l’apprentissage, la calibration et la
sélection de variantes par les chargeurs du projet.

```powershell
& $python -m unittest discover -s tests -v
& $python -m src.validate_inputs
& $python -m src.hygiene.repository_check
```

La deuxième commande valide intégralement les deux ATD, leurs XML et homographies,
le Smart Tagging, puis l’équivalence lecture directe/cache. Son manifeste reste
dans `.cache/manifests/ingestion.json` et ne doit pas être publié. Elle n’utilise
aucune vérité terrain. Le notebook utilise les mêmes interfaces ; ses sorties
sont effacées dans la version partagée.

Les masques `players_observed` et `ball_observed` indiquent la disponibilité de
x/y, indépendamment de la vitesse. Les copies `*_metres` changent seulement x/y.
**Attention à l’unité de vitesse :** le XML déclare `kph`, la prose officielle
annonce des m/s. `speed_unit` et `speed_documentation_conflict` rendent cette
incohérence explicite ; les valeurs brutes restent inchangées.

Ces deux jalons préparent l’ingestion ; la chaîne de prédiction du jalon 2 est désormais disponible ci-dessous.


## Jalon 2 : générer le premier CSV complet

Depuis la racine du dépôt, après la configuration des données :

```powershell
.venv\Scripts\python.exe -m src.pipeline --output submissions/MYA.csv
```

Cette commande attribue le ballon à l’équipe du joueur le plus proche, puis
applique le vote officiel à ±50 images, séparément à chaque mi-temps. Les vitesses
ne sont pas utilisées. Le choix de cette fenêtre vient de la référence officielle
publiée et précède tout diagnostic public. Sans observation d’équipe exploitable,
la référence rend D ; c’est une hypothèse de départ, pas une preuve d’arrêt de jeu.
`--missing-label X` permet une abstention explicite, sans propagation entre périodes.

Le fichier final a exactement 199 319 lignes `frame,label`, passe le validateur
officiel et possède des octets reproductibles. Les réglages, les signatures
d’entrée et les empreintes du code sont enregistrés localement dans `.cache/runs/`.
Les labels publics ne sont jamais lus par cette commande.

Pour vérifier le format avec le script officiel, en utilisant le dépôt voisin
par défaut :

```powershell
.venv\Scripts\python.exe ..\more-than-a-hack-2027\evaluation\validate_submission.py submissions/MYA.csv
```

Si le dépôt officiel est ailleurs, utiliser son chemin configuré pour ce script.
Le diagnostic public est une action séparée, à effectuer sur une version gelée :

```powershell
.venv\Scripts\python.exe -m src.diagnostics
.venv\Scripts\python.exe -m src.diagnostics --submission submissions/MYA.csv
```

Les quatre scores officiels sont reproduits. Ces commandes ne choisissent aucun
modèle ni paramètre ; les cinq minutes publiques ne sont ni un jeu d’entraînement
ni un jeu de réglage. Les rapports détaillés restent ignorés sous `.cache/`.
Voir [la méthode, les preuves et les limites](analysis/JALON_2_VALIDATION.md).


## Préparation avant le jalon 3

Les cinq prérequis sont réalisés : hypothèses du plan assouplies, un match DFL
complet vérifié, observations séparées des cibles, découpage externe figé et
baseline mesurée avant toute nouvelle méthode.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-external.txt
.venv\Scripts\python.exe -m src.external_benchmark --prepare --benchmark
.venv\Scripts\python.exe -m src.external_validation
```

La première exécution télécharge environ 419 Mo pour le seul match d’apprentissage
J03WMX, depuis Figshare v1 / CC BY 4.0, puis vérifie tailles et empreintes.
L’ingestion garde les arrêts de jeu et refuse les conversions implicites des
statuts inconnus en A ou D. Les observations et labels sont stockés séparément.

Quatre matchs sont réservés à l’apprentissage, deux à la validation et un au
test final verrouillé. Le banc initial comporte 19 exécutions de scénarios figés,
sans optimisation. Ses scores sont des contrôles sur un match d’apprentissage,
pas une preuve de performance sur un match réservé. Aucun label public BAR-ATH
n’est lu ; son CSV de référence reste identique.

Les données, caches, cibles et rapports détaillés restent sous `.cache/` et ne
doivent pas être ajoutés au dépôt. Les tests utilisent seulement des fixtures
synthétiques. Les caractéristiques du jalon 3 sont maintenant réalisées ; voir ci-dessous.

Voir [les résultats et preuves](analysis/PREPARATION_JALON_3.md), le
[protocole de comparaison](docs/external_validation_protocol.md) et les
[sources/version/empreintes](configs/dfl_manifest.json).

## Jalon 3 : caractéristiques fiables

```powershell
.venv\Scripts\python.exe -m src.build_features --source all
.venv\Scripts\python.exe -m src.validate_features
```

La construction produit **116 caractéristiques par image** sur les 199 319 images
tactiques et les 145 967 images du match DFL d'apprentissage. Elle décrit les
absences, mouvements par fragments, proximités par équipe, blocs collectifs,
contacts candidats, indices physiques et contexte tactique. Chaque valeur possède
une unité et un masque de validité ; les inconnus restent manquants.

Deux descripteurs non supervisés sont ajustés sur les seules observations du match
externe d'apprentissage : modes de vitesse collective et quantile d'accélération.
Ils ne prédisent pas encore la possession. Les labels publics et les cibles DFL
ne sont pas lus. Le CSV du jalon 2 conserve exactement son contenu.

Les matrices, manifestes et descripteurs ajustés restent sous `.cache/features/`.
Le notebook propose une section de lecture et de visualisation via la même API.
Exécuter la construction avant cette section et vider les sorties avant publication.
Aucun GPU ni paquet supplémentaire n'est nécessaire.

Voir [les conventions et limites](docs/FEATURES.md), le
[dictionnaire des 116 colonnes](docs/feature_schema.json) et les
[preuves de validation](analysis/JALON_3_VALIDATION.md).

## Architecture et état réel

```text
analysis/                  Notebook, plan et rapports de validation
configs/                   Réglages, signatures et protocole externe figé
docs/                      Règles, sources, conventions et dictionnaire
src/
├── config.py              Racines et contrats des sources
├── pipeline.py            Référence de possession du jalon 2
├── build_features.py      Construction des matrices du jalon 3
├── validate_features.py   Contrôles d'intégration sans labels
├── external_benchmark.py  Banc initial externe à scénarios figés
├── preprocessing/         Parseur, cache, fragments et Smart Tagging
├── features/              Géométrie, mouvement, contexte et constructeur
├── imputation/            Analyse des trous ; aucune imputation dans le socle actuel
├── hygiene/               Masques contractuels et contrôles de publication
├── refinement/            Export CSV reproductible
└── utils/                 Chargeurs contrôlés et ingestion externe
tests/                     Fixtures synthétiques et régressions
```

Les modules de classification et de décodage des jalons 4 à 7, la reconstruction
du ballon, le pitch control et la fusion TV restent prévus par le plan. Leur
présence éventuelle comme fichier vide ne signifie pas qu'ils sont implémentés.
Les états des jalons et bonus font autorité dans le plan ci-dessous.

---

## 📚 Key Project References
- Detailed Roadmap & Step-by-Step Guide: [`analysis/Implementation_Plan.md`](analysis/Implementation_Plan.md)
- Exploratory Data Analysis Notebook: [`analysis/data_exploration.ipynb`](analysis/data_exploration.ipynb)
- Technical Report: [`analysis/Gemini - Analyse et Benchmark Possession Football.pdf`](analysis/Gemini%20-%20Analyse%20et%20Benchmark%20Possession%20Football.pdf)
- Official Challenge Repository: [metrica-sports/more-than-a-hack-2027](https://github.com/metrica-sports/more-than-a-hack-2027)
