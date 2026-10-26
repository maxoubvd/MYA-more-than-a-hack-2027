# Préparation avant le jalon 3 — cinq étapes réalisées

Date : 26 octobre 2026. Cette préparation complète les jalons 0–2 et ne déclare
pas les caractéristiques, modèles ou décodeurs du jalon 3 implémentés. Le code,
les protocoles et les tests sont versionnés. Les données, archives préparées,
prédictions et rapports détaillés restent locaux et ignorés par Git.

## 1. Hypothèses du plan corrigées

Le plan ne prescrit plus une durée universelle de D ≥ 2 s, une suppression des
possessions adverses de moins de 2–3 s ou une datation des contacts à l’image près.
Il n’impose plus une cible de 45–52 % de D. Un ballon absent reste une observation
incertaine : ni mort ni vivant automatiquement. Le maintien de l’équipe précédente
doit perdre en confiance et pouvoir être contredit. Le pitch control reste un
bonus à valider ; l’optimalité Viterbi porte sur son score, pas sur spellF1.

## 2. Un match externe vérifié entièrement

Source : DFL IDSSE, Bassek et al. 2025, Figshare **28196177 version 1**, licence
CC BY 4.0. Les sept matchs sont enregistrés dans `docs/sources.json` et leurs
fichiers attendus sont figés dans `configs/dfl_manifest.json`.

Le match **J03WMX** appartient à l’apprentissage. Seuls son XML de métadonnées
et son XML de positions sont téléchargés, environ 419 Mo au total. Taille et MD5
sont vérifiés, SHA-256 consigné localement. Aucun fichier des matchs de validation
ou du test final n’est téléchargé par cette préparation.

| Contrôle | Résultat |
|---|---|
| Frames traitées | 145,967 |
| Première mi-temps | 70,708 frames |
| Deuxième mi-temps | 75,259 frames |
| Cadence | 25 Hz, horodatages du ballon vérifiés sur toutes les frames |
| Durées des périodes | Accord avec les métadonnées du match |
| Terrain source | 105.0 × 68.0 m |
| Pistes anonymisées dans l’interface | 40 emplacements, dont des joueurs absents selon la frame |
| Labels H | 39,111 |
| Labels A | 46,258 |
| Labels D | 60,598 |
| Labels X / inconnus | 0 |
| Statuts/propriétaires inconnus dans ce match | 0 |

L’ingestion distingue ordre, doublons, données absentes, erreurs de coordonnées et
références d’équipes. Les lignes mortes sont conservées. Le mapping ne dépend pas
de l’ordre des équipes dans le XML. Les coordonnées natives en mètres sont
converties au repère normalisé Metrica, avec les dimensions propres au terrain ;
on ne les étire pas artificiellement à 105,3 m.

Contrôle indépendant de bibliothèque : **200 frames, 4 400 positions de joueurs
et leurs équipes, 200 états connus** comparés avec Kloppy 3.19.1,
`only_alive=False`, `coordinates="metrica"`. Tous concordent. Il s’agit d’un
contrôle de parseur/conventions, pas d’une nouvelle annotation de vérité terrain.

Les vitesses XML DFL en km/h sont exclues des entrées du modèle. Pour BAR-ATH,
le désaccord documentaire kph/m/s reste signalé ; les futures cinématiques devront
être dérivées des positions et des temps validés sur des fragments continus.

## 3. Entrées et réponses strictement séparées

- `inputs.npz` contient uniquement x/y normalisés, masques calculés depuis x/y,
  appartenance des pistes à H/A, frame/période, cadence et dimensions du terrain.
- `targets.npz` contient uniquement H/A/D/X et les clés d’alignement.
- BallStatus et BallPossession servent uniquement à construire les cibles.
  La hauteur Z, les noms, numéros de maillot, identités stables et événements ne
  sont pas exposés au prédicteur.
- Les entrées du prédicteur et des dégradations sont typées `ExternalInputs`,
  avec liste blanche versionnée. Un conteneur de cibles ou un fichier d’entrée
  contenant un champ `labels` est refusé.
- Statut 0 → D ; statut 1 et propriétaire 1/2 → H/A ; information inconnue → X.
  Les défauts de bibliothèque ne transforment jamais un inconnu en A ou D.

Les tests modifient les statuts et propriétaires synthétiques sans modifier les
observations : les champs d’entrée restent identiques. La lecture d’entrées et
la prédiction sont aussi vérifiées sans ouverture du fichier de cibles.

