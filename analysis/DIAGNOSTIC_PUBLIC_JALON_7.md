# Bilan des gains J6 et diagnostic public du modèle J7

Diagnostic demandé le 2 novembre 2026. Les cinq CSV sont figés avant l’ouverture des labels par le scoreur officiel. Aucun entraînement, calibration, seuil, lissage, réglage ou choix de variante ne suit ces mesures.

## Apport propre du jalon 6 sur la validation externe

Moyennes des deux matchs J03WPY/J03WQQ, chacun dans les 19 conditions/graine déjà définies. Les deux matchs ont le même poids. Ces 38 conditions ne représentent pas 38 matchs indépendants. Les réglages J6 ont été choisis en interne entre les quatre matchs d’apprentissage, puis confirmés sur ces deux matchs déjà examinés aux jalons précédents.

| Méthode | macroF1 | spellF1 |
|---|---:|---:|
| baseline | 0.417340 | 0.257670 |
| j5_dynamic | 0.830410 | 0.406300 |
| j5_static | 0.830878 | 0.413704 |
| selected | 0.834042 | 0.428010 |

| Référence | Gain macroF1, points sur 100 | Gain spellF1, points sur 100 | Gain relatif spellF1 |
|---|---:|---:|---:|
| j5_static → J6 | +0.316 | +1.431 | +3.46 % |
| j5_dynamic → J6 | +0.363 | +2.171 | +5.34 % |

Le gain propre du J6 est réel sur ce banc, mais incrémental. Le saut majeur venait du décodage J5 face aux observations J4 fragmentées. Le J6 a surtout validé les composants et retenu le modèle complet avec coûts statiques H/A=1 et D=2. Le rappel court moyen y baisse légèrement : 0.0520 → 0.0503. Ce problème n’est pas résolu.

Le jalon 7 n’introduit pas un nouveau modèle : il emballe et reproduit la candidate J6. Le test final externe J03WR9 a été ouvert après gel ; son spellF1 0,406352 et son macroF1 0,828810 sont ceux de cette candidate, sans comparaison de réglages supplémentaires sur ce match.

## Cinq minutes publiques BAR–ATH

Le scoreur officiel à la révision `f8f2629ff1e0985f81d7e59d8413678514ee1530` mesure les 7 500 images annotées publiques. La référence possède **17 possessions H/A**, **21 segments H/A/D**. Les méthodes comparées existaient avant ce diagnostic : baseline officielle ±50, sortie brute J4, deux séquences J5 figées et CSV final J7. Les probabilités, poids, transitions et fichiers de soumission sont inchangés.

| Méthode | macroF1 | spellF1 | Exactitude image | Segments H/A/D prédits | Possessions H/A prédites |
|---|---:|---:|---:|---:|---:|
| baseline_smooth50 | 0.620733 | 0.325581 | 71.32 % | 30 | 26 |
| MYA_j4 | 0.714906 | 0.133333 | 76.60 % | 113 | 85 |
| MYA_j5_static | 0.720217 | 0.419512 | 77.53 % | 31 | 24 |
| MYA_j5_dynamic | 0.719507 | 0.419512 | 77.49 % | 31 | 24 |
| MYA_j7 | 0.706180 | 0.410000 | 76.77 % | 29 | 23 |

| Classe | F1 baseline | F1 J7 |
|---|---:|---:|
| H | 0.778147 | 0.860249 |
| A | 0.761505 | 0.744500 |
| D | 0.322548 | 0.513793 |

Pour J7 : précision D **70.04 %**, rappel D **40.57 %**. Environ 59.4 % des images réellement D ne sont donc pas reconnues comme D. Cela décrit ce diagnostic, pas une mesure sur le match privé complet.

J7 bat la baseline sur les deux critères, mais reste légèrement inférieur aux séquences J5 sur cette fenêtre. Face au J5 statique, la différence est -1.404 points de macroF1 et -0.951 points de spellF1. Les coûts D doublés ne donnent pas le même bénéfice ici que sur la validation externe. Ce constat ne justifie pas de sélectionner J5 sur ces cinq minutes.

