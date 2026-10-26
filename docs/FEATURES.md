# Caractéristiques du jalon 3

Le programme transforme les observations automatiques en **116 caractéristiques
par image**, accompagnées d'un masque de validité et d'un dictionnaire d'unités.
Cette matrice prépare les scores du jalon 4. Elle ne prédit pas encore H/A/D et
n'a pas été sélectionnée sur les cinq minutes annotées de BAR-ATH.

## Exécution

Depuis la racine du dépôt, après la préparation externe décrite dans le README :

```powershell
.venv\Scripts\python.exe -m src.build_features --source all
.venv\Scripts\python.exe -m src.validate_features
```

La première commande construit les caractéristiques du match DFL d'apprentissage
J03WMX, ajuste deux descripteurs non supervisés sur ses seules observations, puis
traite le tracking tactique. Les fichiers du concours restent locaux. Aucun GPU
n'est nécessaire et aucune nouvelle dépendance n'est ajoutée.

`--source external` régénère uniquement les caractéristiques et descripteurs
externes. `--source tactical` réutilise le descripteur externe compatible, s'il
existe ; sinon les deux colonnes qui en dépendent restent manquantes. Un ancien
descripteur incompatible provoque un arrêt explicite : le régénérer avec `all`.
La préparation/téléchargement externe reste une commande distincte.

## Sorties locales et API

```text
.cache/features/
├── context_model.json
├── external/{features.npz,schema.json,manifest.json}
├── tactical/{features.npz,schema.json,manifest.json}
└── validation.json
```

Les archives contiennent `values` (float32, N × 116), `valid` (bool, même forme),
`names`, `frame_ids` et `period_ids`. `schema.json` donne les noms, unités, groupes
et conventions ; `manifest.json` conserve dimensions, signatures d'entrée et de
code, configuration et diagnostics. Les écritures sont atomiques par fichier ;
les empreintes du manifeste détectent une paire incomplète ou modifiée.

```python
from src import config
from src.build_features import load_matrix

arrays, manifest, schema = load_matrix(config.CACHE_DIR / 'features' / 'tactical')
```

Le notebook utilise exactement cette interface. La construction directe passe
par `build_features(FeatureInputs(...))` ; un conteneur de cibles ou un dictionnaire
mélangeant observations et labels est refusé. Le schéma sans valeurs est partagé
dans [feature_schema.json](feature_schema.json).

## Groupes disponibles

| Groupe | Information et convention |
|---|---|
| Disponibilité et qualité | Ballon observé, liens temporels fiables, débuts de fragments, nombre de pistes disponibles et possiblement dupliquées |
| Absences | Durée du trou, temps depuis/avant observation, censure aux bornes de la période |
| Géométrie collective | Centroïdes, dispersion pondérée, largeur/profondeur, distance entre blocs ; calculable sans ballon |
| Proximité | Trois joueurs les plus proches de chaque équipe, effectifs pondérés à 1/2/5 m, noyaux de distance et différences H/A |
| Cinématique relative | Vitesse relative, vitesse de rapprochement, cohérence de mouvement du joueur actuellement proche ; égalités moyennées |
| Physique du ballon | Vitesse, accélération, distance signée aux lignes, mouvement sortant, faible mouvement et disparition après proximité de ligne |
| Contacts candidats | Pics locaux d'accélération, proéminence, proximité instantanée et minimum dans une fenêtre de ±2 images du même fragment |
| Activité collective | Vitesse médiane pondérée des pistes disponibles et score du mode de faible vitesse ajusté sur observations externes |
| Contexte temporel | Moyennes et support passé/futur à une seconde, sans l'image courante ni traversée de mi-temps |
| Smart Tagging | Soutiens offensifs/défensifs H/A, inconnus, conflits, fenêtres et distances aux bornes de reprises |
| Capteur | Disponibilité de l'homographie, validité et erreur de reprojection non négative en pixels |

Les colonnes optionnelles ont les mêmes noms sur les deux sources. Les tags,
l'homographie et le sens d'attaque ne sont pas fournis par l'interface DFL actuelle :
ces informations restent indisponibles. Leur absence n'est pas une phase neutre.