## 4. Protocole fixé avant le premier score

`configs/external_protocol.json`, daté du 26 octobre, a été écrit avant le premier
score externe. L’empreinte du protocole accompagne chaque préparation et rapport.

| Usage | Matchs |
|---|---|
| Apprentissage | J03WMX, J03WN1, J03WOH, J03WOY |
| Validation | J03WPY, J03WQQ |
| Test final verrouillé | J03WR9 |

Les mi-temps d’un match restent ensemble. Le test final est refusé par les accès
de développement jusqu’au futur gel d’une candidate. Le découpage est par match,
sans prétendre être indépendant des clubs ou des saisons.

Scénarios fixés : propre, trous courts, trous longs, bruit spatial, trous favorisés
en zone dense, pistes interrompues, combinaison. Graines 20261026/27/28. Le propre
est exécuté une fois et les autres trois fois. Les dégradations ne reçoivent jamais
les cibles et ne changent pas les données originales. Les distributions ne sont
pas présentées comme un simulateur validé du capteur BAR-ATH.

## 5. Baseline mesurée avant toute nouvelle méthode

La baseline ±50 et son repli D restent fixés. Elle utilise les distances métriques
du terrain externe, lisse séparément par mi-temps et n’applique aucun masque
temporel propre à BAR-ATH. Les prédictions sont produites avant la lecture des
cibles par le banc d’évaluation. Le scoreur officiel figé calcule les métriques.

Résultats sur le **seul match d’apprentissage J03WMX** ; les lignes à trois
graines présentent leur moyenne, sans choisir le meilleur résultat :

| Scénario | Exécutions | spellF1 | macroF1 |
|---|---:|---:|---:|
| clean | 1 | 0.3072 | 0.4150 |
| short_gaps | 3 | 0.2892 | 0.4116 |
| long_gaps | 3 | 0.1970 | 0.4666 |
| spatial_noise | 3 | 0.3076 | 0.4147 |
| crowded_gaps | 3 | 0.1947 | 0.4303 |
| fragmented_tracks | 3 | 0.2499 | 0.3863 |
| combined | 3 | 0.1631 | 0.4279 |

Le scénario propre donne F1(D) = **0.0000**. Le ballon étant
observé sur tout ce match, notre hypothèse simpliste « absence → D » ne détecte
pas les vrais arrêts. Un masquage artificiel peut augmenter macroF1 en produisant
des D par hasard ; cela n’est pas une amélioration de méthode. Ces résultats
montrent l’intérêt d’un détecteur vivant/mort distinct, à construire ensuite.

Ces scores sont un contrôle de fonctionnement et une référence de développement,
pas une mesure sur un match réservé, pas un gain MYA et pas une performance
attendue au concours. Aucun paramètre n’est choisi sur ces scores ni sur les cinq
minutes publiques BAR-ATH. Aucun modèle appris n’est entraîné ici.

## Régression de la référence du concours

`configs/baseline_reference.json` conserve les réglages et l’empreinte initiale.
La seule adaptation au calcul de proximité est un argument optionnel de dimensions
du terrain, dont la valeur par défaut reste celle du concours. Une régénération
du CSV BAR-ATH donne exactement l’empreinte du jalon 2 :

```text
faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797
```

Le fichier `submissions/MYA.csv` original reste identique. Aucune vérité terrain
publique BAR-ATH n’est lue par cette préparation.

## Refaire les contrôles

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-external.txt
.venv\Scripts\python.exe -m src.external_benchmark --prepare --benchmark
.venv\Scripts\python.exe -m src.external_validation
.venv\Scripts\python.exe -m unittest discover -s tests -q
.venv\Scripts\python.exe -m src.hygiene.repository_check
```

**66 tests synthétiques réussis**, dont 16 nouveaux couvrant les cibles inconnues,
la séparation de données, les périodes, les unités de distance, les téléchargements
et empreintes, le test verrouillé et la reproductibilité des dégradations. Les
tests ne téléchargent ni ne lisent les données réelles. Le contrôle de publication
et `pip check` passent.

Sources et règles : [protocole externe](../docs/external_validation_protocol.md).
Données, archives préparées, prédictions et rapports détaillés restent dans
`.cache/external/dfl/28196177/v1/`, ignoré par Git.

**Condition de départ satisfaite pour le jalon 3 :** une source externe contrôlée,
des entrées séparées des cibles, un découpage figé et une baseline mesurée. Les
caractéristiques et modèles des jalons suivants restent à développer.
