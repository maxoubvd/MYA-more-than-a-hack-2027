# Jalon 4 — scores d’observation et apprentissage externe

Réalisation et mesures du **27 octobre 2026**. Trois scores H/A/D sont disponibles
pour chaque image tactique évaluée, avec supports, source d’évidence et confiance.
Le CSV de référence reste inchangé ; aucune nouvelle méthode n’est adoptée automatiquement.
Le décodage temporel du jalon 5 reste à réaliser.

Le modèle améliore nettement macroF1 sur les deux matchs de validation, mais reste
inférieur à la baseline sur **spellF1, le critère principal du concours**. En données
propres, il produit 1 683 segments pour 421 vrais sur J03WPY et 1 879 pour 401 sur
J03WQQ. Ces observations motivent la comparaison d'un décodage temporel au jalon 5 ;
elles ne garantissent pas que ce décodage suffira à dépasser la référence.

## Livraison

- `rules` : score physique vivant/mort indépendant de l’attribution d’équipe,
  puis score H/A issu des proximités et du contexte tactique automatique.
- `rules_hold` : même référence, avec maintien candidat de la dernière équipe,
  décroissance exponentielle de deux secondes et réinitialisation par période.
- `logistic` : trois régressions logistiques L2 sur données externes, pour D,
  l’équipe avec ballon visible et l’équipe par le collectif lorsque la géométrie manque.
- Trois archives tactiques de **199 319 × 3**, ordre H/A/D, valeurs masquées hors
  périodes évaluées, supports et indicateurs de confiance ; aucune position imputée.
- Commandes, notebook, plan, configuration figée et documentation des interfaces.

Voir [les conventions et la reproduction](../docs/OBSERVATION_SCORES.md).

## Apprentissage et séparation des usages

Les quatre matchs d’apprentissage sont J03WMX, J03WN1, J03WOH et J03WOY.
Chacun est traité en données propres, absences longues et dégradation combinée,
avec une graine fixée. Au plus 12 000 lignes par match/scénario sont retenues,
sans séparation aléatoire d’images entre entraînement et validation.

| Tête | Entrées | Lignes d’apprentissage | Itérations | Gradient maximal final |
|---|---:|---:|---:|---:|
| D / vivant | 21 | 144 000 | 7 | 5.14e-07 |
| H / A avec géométrie | 22 | 56 023 | 6 | 8.45e-08 |
| H / A par le collectif | 11 | 76 581 | 5 | 3.47e-07 |

Les trois optimisations ont convergé au seuil fixé de 1e-6. Médianes et échelles
sont estimées sur les seules lignes d’apprentissage. Les têtes d’équipe restent
symétriques lors de l’échange H/A. La tête d’état ne reçoit ni proximité joueur–ballon,
ni noyau de contrôle, ni tag d’équipe. Un seul réglage L2 est testé, sans recherche
de paramètres ni calibration sur les matchs de validation. Les probabilités sont
des estimations **non calibrées**.

Les deux descripteurs non supervisés du jalon 3 restent inchangés et ajustés sur
les seules observations de J03WMX. Aucun label public BAR-ATH, pseudo-label BAR-ATH
ou annotation humaine du match fourni n’est utilisé. Le match de test J03WR9
n’a été ni téléchargé ni ouvert.

## Comparaison sur deux matchs réservés à la validation

J03WPY et J03WQQ restent totalement hors apprentissage. Chaque match complet est
traité dans les 19 couples scénario/graine figés. Les prédictions des quatre
références sont sauvegardées avant l’ouverture de ses cibles. Cela donne
**152 comparaisons** avec le scoreur officiel épinglé, mi-temps séparées.

La baseline utilise déjà son vote à ±50 images. Les scores du jalon 4 sont ici
évalués image par image, sans lissage ni décodeur. La comparaison mesure donc
aussi la fragmentation que devra traiter le jalon 5.

### Données propres

