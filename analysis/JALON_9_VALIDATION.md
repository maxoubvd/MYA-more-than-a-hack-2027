# Jalon 9 — augmentation, qualité et calibration D

## Résultat et portée

Les huit variantes enregistrées ont été entraînées et évaluées : **792 comparaisons** (neuf candidats avec C0-OOF, quatre matchs, 22 conditions). Le meilleur spellF1 S41 interne est celui de **J9_QUALITY**. Le paquet C0/J7 et ses CSV sont conservés. Aucune confirmation J18 ni donnée annotée BAR–ATH ou de J03WR9 n’a été ouverte.

Ces résultats décrivent une sélection interne sur les quatre matchs DFL déjà utilisés pour le développement. Ils ne constituent pas un nouveau test aveugle et ne prédisent pas le classement du concours.

## Décision à l’issue du jalon

**Aucune variante J9 ne remplace C0 et aucune n’est retenue seule pour adoption.** J9_QUALITY gagne seulement 0.0023 de spellF1 S41, contre un minimum enregistré de +0,0100. Elle perd 0,0191 sur J03WN1, au-delà de la perte maximale autorisée de 0,0100 par match. Les autres gardes de cette variante passent. Son R4 baisse légèrement ; le rappel des possessions <2 secondes passe de 0.0679 à 0.0640.

La qualité apporte un signal utile pour D : F1 D passe de 0.8955 à 0.9095. Le diagnostic S41 situe surtout l’apport pendant les absences : parmi les images H/A où le ballon est invisible, les faux D passent de 33,17 % à 24,85 %. En contrepartie, le taux d’arrêts manqués dans ce même groupe passe de 6,43 % à 7,41 %. Lorsque le ballon est visible, les faux D augmentent de 3,65 % à 4,12 %. Sur les images H/A avec balle visible presque immobile, ils restent élevés : 36,66 % contre 36,19 %. Ces moyennes de conditions ne sont pas des fréquences d’événements indépendants.

La calibration améliore les probabilités sans améliorer les possessions : J9_QUALITY_D_PLATT abaisse la log-loss de 0.4960 à 0.4498 et l’ECE D de 0.0773 à 0.0463, mais son spellF1 reste 0.3478. Une meilleure calibration ne suffit donc pas à résoudre la fragmentation ou les frontières.

Pour J10, conserver C0 comme référence principale et tester l’imputation séparément. Les caractéristiques qualité restent disponibles comme ablation déclarée si une interaction est testée ultérieurement ; elles ne deviennent pas automatiquement le nouveau socle. Aucun réglage supplémentaire n’a été lancé après lecture de ces résultats.

## Comparaison

S41 est le spellF1 officiel moyen sur S2/S3/S6 (41 % de ballon absent), avec poids égaux des matchs, scénarios et graines. R4 pondère également les niveaux 0/20/41/60 %. Les autres colonnes ci-dessous sont calculées sur le même sous-ensemble S41.

| Candidat | spellF1 S41 | R4 | MacroF1 | F1 D | Rappel H/A <2s | Δ S41 | Gardes internes |
|---|---:|---:|---:|---:|---:|---:|---|
| C0-OOF | 0.3480 | 0.3711 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J9_AUG | 0.3475 | 0.3706 | 0.7940 | 0.9040 | 0.0623 | -0.0005 | non |
| J9_AUG_D_BAL | 0.3467 | 0.3695 | 0.7930 | 0.9045 | 0.0637 | -0.0012 | non |
| J9_AUG_D_TEMP | 0.3456 | 0.3686 | 0.7919 | 0.9009 | 0.0668 | -0.0023 | non |
| J9_AUG_D_PLATT | 0.3452 | 0.3684 | 0.7920 | 0.9014 | 0.0663 | -0.0028 | non |
| J9_QUALITY | 0.3503 | 0.3700 | 0.7977 | 0.9095 | 0.0640 | +0.0023 | non |
| J9_QUALITY_D_BAL | 0.3485 | 0.3694 | 0.7954 | 0.9081 | 0.0633 | +0.0006 | non |
| J9_QUALITY_D_PLATT | 0.3478 | 0.3679 | 0.7963 | 0.9080 | 0.0650 | -0.0001 | non |
| J9_AUG_HIER_TEMP | 0.3455 | 0.3680 | 0.7918 | 0.9005 | 0.0683 | -0.0024 | non |

