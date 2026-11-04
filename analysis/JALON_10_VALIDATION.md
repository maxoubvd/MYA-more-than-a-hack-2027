# Jalon 10 — imputation courte et contrôle géométrique

**Réalisé le 3 novembre 2026.** Huit configurations enregistrées avant apprentissage, quatre plis de match, 22 conditions par pli : 792 comparaisons avec C0. Aucune annotation BAR–ATH, donnée de confirmation ou cible J03WR9 n’a été ouverte.

Le meilleur spellF1 S41 interne est celui de **J10_LINEAR_25_CONTROL**. Variantes passant toutes les gardes J8 : **aucune**. C0 reste la livraison actuelle ; une adoption demanderait toujours J18/J19.

## Décision et interprétation

**Aucune variante J10 ne remplace C0.** Le meilleur gain S41 est +0.000203, contre le minimum préenregistré de +0,010000. La variante LINEAR 25 + CONTROL respecte les six autres gardes ; le gain principal est simplement trop faible. C0 reste la version à soumettre.

L’imputation courte apporte un bénéfice ciblé : dans S1, le spellF1 moyen passe de 0.4078 à 0.4273 avec LINEAR 25, ou 0.4276 avec son contrôle potentiel. Le R4 de cette dernière passe de 0.3711 à 0.3760. En revanche, les mêmes reconstructions ne couvrent que **0.0556 % des coordonnées retirées dans S41** (1163 sur 2093256). Elles ne peuvent donc pas résoudre les longues occultations visées par le benchmark principal.

Le Kalman fixé ici n’améliore pas l’interpolation : pour la limite de 25 images et les mêmes points reconstruits, le RMSE regroupé est 0.993 m contre 0.957 m, et son spellF1 S1 est 0.4268 contre 0.4273. Aucun autre réglage du filtre n’a été essayé après ce constat.

Le contrôle potentiel seul modifie peu les résultats : spellF1 S41 0.3481 contre 0.3480. L’ajout géométrique à une tête déjà riche en distances et mouvement n’apporte pas ici de gain suffisant. Cela ne teste pas un modèle complet de contrôle du terrain ou une reconstruction des longs trous.

La couche LINEAR 25 reste disponible comme ablation pour les trous courts, sans empilement automatique dans la soumission. La suite prévue au J11 est l’étude des durées et du décodage ; elle n’est pas réalisée dans ce jalon.

## Comparaison de possession

S41 est le spellF1 officiel sur S2/S3/S6 à 41 % de ballon absent ; graines, scénarios et matchs sont pondérés comme au J8. R4 équilibre les niveaux 0/20/41/60 %. Les autres colonnes ci-dessous portent aussi sur S41.

| Candidat | spellF1 S41 | R4 | MacroF1 | F1 D | Rappel H/A <2s | Δ S41 | Gardes |
|---|---:|---:|---:|---:|---:|---:|---|
| C0-OOF | 0.3480 | 0.3711 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_LINEAR_5 | 0.3480 | 0.3711 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_LINEAR_10 | 0.3480 | 0.3715 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_LINEAR_25 | 0.3480 | 0.3760 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_KALMAN_5 | 0.3480 | 0.3711 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_KALMAN_10 | 0.3480 | 0.3715 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_KALMAN_25 | 0.3480 | 0.3758 | 0.7887 | 0.8955 | 0.0679 | +0.0000 | non |
| J10_CONTROL | 0.3481 | 0.3710 | 0.7888 | 0.8955 | 0.0685 | +0.0002 | non |
| J10_LINEAR_25_CONTROL | 0.3482 | 0.3760 | 0.7888 | 0.8955 | 0.0685 | +0.0002 | non |

La référence C0 est **strictement la même que dans J9**, y compris les prédictions des 88 conditions. Ces scores ne se comparent pas directement au 0,4280 historique de J7, obtenu avec d’autres matchs/conditions et une autre pondération.

### Écarts de spellF1 S41 par match

| Candidat | J03WMX | J03WN1 | J03WOH | J03WOY |
|---|---:|---:|---:|---:|
| J10_LINEAR_5 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| J10_LINEAR_10 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| J10_LINEAR_25 | +0.0001 | +0.0000 | +0.0000 | +0.0000 |
| J10_KALMAN_5 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| J10_KALMAN_10 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| J10_KALMAN_25 | +0.0001 | +0.0000 | +0.0000 | +0.0000 |
| J10_CONTROL | +0.0002 | +0.0003 | +0.0012 | -0.0010 |
| J10_LINEAR_25_CONTROL | +0.0003 | +0.0003 | +0.0012 | -0.0010 |

## Reconstruction du ballon

Les erreurs sont des écarts aux coordonnées DFL retirées par le générateur, pas à une mesure physique indépendante. Les volumes ci-dessous comptent des images × conditions ; les graines ne sont pas des matchs supplémentaires. Le RMSE est regroupé par nombre de points reconstruits, tandis que la sélection de possession conserve les poids égaux du protocole.