## Jugement et incertitude

Le modèle est un socle cohérent et reproductible, avec un progrès constaté sur la baseline. Le décodage réduit fortement la fragmentation J4 (113 segments → 29) ; il reste toutefois 23 possessions prédites contre 17 réelles, et D est insuffisamment rappelé. L’amélioration n’est pas uniforme : le F1 de A reste inférieur à la baseline sur cette fenêtre.

La fenêtre contient peu de possessions. Le bootstrap officiel à 1 000 tirages donne pour J7 un intervalle spellF1 [0.270, 0.550] et macroF1 [0.543, 0.808]. Ce ne sont pas des intervalles du gain apparié entre méthodes ; leur chevauchement ne constitue pas un test statistique de cette différence. Ces cinq minutes ne permettent pas une projection fiable vers le score privé complet ni un classement au concours.

Le contraste DFL/BAR–ATH est compatible avec un écart de capteurs, de conventions des labels ou de situations représentées ; ce diagnostic court ne permet pas d’attribuer définitivement la cause. Les éventuels travaux futurs doivent être décidés et évalués sur des données externes autorisées, pas en réglant les coûts sur cette fenêtre publique. Le test J03WR9 est déjà consommé et ne constitue plus un test vierge pour une nouvelle sélection.

## Traçabilité

- CSV J7 SHA256 : `8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7`.
- Modèle SHA256 canonique : `6ccb2be478590bcd3a6d032d22411b500825471979137c72b735d1ba95781e3f`.
- Gel de livraison SHA256 canonique : `de3b48c2b6879e1565f3d498652f44d2c8fe2be1d4ea058f23621183c0d78dfd`.
- Entrées figées, journal officiel, rapports détaillés et bootstrap conservés localement sous `.cache/delivery/public-diagnostic-j7-20261102/`.
- Aucun CSV par image ni annotation du match n’est ajouté au dépôt. Le présent fichier ne contient que des agrégats.
- Le document de soumission et le paquet figé ne sont pas modifiés à partir de ce diagnostic.

## Disponibilité des coordonnées du ballon : complément mesuré

Les sept archives DFL natives, dont celle du test final déjà consommé, fournissent des x/y finis pour le ballon à toutes leurs images : **0 % de coordonnées manquantes**. Il s’agit d’une mesure de disponibilité du tracking, pas d’une inspection visuelle des vidéos. Aucune cible ni nouvelle prédiction n’est nécessaire à ce constat.

| Source ou condition | Coordonnées de ballon manquantes |
|---|---:|
| DFL natif, chacun des sept matchs | 0 % |
| DFL, trous courts synthétiques | ≈20 % |
| DFL, trous longs / trous liés à la densité / combiné | ≈41 % |
| DFL, bruit spatial seul / fragmentation des joueurs seule | 0 % |
| BAR–ATH tactique, périodes évaluées | 40,693 % |
| BAR–ATH tactique, vidéo entière | 43,062 % |
| BAR–ATH tactique, cinq minutes publiques | 11,800 % |

L’apprentissage utilisait clean, long_gaps et combined : il ne recevait donc pas uniquement un ballon toujours disponible. La moyenne macroF1 DFL 0,834 mélange plusieurs niveaux de disponibilité ; ce n’est pas un résultat mesuré uniquement à 41 % de masquage.

Le diagnostic public BAR–ATH porte sur une fenêtre avec seulement 11,8 % de coordonnées manquantes. La baisse de macroF1 ne peut donc pas être expliquée par le simple argument « 40 % d’absences sur les cinq minutes ». Le rôle des erreurs de coordonnées, des types de phases et des conventions de D reste à isoler. À fraction manquante égale, la durée, le placement et les causes des trous peuvent être différents.
