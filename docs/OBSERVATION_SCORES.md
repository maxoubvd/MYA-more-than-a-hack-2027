# Jalon 4 — scores vivant/mort et équipe

Cette étape transforme les 116 caractéristiques du jalon 3 en **scores
d'observation H/A/D**, sans décodage temporel ni remplacement automatique de la
soumission de référence. Elle fournit une référence par règles, une variante avec
mémoire décroissante et un modèle supervisé sur d'autres matchs autorisés.

## Reproduction

Après l'installation et la construction du jalon 3 :

```powershell
.venv\Scripts\python.exe -m src.observation_pipeline --prepare
.venv\Scripts\python.exe -m src.observation_pipeline --train
.venv\Scripts\python.exe -m src.observation_pipeline --validate
.venv\Scripts\python.exe -m src.observation_pipeline --tactical
```

`--all` exécute ces quatre étapes. La préparation vérifie les fichiers existants
ou télécharge les sources externes épinglées. Elle concerne quatre matchs
d'apprentissage et deux matchs de validation, environ 2,3 Go de XML au total,
plus les caches et sorties. Aucun GPU ni nouvelle dépendance n'est nécessaire.
Pour limiter le nombre de threads de calcul sur une machine utilisée en parallèle,
les variables usuelles `OPENBLAS_NUM_THREADS=1` et `OMP_NUM_THREADS=1` conviennent.

Les réglages sont figés avant apprentissage dans
[observation_model.json](../configs/observation_model.json). Le découpage original,
les scénarios et graines du [protocole externe](external_validation_protocol.md)
ne sont pas modifiés. Le match de test final reste verrouillé.

## Factorisation et séparation des indices

```text
P(D) = score de la tête vivant/mort
P(H) = (1 - P(D)) × P(H | vivant)
P(A) = (1 - P(D)) × (1 - P(H | vivant))
```

La tête d'état possède une liste explicite de 21 entrées : mouvement et
accélération du ballon, distance aux lignes, faible mouvement avec ralentissement
collectif, mouvement collectif passé/futur, et sortie candidate suivie d'absence.
Elle ne reçoit ni distances joueur–ballon, ni noyaux d'équipe, ni tags de contrôle,
ni identités. Déplacer les joueurs par rapport au ballon sans changer les indices
physiques collectifs ne peut donc pas modifier directement P(D).

Les caractéristiques de ralentissement collectif peuvent naturellement refléter
les mouvements réels des joueurs ; cette séparation concerne l'**attribution du
contrôle**, pas l'exclusion de toute observation collective du score d'état.

L'équipe est estimée séparément : une tête utilise les distances et mouvements
relatifs avec ballon visible ; une autre utilise les différences de géométrie et
de mouvement des blocs lorsque la géométrie directe est indisponible. Si une équipe
entière manque, le score conditionnel revient à 0,5 avec support nul. Aucune position
du ballon n'est imputée.

## Références par règles

- `rules` combine des indices physiques continus et indépendants du contrôle pour
  D, et des noyaux géométriques H/A éventuellement contredits par le Smart Tagging.
  Une immobilité n'est pas un arrêt garanti ; l'indice de ballon placé exige aussi
  un ralentissement collectif. Une absence seule n'ajoute pas d'évidence D.
- `rules_hold` ajoute un maintien candidat de l'évidence de la dernière équipe.
  Le logit décroît exponentiellement avec une constante de deux secondes, sans
  prolonger une position. Une nouvelle observation faible ou contradictoire,
  un indice D fort ou une nouvelle période réinitialise la mémoire. Cette constante
  initiale n'a pas été optimisée sur BAR-ATH.

Sans évidence exploitable, la référence par règles émet une distribution uniforme
H/A/D et un indicateur de confiance nul. Les égalités du maximum donnent X dans
le diagnostic image par image, plutôt qu'une attribution arbitraire à H.
Le modèle appris revient également à cette incertitude lorsqu'aucun contexte
physique n'est disponible : un support temporel connu égal à zéro signale une
absence, et ne compte pas comme une observation physique.

## Modèle supervisé léger

Trois régressions logistiques régularisées L2 sont ajustées : état D, équipe avec
géométrie directe, équipe par le collectif. L'optimisation Newton avec recherche
de pas, le gradient final et la convergence sont contrôlés. L'implémentation NumPy
évite d'ajouter un environnement d'apprentissage différent au socle.