| Méthode | Points cachés reconstruits, toutes conditions | Part du ballon retiré | RMSE (m) | Part reconstruite dans S1 | Points reconstruits S41 |
|---|---:|---:|---:|---:|---:|
| J10_LINEAR_5 | 4243 | 0.095 % | 0.141 | 1.24 % | 17 |
| J10_LINEAR_10 | 37900 | 0.847 % | 0.310 | 11.12 % | 36 |
| J10_LINEAR_25 | 267070 | 5.967 % | 0.957 | 78.05 % | 1163 |
| J10_KALMAN_5 | 4243 | 0.095 % | 0.176 | 1.24 % | 17 |
| J10_KALMAN_10 | 37900 | 0.847 % | 0.344 | 11.12 % | 36 |
| J10_KALMAN_25 | 267070 | 5.967 % | 0.993 | 78.05 % | 1163 |
| J10_LINEAR_25_CONTROL | 267070 | 5.967 % | 0.957 | 78.05 % | 1163 |

Les limites 5/10/25 images concernent 0,2/0,4/1 seconde de points manquants à 25 Hz. Deux observations de chaque côté, dans une même période, sont obligatoires. Les longues absences ne sont pas extrapolées. Le filtre à vitesse constante et l’interpolation partagent les mêmes limites et règles de rejet.

L’incertitude reste un proxy fixé d’avance. La couverture à deux sigma et les erreurs par durées 1–5 / 6–10 / 11–25 images sont publiées dans les agrégats complets ; elles ne donnent pas une garantie de couverture statistique.

## Ce qui change dans le modèle

- Les six variantes d’imputation réutilisent les trois têtes C0 et son prior. La géométrie des points imputés modifie seulement H/A, avec une confiance décroissante selon l’incertitude.
- CONTROL ajoute un indice local de temps d’arrivée à la tête visible, réapprise sur les trois matchs autorisés avec les mêmes lignes V1 que C0. La variante combinée ajoute cette même tête à LINEAR 25, fixé avant résultats.
- Le contrôle utilise les joueurs anonymes observés ; un doublon exact ne renforce pas son minimum d’arrivée. Une vitesse absente donne un calcul de position seule. Ce n’est pas un champ de contrôle sur tout le terrain.
- Les probabilités D restent identiques à C0 dans les huit variantes. Le décodage conjoint peut toutefois déplacer une frontière D lorsque H/A change ; la matrice temporelle reste fixe.
- Les positions observées, les reconstructions, leur âge et leur incertitude restent distincts. Les masques de corruption et coordonnées masquées n’entrent jamais dans les caractéristiques.

## Preuves et limites

239 tests passent : trajectoire rectiligne, accélération, trou trop long ou censuré, borne absente, période, point aberrant, joueur manquant, doublon, symétrie H/A et invariance du score D. Les caractéristiques H/A reconstruites reproduisent exactement le constructeur gelé sur fixture. Les archives réelles vérifient le rejeu exact de C0 avant toute comparaison.

Les quatre têtes de contrôle sont apprises hors match évalué ; le contexte, les trois têtes et les priors C0 réutilisés ont la même séparation. Les prédictions de toutes les conditions d’un pli sont hachées avant l’ouverture de ses cibles pour la mesure. Les sorties par image restent privées dans le cache.

Ces essais ne reconstruisent pas les joueurs, ne réparent pas toutes les erreurs de projection et ne traitent pas les longues occultations de BAR–ATH. Les trajectoires DFL masquées et dégradations synthétiques ne démontrent pas un transfert réel sur un nouveau capteur. Aucun réglage n’a été ajouté après lecture des scores.

Voir [le guide](../docs/JALON_10.md), [la grille](../configs/bonus_v2/j10_grid.json), [les règles numériques](../configs/bonus_v2/j10_execution.json), [le tableau CSV](JALON_10_COMPARISON.csv) et [les résultats complets](JALON_10_RESULTS.json).

## Vérification finale

Les 528 couches de reconstruction archivées respectent les limites, périodes, masques et incertitudes. Les 88 rejouages C0 sont exacts et ses scores D restent identiques dans toutes les variantes. Les configurations sans mise à jour partagent leurs prédictions : 382 décodages distincts ont suffi pour les 792 lignes de comparaison. Il ne s’agit pas de 792 échantillons indépendants.

Les 52 cellules précédentes du notebook sont conservées ; les deux nouvelles cellules de code ont été exécutées sur les agrégats. Les sorties partagées sont vides. Les CSV J2/C0 et le témoin de test consommé sont inchangés. Voir [l’audit](JALON_10_AUDIT.json).

Coût total de phase enregistré : 1.639 heures CPU, 0 seconde GPU. Ce total comprend J8/J9/J10 et le travail de sous-plis antérieur, pas uniquement J10 ; ce n’est pas une durée murale. Seize configurations sur 48 sont engagées.