## Garanties et limites

- Les positions restent dans leur repère original. Les distances et dérivées
  utilisent les dimensions propres à la source : 105,3 × 68 m pour BAR-ATH,
  105 × 68 m pour J03WMX. Les vitesses scalaires XML ne sont jamais utilisées,
  compte tenu du désaccord documentaire kph/m/s.
- Les vitesses sont calculées sur une même piste, jamais sur un rang de proximité.
  Les ruptures, trous, sauts et changements de période coupent les fragments.
  Un filtre symétrique de trois points et les différences centrées n'interpolent
  aucune position manquante. Le mouvement arrière brut est séparé et sert au
  dernier point visible avant disparition. Des changements d'identité sans saut
  détectable restent possibles.
- Les pistes sont anonymes. Le poids d'une piste proche de doublons de son équipe
  est l'inverse de son nombre de voisins à 0,15 m, elle-même comprise. Ce diagnostic
  symétrique réduit les comptes doubles sans supprimer une position ni certifier
  une identité. Des joueurs distincts très proches peuvent être sous-pondérés.
- Le collectif inclut toutes les pistes d'équipe disponibles, potentiellement
  gardiens compris. Aucune identité fiable ne permet de garantir exactement
  vingt joueurs de champ. La médiane exige au moins quatre pistes effectives
  avec vitesse valide ; les comptes de support sont fournis séparément.
- `NaN` avec `valid=False` signifie indisponible. Un effectif nul ou une absence
  observée peut valoir zéro. Toutes les caractéristiques hors des deux périodes
  évaluées tactiques sont masquées. Les durées censurées ne prétendent pas connaître
  ce qui précède/suit une période.
- Le XML tactique fournit le sens de la première mi-temps ; faute de champ explicite
  pour la seconde, le sens est inversé selon la convention EPTS/Kloppy. Seules les
  projections offensives utilisent cet axe : les positions/vecteurs d'origine
  ne sont pas retournés séparément. Aucune orientation n'est déduite des labels.
- Le mélange de deux gaussiennes sur `log1p(vitesse collective)` et le quantile
  d'accélération sont ajustés sur les seules observations de J03WMX, sans cibles.
  Le score de faible activité **n'est pas P(D)**. Le quantile à 98 % repère des
  accélérations élevées ; il n'est pas une calibration de vrais contacts.
- Les échelles et seuils techniques sont publiés dans
  [features.json](../configs/features.json). Ils sont initiaux, sans réglage
  sur BAR-ATH : les portes de vitesse signalent de possibles ruptures et ne
  prouvent aucune impossibilité physique. Leur robustesse reste à comparer.
- Une proximité, un tag, un faible mouvement ou une sortie géométrique candidate
  ne force jamais H/A/D. Sans hauteur de balle, une projection 2D peut simuler
  une sortie. La décision vivant/mort appartient au jalon 4.
- Le contexte futur et les fenêtres symétriques supposent une analyse hors ligne.
  Cette version ne constitue pas un système temps réel.

## Validation

Les tests synthétiques vérifient mouvement analytique, trous, ruptures, doublons,
permutations, unités, bornes de périodes, tags contradictoires et conservation des
inconnus. Les matrices complètes sont relues et comparées avant/après sauvegarde.

`src.validate_features` contrôle les deux archives intégrales et exécute les
19 couples scénario/graine du protocole figé sur un extrait de 2 048 images du
match **d'apprentissage** externe, sans lire `targets.npz`. Chaque couple vérifie
les masques et l'invariance aux permutations. Il contrôle aussi cette invariance
sur un extrait tactique, la provenance et la signature de la soumission de référence.
Ces contrôles fonctionnels n'évaluent pas la précision de possession.

Le test externe final reste verrouillé. Les matrices, descripteurs ajustés et
rapports détaillés sont exclus de Git ; le notebook partagé conserve ses sorties
et compteurs vides. Les résultats d'exécution sont consignés dans
[JALON_3_VALIDATION.md](../analysis/JALON_3_VALIDATION.md).