Variantes passant toutes les gardes de présélection J8 : **aucune**. Ce filtrage reste interne ; seul J18 peut confirmer une adoption.

### Écarts par match

| Candidat | J03WMX | J03WN1 | J03WOH | J03WOY |
|---|---:|---:|---:|---:|
| J9_AUG | +0.0055 | -0.0138 | +0.0005 | +0.0058 |
| J9_AUG_D_BAL | +0.0045 | -0.0147 | -0.0003 | +0.0055 |
| J9_AUG_D_TEMP | +0.0047 | -0.0153 | +0.0002 | +0.0010 |
| J9_AUG_D_PLATT | +0.0042 | -0.0147 | -0.0026 | +0.0020 |
| J9_QUALITY | +0.0087 | -0.0191 | +0.0056 | +0.0139 |
| J9_QUALITY_D_BAL | +0.0075 | -0.0247 | +0.0069 | +0.0125 |
| J9_QUALITY_D_PLATT | +0.0098 | -0.0209 | +0.0017 | +0.0088 |
| J9_AUG_HIER_TEMP | +0.0048 | -0.0148 | +0.0016 | -0.0013 |

### Qualité des probabilités

| Candidat | Log-loss ↓ | Brier H/A/D ↓ | ECE D ↓ |
|---|---:|---:|---:|
| C0-OOF | 0.4960 | 0.2881 | 0.0773 |
| J9_AUG | 0.4681 | 0.2722 | 0.0757 |
| J9_AUG_D_BAL | 0.4682 | 0.2723 | 0.0752 |
| J9_AUG_D_TEMP | 0.4586 | 0.2698 | 0.0638 |
| J9_AUG_D_PLATT | 0.4587 | 0.2698 | 0.0642 |
| J9_QUALITY | 0.4585 | 0.2664 | 0.0603 |
| J9_QUALITY_D_BAL | 0.4590 | 0.2668 | 0.0599 |
| J9_QUALITY_D_PLATT | 0.4498 | 0.2636 | 0.0463 |
| J9_AUG_HIER_TEMP | 0.4583 | 0.2697 | 0.0638 |

Une baisse de log-loss, Brier ou ECE n’est pas à elle seule un motif d’adoption. La géométrie synthétique, la densité du suivi et la convention DFL diffèrent de BAR–ATH. ECE utilise dix intervalles fixes et dépend de la fréquence des classes. Les probabilités sont mesurées avant Viterbi, les métriques de possession après décodage.

## Implémentation et séparation des données

- Réapprentissage C0 selon sa recette V1 sur les trois autres matchs pour chaque pli ; aucune utilisation des poids publics ayant vu les quatre matchs.
- Augmentation V2 S0/S2/S6 ; qualité sur D seule ; perte D inversement pondérée ; calibration D température/Platt et température équipe partagée, selon les huit variantes scellées.
- Calibration en sous-plis : deux matchs apprennent, le troisième produit des probabilités hors apprentissage ; seuls les trois matchs autorisés du pli externe y participent.
- Contexte non supervisé appris sur le premier match propre autorisé ; médianes/échelles et prior temporel réappris dans chaque pli.
- Têtes H/A, décodeur et échelles temporelles fixes ; masques artificiels de corruption exclus des caractéristiques ; replis neutres conservés après calibration.
- Les 22 archives de prédictions de chaque pli sont hachées avant la mesure sur ses cibles. Les empreintes du code et des données sont revérifiées en fin de calcul.

## Preuves et limites

Les résultats détaillent frontières à 12/25 images, fragmentation, rappel des segments <1/<2/<5 secondes et diagnostics probabilistes par visibilité, immobilité/mouvement et continuité. Les tests synthétiques vérifient pondération, récupération de calibration connue, échange H/A, indépendance de D envers la proximité, balle absente, absence totale et refus des données interdites.

