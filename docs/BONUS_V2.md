# Phase 2 — protocole et outils du jalon 8

## État

Le plan est publié sur `main` au commit `a913db3`. Le travail expérimental est
sur la branche locale `bonus-phase2`. Le tag local `delivery-v1` référence le
commit J7 `e5d40ba`. Le paquet `release/` et le CSV final C0 restent inchangés.
Ce jalon ne calcule aucun score de candidat et n'entraîne aucun bonus.

## Répartition des responsabilités

- `configs/bonus_v2/protocol.json` : huit familles de stress, 22 conditions,
  paramètres numériques, plis, exclusions et règles d'adoption.
- `sources.json` dans ce dossier : audit documentaire et droits/labels à compléter.
- `budgets.json` : 48 configurations maximales par blocs, 48 h CPU et 24 h de jobs
  GPU au plus. Les moyens GPU ne sont pas supposés disponibles.
- `j9_grid.json` : huit configurations J9 exactes, enregistrées mais non exécutées.
  Les autres grilles doivent être scellées avant leur premier essai.
- `artifact_schema.json` : unités, masques, positions observées/imputées distinctes,
  scores H/A/D et provenance.
- `src/bonus/` : contrats, restrictions de matchs, agrégation S41/R4,
  transformations d'observations, budget atomique et précontrôles.

## Exécuter les précontrôles

Dans le dépôt d'expérimentation, avec les quatre matchs d'apprentissage DFL déjà
préparés et les deux entrées tactiques de C0 accessibles :

```powershell
.venv\Scripts\python.exe -m src.bonus.preflight --all
```

Actions séparées : `--register`, `--profile`, `--validate-suite`. Le premier
registre doit être créé après fixation du code et des configurations J8.
Une modification d'une dépendance déjà scellée bloque sa reprise ; ajouter le
code d'un futur jalon ne modifie pas les dépendances J8 enregistrées.

L'inventaire matériel local utilisé ici est conservé sous `.cache/bonus_v2/`.
Pour préparer le même inventaire Windows sur une autre machine :

```powershell
New-Item -ItemType Directory -Force .cache/bonus_v2
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json | Set-Content .cache/bonus_v2/cpu.json -Encoding utf8
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory | ConvertTo-Json | Set-Content .cache/bonus_v2/memory.json -Encoding utf8
Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json | Set-Content .cache/bonus_v2/display.json -Encoding utf8
```

L'état CUDA du rapport J8 décrit la machine auditée : i7-1355U, Intel Iris Xe,
aucun `nvidia-smi` disponible. Une nouvelle machine exige de vérifier son GPU
avant tout essai qui en dépend ; ce constat ne réserve ni n'installe un GPU.
La commande J8 n'est pas une commande de soumission : `mya.py` reste l'inférence C0.

## Les 22 conditions

S0 propre : une graine. S1 à S7 : graines 20261102, 20261103 et 20261104.
Trous courts : 5–25 images ; longs : 100–500 ; liés au contexte : 25–150 ;
combinés : 25–250. Les taux 20/41/60 % sont le total manquant par période,
arrondi à l'image, et non un ajout aveugle à un manque natif. Une demande plus
faible que le manque natif est refusée ; le propre préserve les observations.

S3 pondère les origines par les joueurs à 5 m et la distance aux lignes, avec
les coefficients enregistrés. Aucune annotation vivant/mort n'entre dans ce masque.
Les biais/noises/outliers n'affectent que les observations livrées et ne changent
pas leur disponibilité. Les métadonnées indiquant exactement quels points ont été
corrompus restent dans `SyntheticAudit` ; elles ne sont pas des caractéristiques
accessibles au modèle. Le prédicteur reçoit seulement `.observations`.

S6/S7 ajoutent permutation dans chaque équipe et pertes par blocs de 250 images.
Les tirages sont indépendants entre périodes et composants. Les sévérités
comparables partagent leur tirage de base. Les coordonnées sources ne sont jamais
modifiées et aucune position manquante n'est rétablie.

Les durées configurées concernent les blocs injectés : des blocs qui se recouvrent
peuvent former des trous observés plus longs. Le validateur rapporte leurs durées
réalisées. Ces stress restent des constructions, pas une simulation validée de
BAR–ATH ; en particulier les très longues absences réelles restent une limite.

## Sélection future

S41 : moyenne par graine, famille S2/S3/S6 et match, à poids égaux. R4 : moyenne
équilibrée des niveaux 0/20/41/60 %, après moyenne par famille et graine.
Le module d'agrégation vérifie la couverture exacte et refuse BAR–ATH/J03WR9.
Il opère sur des résultats fournis, sans charger de labels. Les garde-fous
d'accès aux observations/cibles du pipeline restent séparés.

`require_use` autorise au J8 les observations des quatre matchs d'apprentissage.
Pour les futurs ajustements internes, il refuse le match réservé à l'évaluation.
`validate_fit_sources` contrôle modèle, contexte, prétraitement, prior et calibration.
Les poids C0 publiés ont vu les quatre matchs : C0-OOF doit réapprendre la recette
sur les trois autres. La confirmation connue est réservée à J18 et n'est pas ouverte
par ces précontrôles. Aucun label de BAR–ATH ou du test consommé n'est chargé.

Le registre de budget scelle chaque grille, déduplique les configurations identiques
et comptabilise les coûts réels. Une estimation dépassant le solde bloque le départ.
Un dépassement réel reste enregistré et bloque les travaux suivants ; ce registre
n'est pas un système qui interrompt automatiquement un entraînement déjà lancé.
Les sous-plis et prétraitements doivent aussi être facturés par les futurs jalons.

## Sources nouvelles

Aucun nouveau test dense H/A/D n'est admis à ce stade. SkillCorner 2017461 a été
réservé sur sa seule métadonnée d'identité, avant tracking, labels ou prédictions.
Cadence, conventions D, couverture, provenance et droits restent à valider.
Metrica Sample Data et SoccerNet GSR ne sont pas déclarés benchmarks complets de
possession sur la base de leur documentation seule. PathCRF reprend les mêmes
sept matchs DFL ; ses poids demandent un audit des plis d'apprentissage.

Ne pas déduire D d'une possession nulle ou d'un intervalle de phase absent.
Ne pas interpoler des labels 10 Hz en 25 Hz pour prétendre disposer d'une nouvelle
vérité terrain à 25 Hz. Toute admission ultérieure exige une révision déclarée du
protocole avant les essais qui utiliseraient cette source.

Voir `analysis/JALON_8_VALIDATION.md` pour les preuves agrégées du jalon réalisé.
