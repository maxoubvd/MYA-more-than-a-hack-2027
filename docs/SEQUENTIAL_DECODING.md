# Jalon 5 — continuité et frontières des possessions

Le décodeur transforme les scores d'observation H/A/D figés du jalon 4 en une
séquence temporelle. Il maximise exactement un objectif déclaré sur chaque
période, avec des coûts de transition souples. Cette optimalité ne garantit
ni la vérité des labels ni un optimum de spellF1.

## Reproduction

Prérequis : les étapes d'apprentissage, validation et inférence tactique du jalon 4
doivent avoir produit leurs archives. Le jalon 5 ne réentraîne pas ses classifieurs.

```powershell
.venv\Scripts\python.exe -m src.sequential_pipeline --fit
.venv\Scripts\python.exe -m src.sequential_pipeline --validate
.venv\Scripts\python.exe -m src.sequential_pipeline --tactical
```

`--all` exécute ces trois étapes. Les matchs de validation peuvent être calculés
indépendamment avec `--validate --validation-match J03WPY` et
`--validate --validation-match J03WQQ`, puis réunis avec `--merge-validation`.
La réunion vérifie modèles, code, réglages et couverture des scénarios.

Le traitement utilise NumPy sur CPU, sans nouvelle dépendance. Les quatre indices
de frontières sont mis en cache localement pour les répétitions. Les réglages
sont fixés dans [sequential.json](../configs/sequential.json), avant les mesures :
deux décodeurs comparés, aucune recherche d'hyperparamètres, aucun accès aux labels
publics de BAR-ATH et aucun accès au match de test final.

## Objectif exact

Pour un état `s[t]` dans H/A/D :

```text
score = log(1/3) + somme_t log(max(P_jalon4[t, s[t]], 1e-12))
                  - somme_t>=1 cout[t, s[t-1], s[t]]
```

Les potentiels initiaux sont uniformes. Chaque période est traitée indépendamment :
ni les scores cumulés, ni l'état choisi ne traversent la mi-temps. Une égalité
exacte de l'objectif privilégie le moins de changements, puis l'ordre stable des
indices d'états. Les ambiguïtés temporelles sont exposées séparément.

Les probabilités du jalon 4 sont non calibrées. Les utiliser comme potentiels
dans cet objectif ne les transforme pas en vraisemblances physiques vérifiées.
Il n'y a aucun second vote majoritaire ni suppression de petites séquences après
le décodage. La complexité est linéaire en images pour trois états.

## Apprentissage des transitions

Les nombres de paires de labels adjacents sont calculés sur **les quatre matchs
d'apprentissage externes**, sur leur chronologie complète à 25 Hz. Une inconnue X
ou une frontière de période interrompt le comptage. Les comptes sont regroupés
symétriquement pour H/A, lissés par un pseudo-compte de 0,5, puis normalisés par
ligne. Les coûts de base valent `-log(P_transition)` ; les diagonales restent
les coûts d'un maintien.

Il s'agit d'un a priori de durée géométrique **souple**. Tous les changements
restent possibles après une image : aucune durée minimale H/A ou D n'est imposée.
Les étiquettes des matchs de validation n'ajustent aucune transition. Aucun nombre
de possessions ou pourcentage de D n'est ciblé sur le match du concours.

## Deux versions figées

- `static` : les mêmes coûts appris sur toutes les images d'une période.
- `dynamic`, candidate principale prédéfinie : les coûts hors diagonale peuvent
  être réduits de **50 % au maximum** par des indices automatiques de frontière.
  Une information indisponible laisse le coût de base inchangé.

Les indices sont construits à partir des mêmes observations que le jalon 3 :

| Transition | Indice souple |
|---|---|
| H → A ou A → H | Contexte de contrôle opposé avant/après, renforcé par un contact candidat proche d'un joueur ; le contact seul ne force aucun changement |
| H/A → D | Sortie géométrique au-delà d'une marge, sortie candidate suivie d'absence, ou faible mouvement avec ralentissement collectif |
| D → H/A | Reprise de mouvement du ballon et du collectif dans le terrain ; les bornes de tags de reprise ne renforcent qu'un contexte physique déjà disponible |

Les coûts d'entrée/sortie de D ne lisent aucun indice d'attribution H/A ou de
proximité joueur–ballon. Le chemin global utilise néanmoins les scores H/A/D
conjointement. Une projection 2D, une immobilité, un tag ou une déviation ne
constitue jamais une observation certaine du coup de sifflet ou du contrôle.