Pour l'état, les médianes d'imputation et échelles sont estimées sur les seules
lignes d'apprentissage ; des indicateurs signalent les valeurs manquantes. Pour
les équipes, les variables sont des différences H/A, centrées sur zéro et mises
à l'échelle par leur RMS, sans constante ni indicateurs symétriques ajoutés.
Échanger H et A inverse exactement les scores conditionnels et conserve P(D).

Le modèle utilise les quatre matchs d'apprentissage, chacun en trois conditions
fixées : propre, absences longues de ballon et dégradation combinée, avec la
première graine publiée. Au plus 12 000 lignes régulièrement espacées sur chaque
match/scénario sont conservées. Ce choix réduit le coût, sans créer de séparation
aléatoire d'images entre entraînement et validation. Les cibles inconnues X sont
exclues et la tête d'équipe n'apprend que sur H/A avec les deux équipes observables.

Les deux descripteurs non supervisés du jalon 3 restent ajustés uniquement sur
les observations de J03WMX, un match du groupe d'apprentissage. Ils ne sont pas
réajustés sur les matchs de validation ou le match du concours.

Un seul réglage de régularisation est testé. Il n'y a ni recherche de paramètres,
ni calibration a posteriori, ni pseudo-label BAR-ATH dans cet entraînement.
Les sorties logistiques sont des **estimations non calibrées**. La confiance
publiée vaut `1 - entropie/log(3)` ; elle n'est pas une probabilité de justesse.

## Validation et interprétation

Chaque match de validation est traité intégralement dans les 19 couples
scénario/graine figés. Les trois jeux de scores et la baseline ±50 sont sauvegardés
avant l'ouverture des cibles du match, puis évalués avec le scoreur officiel.
Les mi-temps sont séparées pour éviter la fusion des possessions à leur frontière.

Le rapport compare spellF1, macroF1, nombre de segments et résultats par classe ;
pour les scores probabilistes, il donne aussi log-loss, Brier multiclasse et
Brier séparé pour D et l'équipe en jeu vivant. Aucune incertitude statistique
supposant des images indépendantes n'est annoncée sur deux matchs seulement.

Le modèle du jalon 4 est évalué **image par image**, tandis que la référence ±50
est déjà lissée. Un gain de macroF1 ne garantit pas un gain de spellF1 ; une
sur-segmentation relève du décodage du jalon 5. Le rapport n'adopte aucune variante
automatiquement et ne modifie pas `MYA.csv`.

Le fournisseur externe dispose d'un tracking plus propre et de conventions
d'étiquetage qui peuvent différer de celles du concours. Les masques synthétiques
testent des défauts définis ; ils ne reproduisent pas tous les défauts réels.
Les tags et homographies ne sont pas disponibles dans l'interface externe actuelle,
donc le modèle appris ne les utilise pas. La référence par règles peut exploiter
les tags tactiques pour l'équipe ; leur bénéfice réel reste non mesuré ici.

## Fichiers et API

```text
.cache/observations/
├── model.json                    Coefficients, prétraitement et provenance
├── validation.json               Mesures externes détaillées
├── validation/{match}/{cas}/      Prédictions figées de chaque référence
└── tactical/{rules,rules_hold,logistic}/
    ├── scores.npz
    └── manifest.json
```

Chaque archive donne les probabilités N × 3 dans l'ordre **H, A, D**, les deux
scores binaires, supports, source d'évidence d'équipe, confiance, âge du maintien,
identifiants vidéo et périodes. Hors des périodes tactiques évaluées, les
probabilités sont NaN ; la zone D officiellement publiée n'est pas forcée dans
ces observations. Les masques contractuels restent la responsabilité de l'export
et du futur décodage.

```python
from src import config
from src.observation_pipeline import load_scores

scores, frames, periods, manifest = load_scores(
    config.CACHE_DIR / 'observations' / 'tactical' / 'logistic')
# scores.probabilities, scores.p_dead, scores.p_home_given_alive
```

Les signatures des entrées, de la configuration, du modèle et du code restent
traçables. Une archive modifiée ou une configuration incompatible provoque un arrêt.
Toutes les valeurs, coefficients ajustés, prédictions et sorties de notebook
restent locaux et exclus de Git. Seuls code, tests, réglages initiaux et rapports
agrégés sont partageables.

Les deux matchs peuvent être calculés dans deux processus indépendants avec
`--validate --validation-match J03WPY` et `--validate --validation-match J03WQQ`,
puis réunis avec `--merge-validation`. La réunion vérifie le code, le modèle, les
configurations, l'identité des matchs et la couverture exacte des 152 comparaisons.
