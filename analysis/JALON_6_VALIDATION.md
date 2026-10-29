# Jalon 6 — Validation, comparaisons et décision

Réalisé le 29 octobre 2026. Les données du concours et les prédictions par image restent locales.

## Décision

Candidate gelée : **`selected`**, famille **`full`**, Viterbi statique, multiplicateurs H/A **1** et D **2**. Export distinct : `submissions/MYA_jalon6.csv`.

Gain face au J5 statique : **+0,0153** et **+0,0133** de spellF1 selon le match. En revanche, le rappel moyen des possessions de moins de deux secondes baisse légèrement : 0,0492 → 0,0480 et 0,0547 → 0,0526. Le garde-fou enregistré accepte cette petite baisse ; la faiblesse sur les possessions courtes reste ouverte.

Le choix suit la règle enregistrée avant les essais. Les cinq minutes publiques de BAR-ATH ne sont pas ouvertes. J03WR9 reste verrouillé. Les deux matchs de confirmation étaient déjà connus aux jalons 4/5 : ces résultats ne constituent pas un nouveau test aveugle et ne prédisent pas le score privé du concours.

## Recherche interne sans fuite entre matchs

Quatre validations internes laissent chacune un match complet de côté. Le contexte d’activité, les normalisations, les trois têtes et les transitions sont appris sur les trois autres matchs. Conditions : clean, long_gaps et combined, graine 20261026. Les périodes restent ensemble ; aucun partage aléatoire d’images entre apprentissage et évaluation.

| Famille | Colonnes cumulées des trois têtes | spellF1 moyen interne |
|---|---:|---:|
| base | 32 | 0.3504 |
| motion | 42 | 0.3598 |
| temporal | 44 | 0.3629 |
| full | 54 | 0.3732 |

Famille retenue : **full**. Le socle géométrique/physique est fixe ; le facteur mouvement relatif et le facteur contexte temporel sont croisés. Il s’agit des entrées explicites des têtes, pas de 54 caractéristiques uniques supplémentaires à la matrice J3 de 116 colonnes.

| Échelle H/A | Échelle D | spellF1 interne | Moyenne avec voisins | Minimum du voisinage | Rappel des possessions <2 s |
|---:|---:|---:|---:|---:|---:|
| 0.5 | 0.5 | 0.3463 | 0.3549 | 0.3463 | 0.1234 |
| 0.5 | 1 | 0.3513 | 0.3567 | 0.3463 | 0.1206 |
| 0.5 | 2 | 0.3559 | 0.3616 | 0.3513 | 0.1185 |
| 1 | 0.5 | 0.3673 | 0.3638 | 0.3463 | 0.0930 |
| 1 | 1 | 0.3732 | 0.3680 | 0.3513 | 0.0911 |
| 1 | 2 | 0.3776 | 0.3703 | 0.3559 | 0.0890 |
| 2 | 0.5 | 0.3683 | 0.3687 | 0.3673 | 0.0715 |
| 2 | 1 | 0.3704 | 0.3716 | 0.3683 | 0.0609 |
| 2 | 2 | 0.3746 | 0.3742 | 0.3704 | 0.0588 |

La sélection privilégie une zone stable : moyenne du réglage et de ses voisins directs, tolérance de 0,005, puis rappel des vraies possessions courtes. Aucune grille supplémentaire n’est lancée après les résultats. Une grille 3×3 ne prouve pas une stabilité hors de cette plage.

Budget exécuté : **16 apprentissages internes, 48 comparaisons de familles et 108 comparaisons temporelles = 156 comparaisons**. Le modèle complet final conserve les poids J4 appris sur les quatre matchs, tandis que les modèles internes sont tous réappris sans leur match évalué.

## Confirmation externe : 19 conditions par match

Moyennes sur les 19 couples scénario/graine du protocole initial, sans pondération par nombre d’images. Tous les scénarios d’un match sont signés avant ouverture de ses cibles pour cette comparaison. Les mesures détaillées, seuils IoU et frontières sont dans [le CSV agrégé](JALON_6_METRICS.csv).