| Match | Méthode | spellF1 | macroF1 |
|---|---|---:|---:|
| J03WPY | baseline | 0.3171 | 0.3954 |
| J03WPY | rules | 0.1150 | 0.8272 |
| J03WPY | rules_hold | 0.1150 | 0.8272 |
| J03WPY | logistic | 0.1610 | 0.8846 |
| J03WQQ | baseline | 0.3608 | 0.4162 |
| J03WQQ | rules | 0.0939 | 0.8099 |
| J03WQQ | rules_hold | 0.0939 | 0.8099 |
| J03WQQ | logistic | 0.1421 | 0.8872 |

### Moyenne des 19 conditions par match

Chaque couple scénario/graine a le même poids. Il ne s’agit ni d’un score sur
les labels privés du concours ni d’un intervalle de confiance statistique.

| Match | Méthode | spellF1 moyen | macroF1 moyen | Brier multiclasse moyen |
|---|---|---:|---:|---:|
| J03WPY | baseline | 0.2401 | 0.4072 | — |
| J03WPY | rules | 0.0910 | 0.6362 | 0.4460 |
| J03WPY | rules_hold | 0.0910 | 0.6744 | 0.4354 |
| J03WPY | logistic | 0.1098 | 0.8160 | 0.2251 |
| J03WQQ | baseline | 0.2752 | 0.4275 | — |
| J03WQQ | rules | 0.0799 | 0.5990 | 0.4777 |
| J03WQQ | rules_hold | 0.0799 | 0.6358 | 0.4669 |
| J03WQQ | logistic | 0.1001 | 0.8184 | 0.2438 |

Brier est la moyenne de la somme des erreurs quadratiques H/A/D ; plus bas
est meilleur. Log-loss, Brier D et Brier conditionnel H/A, résultats par classe
et nombres de segments figurent dans le rapport local détaillé.

- J03WPY : modèle logistique moins baseline, en moyenne des 19 conditions : spellF1 -0.1304, macroF1 +0.4088.
- J03WQQ : modèle logistique moins baseline, en moyenne des 19 conditions : spellF1 -0.1751, macroF1 +0.3909.

Ces mesures ne déclenchent aucun remplacement automatique de la référence.
Le décodage temporel, la robustesse au changement de fournisseur et les conventions
de possession doivent encore être comparés avant une adoption. Deux matchs ne
garantissent pas un gain sur BAR-ATH ni une victoire au concours.

## Preuves de fonctionnement

- **123 tests réussis**, dont 30 tests ajoutés pour le jalon 4 : séparation de
  l’état et du contrôle, absence totale, incohérences de probabilité, maintien
  décroissant et contradictoire, symétrie H/A, convergence logistique, prétraitement
  hors validation, alignement des cibles, rôles des matchs et signatures d’archives.
- Une absence connue ne compte pas comme un support physique. Sans aucun contexte
  physique ni équipe observable, le modèle revient à H/A/D uniformes, confiance
  nulle et abstention du diagnostic image par image, même avec un prior appris fort.
- Jalons antérieurs revérifiés : matrices complètes du jalon 3 et 19 scénarios
  fonctionnels, masques et invariance aux permutations ; descripteur externe inchangé.
- Scores tactiques complets construits puis relus, factorisation et somme à un
  vérifiées, NaN hors périodes évaluées. La zone D connue n’est pas forcée dans
  ces scores d’observation ; elle appartient aux contraintes d’export.
- Notebook exécuté : **10 cellules de code** ; sorties partagées et compteurs vides.
  L'exploration historique a ensuite été réintégrée : le notebook courant compte
  **24 cellules de code**, toutes réexécutées en modes normal et diagnostic complet.
  Voir [la restauration et ses vérifications](RESTAURATION_NOTEBOOK.md).
- Dépendances cohérentes et contrôle de publication réussi. Les matrices, modèles
  ajustés, données externes, prédictions et sorties détaillées restent sous `.cache/`.
- Soumission de référence inchangée, SHA-256 :
  `faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797`.

## Suite

Le jalon 5 pourra combiner ces scores avec mémoire et pénalités de transition
sur chaque période. Il faudra conserver les vraies possessions courtes, traiter
les frontières incertaines et comparer le décodage à la baseline sur les matchs
externes. Le modèle collectif et la mémoire restent des hypothèses mesurées,
sans pureté d’ancres ni précision privée présumée.
