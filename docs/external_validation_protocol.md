# Protocole externe avant le jalon 3

Version `external-v1`, fixée le 26 octobre 2026 avant le premier score externe.
Le fichier exécutable de référence est `configs/external_protocol.json`. Une
modification des scénarios, du découpage ou des graines exige une nouvelle
version d’expérience ; les caches portant l’ancienne empreinte sont refusés.

## Source, droits et conventions

Source adoptée : DFL IDSSE, Figshare article **28196177, version 1**, sept matchs
Bundesliga / 2. Bundesliga 2022/23, licence **CC BY 4.0**. Chaque fichier attendu
est fixé par ID, taille et MD5 dans `configs/dfl_manifest.json`. Le téléchargement
est atomique et vérifié ; une signature SHA-256 locale complète la provenance.

Attribution : Bassek, M., Rein, R., Weber, H. & Memmert, D. (2025), *An integrated
dataset of spatiotemporal and event data in elite soccer*, Scientific Data 12,
195, DFL / Sportec Solutions. [Article](https://doi.org/10.1038/s41597-025-04505-y),
[données](https://doi.org/10.6084/m9.figshare.28196177.v1),
[licence](https://creativecommons.org/licenses/by/4.0/).

Les champs de possession et d’état de balle sont ceux du fournisseur. L’article
documente le contrôle du ballon, les interruptions et une vérification des données
par des opérateurs. Cela constitue une référence externe autorisée, mais pas une
preuve d’identité parfaite avec la convention du concours. La cohérence de
quelques champs ne remplace pas l’analyse des conventions et des cas limites.

## Découpage fixé avant les scores

Règle déterministe : trier les sept IDs, affecter les quatre premiers à
l’apprentissage, les deux suivants à la validation et le dernier au test final.
Les deux mi-temps de chaque match restent toujours dans le même groupe.

| Usage | Matchs |
|---|---|
| Apprentissage | J03WMX, J03WN1, J03WOH, J03WOY |
| Validation | J03WPY, J03WQQ |
| Test final verrouillé | J03WR9 |

Le match de contrôle initial est **J03WMX, dans l’apprentissage**. Ses scores
vérifient la chaîne de mesure et ne sont pas une performance indépendante sur
un match réservé. Les matchs de validation et de test n’ont pas été téléchargés
ou évalués pendant cette préparation.

Les réglages futurs se feront par validation interne entre matchs d’apprentissage.
Avant une recherche, consigner son budget et les configurations candidates.
Comparer ensuite une liste figée sur les matchs de validation ; ne pas réutiliser
le test final pour choisir les caractéristiques ou les paramètres. Le test est
refusé par les fonctions de téléchargement, ingestion et lecture en mode
développement ; sa prise en charge finale reste à ouvrir après gel de la candidate.

Ce découpage n’isole pas toutes les équipes : plusieurs matchs concernent le même
club. Sept matchs ne suffisent pas à garantir la généralisation à une autre
ligue, une autre saison ou un autre capteur. Les résultats seront présentés par
match et par scénario, avec cette limite explicite.

## Frontière entre observations et cibles

`src/utils/external_data.py` crée deux fichiers locaux distincts :

- **`inputs.npz`** : x/y normalisés, masques d’observation calculés depuis x/y,
  appartenance des pistes à H/A, identifiants de frames et de périodes, cadence
  et dimensions du terrain. Les pistes sont anonymes dans cette interface.
- **`targets.npz`** : labels H/A/D/X et clés d’alignement frame/période.

La classe `ExternalInputs` et sa liste blanche sont les seules entrées acceptées
par `predict_external` et `degrade`. Aucun BallStatus, BallPossession, événement,
nom, numéro de maillot, identité stable, hauteur de balle ou vitesse fournie ne
traverse cette interface. Les identités originales servent uniquement à parser
et aligner les pistes ; elles ne sont pas exposées au prédicteur.

Les cibles sont dérivées directement du XML : statut `0` → D ; statut `1` avec
propriétaire `1` → H ou `2` → A ; information inconnue → X. Un propriétaire
inconnu pendant un arrêt ne change pas D. Aucun statut ou propriétaire manquant
ne devient implicitement A ou D par les valeurs par défaut d’une bibliothèque.

Les lignes sans observation de balle restent présentes. Leur cible reste X si
aucun état n’est fourni. L’ordre, les doublons, les coordonnées non finies, les
références de joueurs/équipes, la continuité des périodes et l’accord des horodatages
avec 25 Hz sont contrôlés. Les durées des périodes sont comparées aux métadonnées.

## Repères, unités et contrôle indépendant

Le Sportec natif utilise des mètres centrés et un axe y vers le haut. L’interface
normalisée suit Metrica : `x_norm=x/PitchX+0.5`, `y_norm=0.5-y/PitchY`.
Les dimensions réelles du match sont conservées pour les distances ; étirer un
terrain de 105 m vers 105,3 m fausserait les mesures physiques. Aucun retournement
du sens d’attaque n’est ajouté sans justification.

Les vitesses XML DFL sont documentées en km/h. Elles sont exclues des entrées
actuelles. Les futures vitesses vectorielles devront être dérivées de fragments
continus à 25 Hz, sans traverser trous, ruptures de piste ou périodes. Le désaccord
d’unité dans les données BAR-ATH reste signalé ; aucun seuil m/s n’est appliqué
à sa vitesse scalaire brute.

`python -m src.external_validation` compare un échantillon borné de 200 frames à
Kloppy 3.19.1 avec `only_alive=False`, `coordinates="metrica"`. Ce contrôle vérifie
la cohérence du parseur, des équipes, des coordonnées et des états connus. Les
valeurs inconnues sont testées synthétiquement et ne sont pas confiées aux défauts
de Kloppy. Ce contrôle n’est pas une nouvelle annotation indépendante.

## Scénarios de robustesse

Les scénarios et graines sont figés dans le JSON. Toutes les dégradations prennent
uniquement `ExternalInputs` ; elles ne voient jamais les cibles et ne modifient
pas les observations originales. Le masquage est construit séparément par période.

| Scénario | Dégradation prévue |
|---|---|
| Propre | Observations d’origine, aucune dégradation supplémentaire |
| Trous courts | 20 % des indices masqués, trous candidats de 5 à 25 frames |
| Trous longs | 41 %, trous candidats de 100 à 500 frames |
| Bruit spatial | Bruit gaussien de 0,25 m sur x/y observés |
| Trous en zone dense | 41 %, départs favorisés par la proximité de plusieurs joueurs, sans labels |
| Pistes interrompues | Réassignation de pistes au sein des équipes et interruptions par blocs |
| Combiné | Trous, bruit spatial et interruptions de pistes |

Graines : 20261026, 20261027, 20261028. Le scénario propre est exécuté une fois,
les six autres trois fois : **19 exécutions**, toutes rapportées sans sélectionner
la meilleure. Les longueurs sont tronquées aux bords des périodes et à la limite
de couverture. Le rapport donne le taux de manque réellement obtenu, y compris
les absences présentes avant masquage.

Ces distributions sont des stress tests reproductibles, pas un modèle prouvé du
capteur du concours. Atteindre 41 % d’absences ne suffit pas à reproduire ses
longueurs de trous, leur dépendance au contexte ou ses erreurs de projection.

## Référence et mesure

La référence reste joueur le plus proche + vote H/A centré ±50, repli D, paramètres
fixés avant ces scores. Les distances utilisent le terrain du match externe et
le lissage reste séparé par période. Aucun masque temporel spécifique BAR-ATH
n’est appliqué à un autre match.

Les prédictions sont écrites avant l’ouverture des cibles par le banc de mesure.
Le scoreur officiel figé calcule spellF1, son détail par IoU, macroF1, fragmentation
et diagnostics de transitions. Une séparation X est insérée entre les périodes
pour empêcher leur fusion par les métriques. Elle n’ajoute aucune frame évaluée.

Un masquage peut paradoxalement améliorer macroF1 parce que la référence assimile
une absence à D. Cela ne prouve pas un meilleur tracking ou une méthode améliorée.
Rapporter les échecs, les scores par classe et les différences entre scénarios.
Ne pas choisir une configuration sur le score public BAR-ATH ou sur une proportion
de D imaginée. Aucune recherche de paramètres n’a lieu dans cette préparation.

## Commandes et fichiers locaux

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-external.txt
.venv\Scripts\python.exe -m src.external_benchmark --prepare --benchmark
.venv\Scripts\python.exe -m src.external_validation
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Le téléchargement initial du match de contrôle représente environ 419 Mo pour le
tracking, plus ses métadonnées. Les données, caches, cibles, prédictions et rapports
restent sous `.cache/external/dfl/28196177/v1/`, ignoré par Git. Les sources,
protocoles et tests synthétiques sont partageables. Aucun label public BAR-ATH
n’est lu et aucune nouvelle caractéristique du jalon 3 n’est développée ici.