| Match | Méthode | spellF1 | macroF1 | Rappel possessions <2 s | Segments H/A/D prédits |
|---|---|---:|---:|---:|---:|
| J03WPY | baseline | 0.2401 | 0.4072 | 0.0149 | 608.2 |
| J03WPY | rules | 0.0910 | 0.6362 | 0.1919 | 4206.1 |
| J03WPY | rules_hold | 0.0910 | 0.6744 | 0.1919 | 4208.9 |
| J03WPY | raw_selected | 0.1098 | 0.8160 | 0.1329 | 4815.1 |
| J03WPY | selected | 0.4205 | 0.8313 | 0.0480 | 398.8 |
| J03WPY | no_collective | 0.4011 | 0.8140 | 0.0501 | 408.5 |
| J03WPY | physical_state | 0.3575 | 0.7209 | 0.0429 | 387.7 |
| J03WPY | j5_static | 0.4052 | 0.8283 | 0.0492 | 440.5 |
| J03WPY | j5_dynamic | 0.3990 | 0.8279 | 0.0518 | 457.0 |
| J03WQQ | baseline | 0.2752 | 0.4275 | 0.0281 | 621.3 |
| J03WQQ | rules | 0.0799 | 0.5990 | 0.1829 | 3734.5 |
| J03WQQ | rules_hold | 0.0799 | 0.6358 | 0.1829 | 3734.5 |
| J03WQQ | raw_selected | 0.1001 | 0.8184 | 0.1459 | 5416.7 |
| J03WQQ | selected | 0.4355 | 0.8368 | 0.0526 | 433.3 |
| J03WQQ | no_collective | 0.4217 | 0.8189 | 0.0563 | 438.1 |
| J03WQQ | physical_state | 0.3667 | 0.6926 | 0.0318 | 405.0 |
| J03WQQ | j5_static | 0.4222 | 0.8335 | 0.0547 | 479.4 |
| J03WQQ | j5_dynamic | 0.4136 | 0.8329 | 0.0537 | 498.6 |

Soit **342 comparaisons de confirmation**. Les graines partagent les mêmes matchs et ne sont pas des matchs indépendants. Aucune incertitude statistique entre matchs n’est estimée à partir de ces répétitions.

### Écarts par condition

Moyennes des graines disponibles, pour la candidate interne `selected` et la référence `j5_static`. Le propre clean n’a qu’une graine.

| Match | Condition | spellF1 J5 statique | spellF1 candidate interne | Écart |
|---|---|---:|---:|---:|
| J03WPY | clean | 0.4742 | 0.4847 | +0.0105 |
| J03WPY | short_gaps | 0.4208 | 0.4454 | +0.0246 |
| J03WPY | long_gaps | 0.3812 | 0.3944 | +0.0132 |
| J03WPY | spatial_noise | 0.4433 | 0.4528 | +0.0095 |
| J03WPY | crowded_gaps | 0.3708 | 0.3951 | +0.0243 |
| J03WPY | fragmented_tracks | 0.4469 | 0.4562 | +0.0094 |
| J03WPY | combined | 0.3452 | 0.3577 | +0.0125 |
| J03WQQ | clean | 0.5166 | 0.5252 | +0.0087 |
| J03WQQ | short_gaps | 0.4487 | 0.4634 | +0.0146 |
| J03WQQ | long_gaps | 0.4058 | 0.4222 | +0.0164 |
| J03WQQ | spatial_noise | 0.4727 | 0.4824 | +0.0097 |
| J03WQQ | crowded_gaps | 0.3788 | 0.3947 | +0.0160 |
| J03WQQ | fragmented_tracks | 0.4538 | 0.4650 | +0.0112 |
| J03WQQ | combined | 0.3420 | 0.3556 | +0.0135 |

### Frontières et possessions courtes

| Match | Méthode | F1 frontières ±25 images | Fragmentation moyenne | Possessions courtes réelles, clean | Courtes retrouvées, clean |
|---|---|---:|---:|---:|---:|
| J03WPY | raw_selected | 0.2052 | 9.2955 | 124 | 23 |
| J03WPY | j5_static | 0.4511 | 0.8503 | 124 | 7 |
| J03WPY | selected | 0.4672 | 0.7699 | 124 | 7 |
| J03WQQ | raw_selected | 0.1782 | 10.8334 | 101 | 18 |
| J03WQQ | j5_static | 0.4526 | 0.9588 | 101 | 7 |
| J03WQQ | selected | 0.4692 | 0.8666 | 101 | 7 |

Le rappel court utilise le matching officiel un-à-un à IoU 0,5. L’absence de durée minimale ne garantit pas la conservation de toutes les possessions brèves. Les pénalités souples peuvent encore en effacer. Le petit nombre d’arrêts D de moins de deux secondes sur ces deux matchs ne permet pas une conclusion robuste sur cette catégorie.

## Composants conservés et limites

Le tracking DFL est plus propre que les pistes ATD du concours. Les dégradations sont des tests de robustesse, pas un simulateur validé de BAR-ATH. Les conventions de possession des fournisseurs peuvent différer ; la séparation par match ne garantit pas des équipes ou saisons distinctes. Ces limites empêchent de convertir les scores externes en score attendu au concours.

