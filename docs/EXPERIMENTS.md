# Jalon 6 — Comparaisons, recherche bornée et candidate gelée

## Protocole

`configs/experiments.json` fixe le budget, les comparaisons et les règles de
sélection avant le premier essai. Le registre local `registration.json` conserve
la date UTC, le commit de départ, les empreintes de toutes les sources Python,
des configurations, des archives DFL et du scoreur officiel. Une modification de
ces entrées bloque la reprise du même registre.

Les quatre matchs d'apprentissage sont évalués à tour de rôle : trois apprennent,
un quatrième est évalué intégralement. Les trois têtes logistiques, leur
prétraitement, le descripteur d'activité non supervisé et les transitions sont
réappris sans le match réservé. Les labels restent séparés des observations.
Les caractéristiques géométriques sont mises en cache sans modèle de contexte,
puis reçoivent uniquement le contexte appris dans le groupe concerné.

Les conditions internes sont `clean`, `long_gaps` et `combined`, graine 20261026.
Les périodes d'un match restent ensemble. Les deux matchs de validation externes
ont déjà été examinés aux jalons 4/5 : la confirmation finale n'est donc pas un
nouveau test aveugle. J03WR9 demeure verrouillé. Les cinq minutes publiques de
BAR-ATH ne sont ni ouvertes ni utilisées dans cette étape.

## Recherche enregistrée

1. Quatre combinaisons de familles, soit 16 apprentissages internes :
   `base`, `motion`, `temporal`, `full`. Le socle conserve la géométrie collective,
   les distances et l'état physique instantané. `motion` ajoute les mouvements
   relatifs et les vitesses collectives des têtes d'équipe ; `temporal` ajoute les
   contextes passé/futur, durées d'immobilité et sortie suivie d'absence dans la
   tête d'état. `full` ajoute les deux. Les vitesses instantanées de balle et
   d'activité nécessaires à l'état du jeu restent dans le socle.
2. Chaque famille est décodée avec le réglage statique initial. Parmi les moyennes
   spellF1 à moins de 0,005 de la meilleure, retenir le moins de colonnes d'entrée.
3. Sur cette famille, évaluer neuf réglages : multiplicateurs H/A et D dans
   {0,5 ; 1 ; 2}. Les termes diagonaux du prior restent identiques ; seuls les coûts
   de changement sont multipliés. Ces potentiels modifiés ne sont pas présentés
   comme une nouvelle matrice markovienne normalisée.
4. Calculer le score moyen du réglage et de ses voisins directs dans la grille.
   Parmi les voisinages à moins de 0,005 du meilleur, préférer le rappel des vraies
   possessions de moins de deux secondes, puis les coûts les plus faibles.

Cela représente 48 comparaisons de familles et 108 comparaisons temporelles,
soit **156 comparaisons internes**. Les trois conditions reçoivent le même poids,
comme les quatre matchs. Le voisinage est une protection limitée contre un pic
isolé ; il ne prouve pas une stabilité en dehors de la grille. Un meilleur point
sur le bord n'entraîne pas automatiquement une extension de la recherche.

Aucune durée minimale n'est ajoutée : les HSMM restent au bonus B2. Aucune
calibration probabiliste n'est annoncée. Une température unique des trois scores
et une multiplication globale des coûts temporels peuvent être redondantes pour
l'argmax ; les calibrations distinctes des têtes exigeraient une autre expérience.

## Confirmation et interventions

La liste est figée avant la confirmation sur J03WPY et J03WQQ, chacun dans les
19 conditions/graine du protocole initial :

| Méthode | Ce qu'elle mesure |
|---|---|
| `baseline` | Référence inchangée, majorité ±50 |
| `rules` | État physique par règles, attribution géométrique |
| `rules_hold` | Même référence avec maintien décroissant |
| `raw_selected` | Scores de la famille retenue, sans décodeur |
| `selected` | Même modèle avec réglages temporels retenus en interne |
| `no_collective` | Même candidat, tête de secours sans ballon neutralisée à H/A=0,5 |
| `physical_state` | Même candidat, état D appris remplacé par les règles physiques |
| `j5_static` | Référence J5 statique, modèle complet et coûts initiaux |
| `j5_dynamic` | Référence J5 dynamique, indices physiques souples |