Les caractéristiques V1 réutilisées sont des observations sans cibles : leurs trois archives ont été comparées à un recalcul neuf sur J03WN1, toutes les valeurs étant identiques. Les nouveaux scénarios V2 sont calculés séparément. Les modèles et archives par image restent locaux.

La convention originale DFL est conservée : BallStatus=0 donne D ; BallStatus=1 avec BallPossession=1/2 donne H/A ; autre valeur donne X. Une possession inconnue ne devient pas automatiquement D. Aucun événement tiers ne complète les labels. Cette convention ne démontre pas une équivalence parfaite avec toutes les annotations du concours.

L’incertitude de projection n’a pas été testée : aucune erreur de reprojection exploitable n’est fournie dans ces entrées. La qualité ajoutée décrit disponibilité et continuité, sans corriger des coordonnées ni reconstruire un ballon caché. Le transfert entre capteurs reste simulé sur DFL ; il n’est pas validé sur une nouvelle source indépendante.

Voir [le guide](../docs/JALON_9.md), [la grille scellée](../configs/bonus_v2/j9_grid.json), [les détails numériques](../configs/bonus_v2/j9_execution.json), [le tableau CSV](JALON_9_COMPARISON.csv) et [les agrégats complets](JALON_9_RESULTS.json).

Suite : J10 teste séparément l’imputation courte et le contrôle géométrique. J18 comparera une liste fermée aux matchs de confirmation ; J19 préparera la nouvelle livraison. Aucun de ces travaux n’est déclaré réalisé ici.

## Apport isolé des leviers

Les écarts suivants utilisent les mêmes plis et conditions ; ils ne créent pas de nouvel essai.

| Levier | Référence | Δ spellF1 S41 | Δ macroF1 S41 |
|---|---|---:|---:|
| Augmentation V2 seule | C0-OOF | -0.0005 | +0.0053 |
| Qualité ajoutée seule | J9_AUG | +0.0028 | +0.0036 |
| Pondération D seule | J9_AUG | -0.0008 | -0.0010 |
| Température D | J9_AUG | -0.0019 | -0.0021 |
| Platt D | J9_AUG | -0.0023 | -0.0020 |
| Pondération D sur qualité | J9_QUALITY | -0.0017 | -0.0023 |
| Platt D sur qualité | J9_QUALITY | -0.0024 | -0.0013 |
| Température équipe en plus de D | J9_AUG_D_TEMP | -0.0001 | -0.0002 |

Les comparaisons n’opposent donc pas directement ces nombres aux 0,4280 de J7 : les matchs tenus à l’écart, les dégradations et la pondération ont changé. La bonne référence est C0-OOF dans la même table.

## Vérification finale

222 tests passent. Les 32 paquets de modèles comprennent 20 paquets externes et 12 paquets internes, soit 60 têtes logistiques distinctes après partage des têtes équipe inchangées. Tous les entraînements convergent ; gradient maximal 9.9e-07 pour une tolérance fixée à 1e-6. Les quatre références C0-OOF retrouvent les anciens coefficients appris sur trois matchs à moins de 1e-10.

Les 49 cellules précédentes du notebook sont conservées ; les deux nouvelles cellules de code ont été exécutées sur les agrégats, et les sorties du notebook partagé restent vides. Le CSV C0, la baseline J2 et le témoin de test consommé ont leurs empreintes inchangées. Voir [l’audit](JALON_9_AUDIT.json) et [le diagnostic par visibilité/qualité](JALON_9_STRATA.json).

Coût total phase enregistré : 1.237 heures CPU, 0 seconde GPU. Ce total inclut les tâches J8 et J9 comptabilisées, les sous-plis et les calculs de diagnostic ; ce n’est pas une durée murale. Huit configurations nouvelles sur 48 sont engagées.

Le diagnostic décodé est reproductible avec [scripts/j9_diagnostics.py](../scripts/j9_diagnostics.py) après la grille complète ; son empreinte et les 1 944 agrégats de conditions sont enregistrés.