- Les deux familles additionnelles sont conservées selon la validation interne, avec réapprentissage par match.
- Neutraliser la tête collective fait perdre environ 0,0194 et 0,0138 de spellF1 à la candidate selon le match. Remplacer la tête D apprise par les règles physiques fait perdre environ 0,0630 et 0,0688. Ces interventions soutiennent la conservation des deux têtes sur ce banc.
- Le maintien par règles améliore macroF1 mais pas spellF1 ici. La variante dynamique J5 est moins bonne que la statique sur les deux matchs. Ces variantes ne sont pas ajoutées automatiquement.
- Le décodage global reste nécessaire pour réduire la fragmentation ; les sorties brutes sont une ablation.
- Le maintien par règles est une comparaison indépendante, pas une brique empilée automatiquement sur la logistique.
- Le retrait du collectif neutralise seulement la tête de secours sans géométrie. La substitution d’état remplace seulement la tête D par les règles physiques. Les écarts mesurés ne justifient pas à eux seuls une interdiction universelle de ces variantes.
- Les transitions dynamiques J5 sont conservées comme référence mesurée ; leur motivation physique ne suffit pas à les adopter.
- HSMM, durée minimale, calibration des probabilités, réseaux profonds, reconstruction de balle et fusion TV restent des essais bonus ou futurs. Ils ne sont pas présentés comme évalués par ce jalon.

Règle d’adoption : moyenne spellF1 ≥ J5 statique−0,005 ; chaque match ≥−0,02 ; rappel court moyen ≥−0,01. Sinon repli J5 statique. Détail observé :

| Match | ΔspellF1 candidate interne − J5 statique | Δrappel court |
|---|---:|---:|
| J03WPY | +0.0153 | -0.0013 |
| J03WQQ | +0.0133 | -0.0021 |

Décision automatique selon la règle : **selected**. Aucun réglage supplémentaire sur la confirmation, les ancres BAR-ATH ou les cinq minutes publiques.

## Vérifications et reproduction

- 174 tests passent, dont exclusion du match réservé, familles emboîtées, interventions séparées, garde-fous de sélection et égalité des chemins groupés avec le Viterbi de référence.
- Égalité supplémentaire sur un match complet : 146 211 images, sortie groupée au réglage initial identique à la référence J5 statique figée.
- Notebook : 40 cellules existantes préservées sans changement de source ; 43 cellules au total, dont 28 cellules de code exécutées. Les sorties exécutées restent sous `.cache`, les sorties partagées restent vides. Diagnostic public désactivé et absence d’artefacts J6 gérée.
- CSV de 199 319 images, masques contractuels et contrainte D officielle conservés ; validation interne et validateur officiel sans vérité terrain. Aucune abstention X inattendue dans les périodes observées.
- Baseline et poids J4 inchangés ; les deux anciennes archives J3 sont rafraîchies avec le même contexte appris, puis leurs contrôles fonctionnels sont rejoués.
- Le registre fournit sources, versions, graines, hypothèses, empreintes des prédictions, temps mesurés et décisions. Aucun tableau par image n’est publié.

Matériel : Intel i7-1355U, 10 cœurs / 12 processeurs logiques, environ 15.7 Gio de RAM ; aucun GPU. Recherche interne : 469.4 s ; confirmation : 586.1 s ; décodage/export tactique : 2.6 s. La préparation des caractéristiques et les contrôles globaux s’ajoutent ; ces temps dépendent de la machine et du cache.

Les durées de décodage groupé couvrent trois variantes à la fois. Les références J4/J5 réutilisent leurs prédictions signées ; aucun classement équitable du temps complet de toutes les méthodes n’est établi à partir de ce cache. Le registre distingue ce temps du coût total de recherche et de confirmation.

Empreinte du CSV J6 : `8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7`.
Empreinte de la baseline préservée : `faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797`.

Commandes, interfaces et limites : [docs/EXPERIMENTS.md](../docs/EXPERIMENTS.md). Choix exporté : [configs/selected_candidate.json](../configs/selected_candidate.json). Registre public agrégé : [jalon6_experiment_registry.json](jalon6_experiment_registry.json). Comparaisons internes : [JALON_6_INTERNAL.csv](JALON_6_INTERNAL.csv).

Le jalon 7 reste à faire : installation propre, reproduction exacte, accès aux poids et document final. Le CSV J6 n’écrase pas encore la soumission de référence.
