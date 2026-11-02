# Jalon 9 — observations et calibration

## Exécution

Depuis la racine du dépôt, avec l'environnement du projet :

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
.venv\Scripts\python.exe -m src.bonus.j9 --all
```

La grille `configs/bonus_v2/j9_grid.json` reste celle enregistrée au J8 : huit
variantes, pas de recherche supplémentaire. `j9_execution.json` fixe les détails
numériques avant le premier entraînement. `src/bonus/j9.py` orchestre les calculs,
`j9_models.py` adapte les observations et calibre, `j9_logistic.py` ajoute la perte
pondérée sans modifier les sources gelées de C0.

## Séparation des données

Chaque match d'apprentissage est successivement tenu à l'écart. Les trois autres
réapprennent modèles, standardisation, imputation statistique des caractéristiques,
contexte non supervisé et prior de transitions. Cela concerne aussi **C0-OOF** :
les poids publics entraînés sur quatre matchs ne servent pas de référence sur un
match qu'ils ont déjà vu. La recette originale V1 est réapprise pour C0 ; les bonus
apprennent S0/S2/S6 V2 à graine fixe, 12 000 lignes connues par match/condition.

La calibration utilise des prédictions internes supplémentaires : parmi les trois
matchs d'entraînement, deux apprennent et prédisent le troisième. Les calibrateurs
ne voient jamais les cibles du match externe évalué. Les modèles strictement
identiques des sous-plis et les têtes équipe inchangées sont réutilisés, sans
nouveau réglage. Aucun calibrateur n'est ajusté sur les probabilités d'un modèle
appliqué à ses propres lignes d'apprentissage.

Les 22 conditions d'un pli, pour les neuf candidats, sont prédites, décodées et
hachées avant l'ouverture des cibles de ce pli **pour la mesure**. Ces matchs
restent des données de développement déjà connues dans les étapes précédentes ;
il ne s'agit pas d'un nouveau test aveugle. Les deux matchs de confirmation sont
réservés au J18 ; J03WR9 et les labels publics BAR–ATH ne sont pas ouverts.

## Variantes et garanties

- Augmentation V2 seule ; ajout isolé de perte D équilibrée, température D ou Platt D.
- Qualité sur la tête D seule ; puis perte équilibrée ou Platt D.
- Température D et température équipe positive partagée, sans biais H/A.

Les neuf indices qualité correspondent à la continuité, aux durées des trous,
aux bornes temporelles et aux fractions de joueurs observés/avec vitesse valide.
Les masques artificiels de corruption ne sont jamais des caractéristiques.
Aucune incertitude de projection n'est inventée : une homographie et son erreur ne
sont pas disponibles dans les entrées DFL admises. Cette piste reste non testée.

L'équilibrage apprend ses fréquences sur les seules cibles d'entraînement. Les
têtes équipe, le Viterbi et ses échelles H/A=1, D=2 restent fixes. Après calibration,
une absence de toute preuve physique conserve P(D)=1/3 et une absence des deux
équipes conserve P(H|vivant)=1/2. Ni l'absence ni l'immobilité ne forcent D.

## Mesures et fichiers

Les modèles, caractéristiques, probabilités et prédictions restent dans
`.cache/bonus_v2/j9/`, ignoré par Git. Le registre comprend empreintes du code, de
la grille, des entrées/cibles autorisées, du CSV C0, de la baseline J2 et du témoin
de test consommé. Une reprise avec un code ou des données différents est refusée.
Le coût réel CPU est porté au registre de phase, y compris sous-plis et mesures.

`analysis/JALON_9_RESULTS.json` publie seulement des agrégats : 9 candidats ×
4 matchs × 22 conditions = 792 lignes de métriques, jamais les trajectoires ou
prédictions par image. S41 pondère également matchs, scénarios S2/S3/S6 puis
graines ; R4 pondère également les quatre niveaux d'absence. MacroF1, F1/rappel D,
rappel des possessions <1/<2/<5 secondes, frontières à 12/25 images, fragmentation,
log-loss, Brier et ECE D à dix intervalles fixes complètent spellF1 officiel.
Des diagnostics probabilistes séparent visibilité et qualité des liens.

Les critères de garde du J8 servent au filtrage **interne**. Le classement ne
remplace pas C0 et ne déclenche aucun CSV de soumission. Une éventuelle adoption
exige toujours la liste fermée et la confirmation du J18. Une meilleure calibration
sur DFL dégradé ne démontre pas une meilleure calibration sur BAR–ATH.

Pour reproduire le diagnostic D après décodage, après la grille complète :

```powershell
.venv\Scripts\python.exe scripts/j9_diagnostics.py
```

Ce calcul produit `analysis/JALON_9_STRATA.json`, sans entraînement, sélection ou nouvel export de soumission. Le code du diagnostic et ses coûts sont enregistrés séparément.
