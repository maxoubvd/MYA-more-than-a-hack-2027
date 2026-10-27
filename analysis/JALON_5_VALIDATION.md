# Jalon 5 — décodage temporel exact et frontières

Réalisation et mesures du **27 octobre 2026**. Les deux Viterbi réduisent fortement
la fragmentation du modèle J4 et dépassent la baseline sur les deux matchs externes
de validation, en moyenne des conditions figées. Le statique obtient ici un
spellF1 légèrement supérieur au dynamique. Le rappel des possessions courtes reste
faible et inférieur à celui du modèle brut : ce point reste à améliorer.

Aucun paramètre n’est réajusté après ces mesures. La candidate dynamique était
désignée avant les essais ; elle est exportée dans un CSV distinct. La baseline
n’est pas remplacée. Aucun score privé BAR-ATH n’est connu et aucun nouveau
diagnostic public n’est exécuté dans ce jalon.

## Livrables

- Viterbi max-somme exact, coûts constants ou variables dans le temps, preuve par
  comparaison à des chemins exhaustifs sur fixtures synthétiques.
- A priori de transitions estimé uniquement sur J03WMX, J03WN1, J03WOH et J03WOY,
  avec H/A regroupés symétriquement, pseudo-compte 0,5 et état initial uniforme.
- Coûts dynamiques souples : contexte de contrôle et contacts candidats pour H/A ;
  indices physiques séparés de l’équipe pour les transitions impliquant D.
- Réinitialisation par période, inconnus explicites et contraintes officielles
  intégrées à l’optimisation. Aucune durée minimale ni suppression après coup.
- Marges max-somme et profils conditionnels d’incertitude de datation des frontières.
  Ce ne sont pas des probabilités de justesse ou des intervalles statistiques.
- **160 tests réussis**, dont 37 nouveaux, commandes, cache de quatre indices
  physiques, documentation et trois cellules de notebook supplémentaires.

Voir [les conventions et la reproduction](../docs/SEQUENTIAL_DECODING.md).

## Protocole

Les classifieurs du jalon 4 sont figés et ne sont pas réentraînés. Les paramètres
temporels proviennent des paires de labels adjacents des quatre matchs externes
d’apprentissage. Inconnus et mi-temps interrompent le comptage. Les coûts de base
sont les opposés des logarithmes des probabilités de transition apprises.

Les deux matchs de validation sont J03WPY et J03WQQ. Chaque match est évalué dans
les 19 couples scénario/graine déjà fixés : propre, trous courts/longs, bruit,
trous denses, fragmentation et combinaison. Les quatre méthodes produisent
**152 comparaisons** avec la révision officielle épinglée du scoreur.

Avant la mesure, les probabilités J4 et la baseline sont reproduites à partir
des observations dégradées, puis les deux séquences décodées sont figées. Les
cibles du match de validation sont ouvertes ensuite uniquement pour le score.
La réunion des rapports vérifie le code, le modèle, les réglages et la couverture.
Les 19 scénarios ne constituent pas 19 matchs indépendants.

La configuration est [sequential.json](../configs/sequential.json) : deux versions
prédéfinies, aucun balayage d’hyperparamètres, aucun réglage sur les résultats
publics et aucun accès au dernier match J03WR9.

## Résultats moyens sur les 19 conditions de chaque match

| Match | Méthode | spellF1 moyen | macroF1 moyen | Segments H/A/D moyens |
|---|---|---:|---:|---:|
| J03WPY | baseline | 0.2401 | 0.4072 | 608.2 |
| J03WPY | raw_logistic | 0.1098 | 0.8160 | 4815.1 |
| J03WPY | static | 0.4052 | 0.8283 | 440.5 |
| J03WPY | dynamic | 0.3990 | 0.8279 | 457.0 |
| J03WQQ | baseline | 0.2752 | 0.4275 | 621.3 |
| J03WQQ | raw_logistic | 0.1001 | 0.8184 | 5416.7 |
| J03WQQ | static | 0.4222 | 0.8335 | 479.4 |
| J03WQQ | dynamic | 0.4136 | 0.8329 | 498.6 |

Les segments incluent D ; spellF1 porte sur les possessions H/A. Le gain de
continuité s’accompagne ici d’un léger gain de macroF1. Aucun objectif de nombre
de segments n’a été fixé : les différences ci-dessus sont mesurées après coup.

### Données propres uniquement

| Match | Méthode | spellF1 | macroF1 | Segments prédits / référence |
|---|---|---:|---:|---:|
| J03WPY | baseline | 0.3171 | 0.3954 | 375 / 518 |
| J03WPY | raw_logistic | 0.1610 | 0.8846 | 2184 / 518 |
| J03WPY | static | 0.4742 | 0.8957 | 418 / 518 |
| J03WPY | dynamic | 0.4605 | 0.8952 | 440 / 518 |
| J03WQQ | baseline | 0.3608 | 0.4162 | 406 / 500 |
| J03WQQ | raw_logistic | 0.1421 | 0.8872 | 2561 / 500 |
| J03WQQ | static | 0.5166 | 0.9030 | 460 / 500 |
| J03WQQ | dynamic | 0.5029 | 0.9021 | 479 / 500 |