Le contexte H/A utilise 0,2 seconde de chaque côté, sans l'image courante. Les
contacts candidats ont une fenêtre de ±2 images ; cette fenêtre exprime une
incertitude de datation. Les contextes restent séparés par période. Le traitement
est hors ligne, pas temps réel.

## Inconnus, contraintes et possessions courtes

Un trou de ballon n'est pas rempli par une position. Si une période possède des
observations informatives, Viterbi peut maintenir un état pendant une absence,
avec les scores et coûts disponibles. Si la période entière est dépourvue
d'observation informative, la sortie reste X, hormis les contraintes explicitement
publiées ; l'a priori de durée ne fabrique pas seul un état D.

Sur la tactique, X est conservé hors périodes évaluées et le D publié avant la
reprise de deuxième mi-temps est imposé **dans** l'optimisation. Ces constantes
viennent de la FAQ et de la configuration commune. Elles ne sont jamais appliquées
aux matchs externes. Le garde-fou refuse une abstention inattendue au lieu de la
remplir silencieusement.

Les tests comprennent des récupérations et arrêts d'une seule image soutenus par
une évidence forte. Ils peuvent survivre malgré les coûts, tandis qu'une faible
micro-déviation peut être éliminée. Sur données réelles, la conservation des
possessions et arrêts de moins de deux secondes est mesurée séparément, avec
l'appariement officiel à IoU 0,5. Ce seuil descriptif n'est pas une règle de filtrage.

## Incertitude des frontières

Deux informations sont fournies, sans modifier le chemin optimal :

1. La marge entre les deux meilleurs chemins complets contraints à des états
   différents sur chaque image, calculée par max-somme avant/arrière. Une marge
   nulle signale une égalité ; l'infini indique un état imposé seul. Cette marge
   n'est pas une probabilité de justesse.
2. Pour chaque changement, un profil de score en déplaçant cette seule frontière
   à ±1 seconde au maximum, en conservant les états voisins et au moins une image
   de chaque segment. L'enveloppe des alternatives à au plus un point de log-score
   est conditionnelle à ces voisins : **ce n'est pas un intervalle de confiance
   statistique**. Les candidats impossibles sont indiqués par `null` dans le JSON.

Aucune frontière n'est déplacée systématiquement au premier contact, ni vers
la date la plus précoce ou la plus tardive après le décodage.

## Validation et sorties

Les mêmes 19 couples scénario/graine sont utilisés sur chacun des deux matchs de
validation. Les scores J4 déjà figés et la baseline sont reproduits avant calcul
des indices physiques. Les prédictions des deux Viterbi sont ensuite sauvegardées
avant l'ouverture des cibles pour la mesure. Le rapport conserve 152 comparaisons :
baseline, modèle brut, Viterbi statique et Viterbi dynamique.

Les mesures incluent spellF1 par seuil d'IoU, macroF1, segmentation, précision et
rappel des frontières, latence des appariements et rappel des segments courts.
Les résultats restent séparés par match ; 19 scénarios ne constituent pas 19
nouveaux matchs indépendants. Aucune amélioration privée n'est déduite des
statistiques globales de BAR-ATH.

```text
.cache/sequential/
├── prior.json
├── cues/{match}/{scenario_graine}/
├── validation.json
├── validation/{match}/{scenario_graine}/{static,dynamic}/
└── tactical/{static,dynamic}/
    ├── predictions.npz
    ├── boundaries.json
    └── manifest.json
submissions/MYA_jalon5.csv          Candidate dynamique distincte, ignoree par Git
submissions/MYA.csv                 Baseline conservee a l'identique
```

`predictions.npz` contient labels, états du chemin, marges, masque d'abstention
explicite, images et périodes. Les profils et artefacts par image restent locaux.
Le CSV distinct est accepté par le validateur officiel, ce qui valide son format,
pas sa précision. Il ne remplace pas automatiquement la baseline.

```python
from src import config
from src.sequential_pipeline import load_sequence

arrays, manifest = load_sequence(config.CACHE_DIR / 'sequential/tactical/dynamic')
# arrays['labels'], arrays['margin'], arrays['frame_ids'], arrays['period_ids']
```

Voir [le rapport du jalon 5](../analysis/JALON_5_VALIDATION.md) pour les mesures,
les tests réalisés et les limites observées. Le notebook conserve ses anciennes
rubriques d'exploration et ajoute une lecture des séquences statique/dynamique.
