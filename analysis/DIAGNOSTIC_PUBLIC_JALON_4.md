# Diagnostic public du modèle figé du jalon 4

Exécution du 27 octobre 2026, à la demande de l'équipe. Diagnostic unique sur les
**7 500 images des cinq minutes publiques BAR-ATH**, avec le scoreur officiel
épinglé. Aucun entraînement, calibration, recherche de seuil, lissage ajouté ou
choix de variante à partir de ces résultats.

Le modèle, son archive de scores et les trois CSV d'entrée ont été vérifiés et
figés par empreintes avant l'ouverture des labels par le scoreur. La décision
du modèle reste celle existante : maximum unique des scores H/A/D par image,
abstention X en cas d'égalité. Aucun décodage temporel n'est appliqué.

| Méthode | spellF1, critère principal | macroF1 | Exactitude par image | Segments H/A/D prédits |
|---|---:|---:|---:|---:|
| MYA jalon 2 | 0,325581 | 0,620733 | 71,32 % | 30 |
| Baseline officielle smooth50 | 0,325581 | 0,620733 | 71,32 % | 30 |
| Modèle logistique jalon 4, sans décodage | 0,133333 | 0,714906 | 76,60 % | 113 |

La référence publique contient 21 segments H/A/D, dont 17 possessions H/A.
Aucune méthode ne s'abstient dans les 7 500 images évaluées.

| Classe | F1 de la baseline | F1 du modèle |
|---|---:|---:|
| H | 0,778147 | 0,854382 |
| A | 0,761505 | 0,735329 |
| D | 0,322548 | 0,555008 |

Le modèle améliore macroF1 et l'exactitude par image, mais reste inférieur sur
spellF1. Ses 113 segments montrent une fragmentation excessive. Ce problème
avait déjà été mesuré sur les deux matchs externes de validation, avant ce
diagnostic public, et motivait déjà le jalon 5.

Ces cinq minutes ne permettent ni de connaître la performance privée sur le
match complet, ni de régler ou de sélectionner une méthode. Les choix futurs
restent fondés sur les données externes autorisées. Le modèle et le CSV de
référence sont inchangés après l'évaluation.

Les empreintes, le rapport officiel et les sorties par image restent locaux
dans `.cache/observations/public_diagnostic/`. Seuls les agrégats ci-dessus sont
présentés dans ce document. La baseline officielle publiée est reproduite aux
quatre décimales attendues.