## Frontières et possessions courtes

Le diagnostic court utilise les segments de référence de moins de deux secondes
et l’appariement officiel un à un à IoU 0,5. Ce seuil descriptif ne filtre aucune
prédiction. Les frontières sont aussi évaluées par le scoreur officiel à ±25 images,
soit une seconde ; les autres tolérances et latences restent dans le rapport local.

| Match | Méthode | Rappel moyen des possessions courtes | F1 moyen des frontières à ±25 images |
|---|---|---:|---:|
| J03WPY | baseline | 1.49 % | 0.1900 |
| J03WPY | raw_logistic | 13.29 % | 0.2052 |
| J03WPY | static | 4.92 % | 0.4511 |
| J03WPY | dynamic | 5.18 % | 0.4506 |
| J03WQQ | baseline | 2.81 % | 0.1871 |
| J03WQQ | raw_logistic | 14.59 % | 0.1782 |
| J03WQQ | static | 5.47 % | 0.4526 |
| J03WQQ | dynamic | 5.37 % | 0.4498 |

**Limite importante :** le décodeur conserve moins de vraies possessions courtes
que le modèle brut, malgré l’absence de durée minimale. En données propres, le
modèle brut récupère 23/124 et 18/101 possessions courtes ; les deux Viterbi en
récupèrent 7/124 et 7/101. Ils en récupèrent davantage que la baseline, mais cela
reste insuffisant pour considérer le problème résolu. Une pénalité souple peut
encore supprimer un segment réel si son évidence n’est pas assez forte.

Les tests prouvent qu’une récupération ou un arrêt d’une image peut survivre avec
une évidence forte. Ils ne prouvent pas que les observations réelles donnent cette
évidence aux bons endroits. La calibration des potentiels, les pénalités et les
indices de contrôle restent des pistes à comparer au jalon 6, avec protocole interne
sur les quatre matchs d’apprentissage et budget déclaré avant les nouveaux essais.

Le dynamique produit un peu plus de segments que le statique et ne gagne pas
spellF1 sur ces deux matchs. Son bénéfice n’est donc pas démontré ici. Les deux
versions et leurs limites sont conservées sans changement rétroactif de configuration.

## Tactique et format de sortie

Les scores J4 déjà figés sont décodés sur les 199 319 images. X reste hors périodes
évaluées. La zone D publiée avant la reprise de deuxième mi-temps est une contrainte
interne au décodage, sans correction ajoutée après le choix des frontières. Les
positions manquantes ne sont jamais remplies. Aucune annotation publique BAR-ATH
n’est lue pour cette génération.

Les deux archives séquentielles sont relues et comparées après sauvegarde. Le fichier
**`submissions/MYA_jalon5.csv`**, issu de la version dynamique prédéfinie, est accepté
par le validateur officiel : 199 319 lignes et alphabet H/A/D/X. Ce succès valide
le format uniquement. Il n’est pas une mesure de précision privée.

Empreinte de la candidate : `9a7bc3697631313f16554ddca1c3fe6dca39ece5a66fdea7a2f9de631a3d877f`.

La référence `submissions/MYA.csv` reste inchangée :
`faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797`.

## Vérifications et notebook

- 160 tests automatisés réussis : chemins exhaustifs, coûts variables, marges,
  égalités, contraintes D, priors symétriques, inconnus, périodes, déviations,
  récupérations et arrêts très courts, signatures et séparation des usages.
- Vérification synthétique avec le scoreur officiel : séparation des mi-temps,
  rappel exact des courts segments et sérialisation du rapport.
- Jalons antérieurs revérifiés : matrices complètes J3, 19 scénarios fonctionnels
  et invariance, sans changement du descripteur externe ni des poids J4.
- Notebook exécuté avec **40 cellules dont 26 de code** : les 37 cellules
  précédentes sont conservées ; trois cellules ajoutent le décodage. Exploration
  historique et repli en absence d’artefacts restent disponibles.
- Diagnostic public désactivé pendant cette exécution ; tables publiques non
  chargées. Sorties détaillées dans le cache local, notebook partagé sans sorties.
- Dépendances cohérentes, contrôle de publication réussi. Modèles ajustés, tableaux
  par image, profils, caches et CSV restent exclus de Git.

## Suite

Le jalon 6 pourra comparer les choix de calibration et de pénalités, les ablations
et la conservation des frontières courtes. Le statique constitue ici la meilleure
des deux variantes temporelles mesurées, sans garantir un gain sur le match du
concours. Les deux matchs de validation ne remplacent ni le test final verrouillé
ni une vérification de transfert entre conventions de possession des fournisseurs.
