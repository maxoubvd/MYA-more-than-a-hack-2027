# Jalon 10 — imputation courte et contrôle géométrique

La référence est **C0-OOF**, la recette J7 réapprise sur trois matchs pour prédire
le quatrième. Les poids, priors et archives indépendants du J9 sont réutilisés
avec leurs empreintes, sans adopter une variante J9. Les sources J8/J9/C0 restent
inchangées. Les nouveaux modules sont `ball_bridges.py`, `geometry_layer.py` et
`j10.py` dans `src/bonus/`.

## Huit essais enregistrés avant le premier apprentissage

| Essai | Balle reconstruite | Contrôle potentiel |
|---|---|---|
| LINEAR 5 / 10 / 25 | Interpolation linéaire, trous ≤5/10/25 images | Non |
| KALMAN 5 / 10 / 25 | Modèle à vitesse constante, filtre puis lissage RTS, mêmes limites | Non |
| CONTROL | Aucune | Une caractéristique ajoutée à la tête H/A visible |
| LINEAR 25 CONTROL | Interpolation ≤25 images, fixée avant résultats | Même tête que CONTROL |

À 25 Hz, les limites correspondent à 0,2 / 0,4 / 1 seconde **d’images manquantes** ;
le temps entre les deux observations qui encadrent le trou est une image plus long.
La variante combinée est fixée d’avance, pas choisie après classement des méthodes.

## Reconstruction prudente

Seule la balle est reconstruite. Chaque trou doit avoir deux points observés de
chaque côté, dans une période contiguë. Les trous censurés, les bornes absentes,
les déplacements incompatibles et les trous trop longs restent manquants.
Aucun slot de joueur n’est prolongé et aucune identité stable n’est supposée.

Les bornes observées restent inchangées. `PositionLayers` sépare coordonnées
normalisées observées, coordonnées imputées et incertitude en mètres. L’âge et la
durée du trou sont conservés séparément. Les masques livrés ne sont pas remplacés.
Les limites de vitesse, d’accélération, d’incertitude et les paramètres du filtre
sont dans la grille. Ce sont des hypothèses d’ingénierie fixes, pas des garanties
physiologiques ni une incertitude statistiquement calibrée.

Le filtre Kalman représente position et vitesse par axe ; les observations de
droite contraignent la trajectoire par un lissage RTS vers l’arrière. L’usage du
futur est explicite : le projet travaille hors ligne. Il ne traverse jamais une
période ou un trou sans bornes fiables.

## Utilisation dans le modèle

Les points imputés alimentent seulement le calcul géométrique **H/A**. Le score D,
son support physique et toutes les lignes de score non modifiées restent identiques
à C0. Le décodeur conjoint peut néanmoins changer une frontière D indirectement,
car il compare les trois états ensemble. La matrice temporelle et ses échelles
H/A=1, D=2 restent celles du pli C0.

La géométrie d’une balle imputée est mélangée au repli collectif original selon
`exp(-0.5*(incertitude_m/1.5)^2)`. La source équipe 4 désigne explicitement cette
reconstruction ; elle n’est pas présentée comme une balle observée.

Le contrôle potentiel est un indice local au point du ballon : temps d’arrivée
minimal par équipe après une courte projection des positions des joueurs. Il ne
s’agit pas d’un champ de contrôle sur tout le terrain. Une vitesse joueur manquante
utilise une estimation fondée sur la position seule. Le minimum par équipe évite
qu’un doublon exact compte deux fois ; l’indice change de signe sous échange H/A.

Seule une tête logistique H/A visible, à 23 caractéristiques au lieu de 22, est
apprise pour chacun des quatre plis. Elle utilise les mêmes observations V1,
lignes connues et réglages que C0, plus cet indice. La tête collective et D ne sont
pas réapprises ; aucune calibration ni recherche supplémentaire n’est ajoutée.

## Protocole et mesures

Quatre matchs d’apprentissage, chacun tenu à l’écart à tour de rôle ; 22 conditions
V2 par match ; huit variantes plus C0 = 792 comparaisons. Aucun label BAR–ATH,
J03WR9 ou des deux matchs réservés au J18 ne participe. Toutes les prédictions d’un
pli sont figées avant le calcul de ses métriques de possession et de reconstruction.

L’erreur de position compare les coordonnées reconstruites aux **coordonnées DFL
masquées artificiellement**, uniquement où le générateur a retiré un point connu.
Ces coordonnées ne sont pas une mesure indépendante de la vraie trajectoire
physique. RMSE, p90, fraction reconstruite et couverture du proxy d’incertitude
complètent les métriques de possession. Les masques d’injection servent uniquement
au calcul des erreurs, jamais à la reconstruction ou aux caractéristiques.

La décision utilise les mêmes S41, R4, frontières et rappels des possessions courtes
que J8. Une baisse du RMSE ne remplace pas un gain de spellF1. Les longs trous de
S41 dépassent souvent une seconde : il est normal qu’une méthode prudente ne
reconstruise qu’une faible part de ce benchmark.

## Reproduire

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
.venv\Scripts\python.exe -m src.bonus.j10 --all
```

Ou préparer les caractéristiques sans cibles, exécuter les quatre plis séparément,
puis agréger :

```powershell
.venv\Scripts\python.exe -m src.bonus.j10 --prepare
.venv\Scripts\python.exe -m src.bonus.j10 --fold J03WMX
.venv\Scripts\python.exe -m src.bonus.j10 --fold J03WN1
.venv\Scripts\python.exe -m src.bonus.j10 --fold J03WOH
.venv\Scripts\python.exe -m src.bonus.j10 --fold J03WOY
.venv\Scripts\python.exe -m src.bonus.j10 --report
```

Le cache J9 doit être présent et correspondre aux empreintes publiées. Pour le
recréer, utiliser le commit J9 `277f58d` : son exécuteur refuse volontairement un
code ultérieur. J10 autorise les nouveaux modules tout en vérifiant les anciens
fichiers individuellement. Les positions et prédictions restent dans
`.cache/bonus_v2/j10/`, ignoré par Git ; seuls les agrégats sont publiés.