Le retrait du collectif ne change pas la tête d'équipe lorsque la géométrie est
utilisable. La substitution d'état ne change pas la tête d'équipe. Les étiquettes
finales peuvent néanmoins différer ailleurs à cause du décodage global. La
comparaison baseline/règles/modèle change plusieurs composants ; elle ne constitue
pas à elle seule une attribution causale d'un gain à une seule caractéristique.

Les neuf sorties sont sauvegardées et signées pour les 19 conditions d'un match
**avant** d'ouvrir ses cibles pour les mesurer. Les comparaisons J4/J5 préexistantes
sont réutilisées seulement après contrôle des empreintes, des poids, des frames,
des périodes et du prior. Elles ne sont pas réapprises sur la confirmation.
Le modèle complet réutilise exactement l'apprentissage J4 sur les quatre matchs ;
une famille réduite est réapprise sur les quatre matchs avant confirmation.

Règle d'adoption prédéfinie face à `j5_static` : différence moyenne spellF1 ≥−0,005,
différence de chaque match ≥−0,02 et différence moyenne de rappel des possessions
courtes ≥−0,01. Sinon, conserver `j5_static`. Ce garde-fou peut accepter une petite
régression globale : il n'est pas une promesse de gain. Aucun nouveau réglage
n'est lancé après lecture des résultats de confirmation.

Les mesures utilisent le scoreur officiel : spellF1 et ses seuils IoU, macroF1,
frontières, fragmentation, rappel des possessions et arrêts <2 s à IoU=0,5.
Les durées mesurées et empreintes des prédictions complètent le registre. Deux
matchs de confirmation ne permettent pas une estimation solide de l'incertitude
entre matchs ; aucune barre d'erreur basée sur des images supposées indépendantes.

## Reproduction locale

Depuis la racine du dépôt, après préparation J3/J4/J5 :

```powershell
.venv\Scripts\python.exe -m src.experiment_pipeline --prepare
.venv\Scripts\python.exe -m src.experiment_pipeline --internal
.venv\Scripts\python.exe -m src.experiment_pipeline --validate
.venv\Scripts\python.exe -m src.experiment_pipeline --tactical
```

`--all` enchaîne les étapes. CPU et dépendances actuelles suffisent. La recherche
utilise un Viterbi groupé indépendant par expérience, sans calculer les marges de
chaque essai. Ses chemins et ses égalités sont testés contre le décodeur J5. La
candidate tactique utilise le décodeur exact complet avec marges et profils de
frontières. Les deux mi-temps restent indépendantes ; la zone D officielle est
une contrainte dans le décodeur, les images hors périodes restent X.

Sorties locales dans `.cache/experiments/` : `registration.json`, `features/`,
`internal/`, `family_selection.json`, `internal.json`, `bundle.json` (poids,
contexte et prior), `validation/`, `validation.json`, `tactical/`, `candidate.json`.
L'export est `submissions/MYA_jalon6.csv`, distinct de `MYA.csv` et ignoré par Git.
Le choix et les mesures agrégées figurent dans `analysis/JALON_6_VALIDATION.md`.
Les positions, scores et prédictions par image restent locaux ; le notebook
partagé conserve des cellules sans sorties.

Le contrôle du registre recalcule les empreintes des archives DFL, y compris
celles des fichiers de cibles externes, sans les désérialiser comme étiquettes.
Les valeurs des labels ne sont utilisées que dans les phases d'apprentissage
et de mesure. L'export J6 et les vues du notebook conservent donc une dépendance
locale à ces archives pour l'audit ; le chemin de livraison J7 devra séparer
cette vérification du registre de l'inférence depuis le paquet de poids gelé.
Aucun fichier d'annotations BAR-ATH n'entre dans ce contrôle.

Le jalon 7 reste nécessaire pour une reproduction depuis une installation neuve,
l'accès aux poids et le document de soumission. L'export J6 ne prouve pas encore
cette reproduction propre ni un score sur le match privé du concours.
