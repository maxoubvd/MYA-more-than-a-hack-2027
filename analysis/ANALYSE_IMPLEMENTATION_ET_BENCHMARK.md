# Analyse de l’implémentation et du benchmark — équipe MYA

> Note préparée le 25 octobre 2026 à partir de l’audit du 22 octobre et de la recherche bibliographique complémentaire présentée dans la discussion. État de code examiné : `0d44f2c` sur `main`. Une vérification du dépôt distant le 25 octobre confirme que cette révision est encore sa tête avant publication de cette note.
>
> **Contexte de lecture :** le projet est en phase de conception. L’absence d’implémentation des modules annoncés est normale à ce stade ; elle est consignée pour distinguer la conception, les mesures réalisées et les résultats encore hypothétiques. Elle ne constitue pas un jugement sur la qualité de la recherche. Les remarques techniques et les propositions bibliographiques sont séparées.
>
> **Statut des preuves :** les défauts signalés comme reproduits ont été vérifiés sur des données synthétiques ; les scores de référence ont été recalculés sur les seules annotations publiques. Aucun modèle MYA ou article ajouté au benchmark n’a été évalué sur la vérité privée du concours. Aucune donnée privée ni aucun extrait reconstructible n’est inclus dans cette note.

## Repères de lecture

- Sections 1 à 3 : points forts, état de réalisation et défauts techniques vérifiés.
- Sections 4 à 6 : hypothèses scientifiques, documents et règles à prendre en compte.
- Sections 7 à 9 : propositions d’architecture, de validation et d’organisation.
- Sections 10 et 11 : compléments au benchmark et comparaison des stratégies candidates.

## Avis général

Le projet dispose d'une bonne compréhension des difficultés du concours et d'un travail réel de préparation : exploration, chargeurs, configuration, documentation et architecture cible. Le point à garder explicite est l'écart entre une architecture cible ambitieuse et les composants déjà exécutables ; cet écart est attendu à ce stade de conception. La prochaine priorité devrait être une première chaîne complète, mesurée et reproductible, avant l'ajout de nouveaux modèles.

L'objectif que je recommande est d'obtenir rapidement une soumission fiable, puis de démontrer séparément l'utilité de chaque amélioration. Aucun élément examiné ne permet aujourd'hui d'affirmer que MYA dépasse la référence officielle, ni de prédire une place au classement.

## Périmètre et limites

- Dépôt examiné : `maxoubvd/MYA-more-than-a-hack-2027`, branche `main`, commit `0d44f2c`. Seule cette branche apparaît dans la copie clonée.
- Sources examinées : README, configuration, chargeurs, tous les fichiers Python, plan de 371 lignes, sources des 26 cellules du notebook et texte du PDF de 31 pages. Inspection visuelle ciblée du PDF, notamment des figures des pages 3, 7 et 24.
- Vérifications exécutées : cas synthétiques des chargeurs et de la segmentation ; reproduction des quatre références sur les annotations publiques officielles ; vérification des règles Git ; consultation des règles et de plusieurs articles scientifiques originaux.
- Les données privées du match n'ont pas été chargées. Les sorties détaillées du notebook contenant des données du match n'ont pas été lues ni envoyées au modèle ; seules leur présence et leurs catégories ont été examinées.
- Je n'ai pas exécuté le notebook complet ni entraîné de modèle MYA. Les conclusions sur ses statistiques de tracking restent donc conditionnées à leur reproduction locale.
- Lors de l'audit initial, les sources du dépôt n'ont pas été modifiées. Les essais ont été réalisés sur une copie séparée ; la présente publication ajoute uniquement cette note Markdown.

## 1. Ce qui est bien engagé

### Le problème est posé au bon niveau

Le rapport et le plan ont identifié la continuité des possessions, les arrêts de jeu et les transitions comme les objets à traiter. La distinction entre contrôle effectif et simple proximité est pertinente. Garder la dernière équipe sur un ballon disputé correspond à la définition du concours.

### Les particularités des entrées ont été prises au sérieux

Le travail mentionne le ballon souvent manquant, les pistes anonymes et instables, les doublons de joueurs, le bruit des annotations tactiques et les touches sans équipe renseignée. Le tri des joueurs par distance au ballon, avec regroupement par équipe, constitue une représentation de départ raisonnable et indépendante de l'ordre des pistes.

### Il existe du code utile

La configuration centralise les constantes et les chemins. Les chargeurs séparent les annotations publiques, le Smart Tagging, les homographies, les équipes et le tracking. Le parsing en flux, les tableaux préalloués et le cache sont des choix adaptés à la taille du match. Le chargeur tactique fonctionne sur mon petit exemple valide.

Le notebook appelle directement le module officiel pour les métriques. Cette réutilisation est préférable à une réécriture personnelle de la notation.

### La structure aide le travail à trois

Les responsabilités sont identifiables. Les instructions d'installation sont détaillées. La séparation entre données, sources et sorties est utile. Une arborescence préparée peut faciliter la répartition des tâches, à condition d'afficher clairement les composants encore à écrire.

## 2. L'état réel de réalisation

| Élément | État constaté |
|---|---|
| Configuration | Implémentée, avec quelques limites de portabilité |
| Chargeurs | Implémentés, avec des défauts reproductibles |
| Notebook | Exploration codée ; sorties enregistrées ; exécutions non séquentielles |
| Modèles, Viterbi, HSMM, raffinement, export | Fichiers préparatoires vides |
| Exécution complète | `src/pipeline.py` est vide |
| Tests présents dans le dépôt | Aucun répertoire ou dispositif de tests identifié |
| Soumission MYA présente | Aucune ; seulement `submissions/.gitkeep` |
| Gain MYA mesuré | Aucun résultat reproductible trouvé |

Sur 45 fichiers Python, 41 sont vides. Les quatre autres sont `config.py`, `utils/loaders.py` et deux fichiers d'initialisation. Ce décompte décrit le contenu du dépôt ; il ne mesure pas un pourcentage d'avancement.

Le Gantt indique déjà le jalon 0 comme terminé alors que ses fichiers de masquage, garde et validation sont vides. Le README devrait distinguer explicitement « disponible », « à tester » et « prévu ».

## 3. Défauts techniques confirmés

### Priorité haute — le chargeur broadcast ne prend pas en charge ses propres métadonnées

Référence : `src/utils/loaders.py`, lignes 324–356 ; `src/config.py`, ligne 104.

Les deux sources sont parsées avec `NUM_SLOTS = 46`. Le broadcast possède 51 pistes. Avec 51 pistes renseignées sur une ligne synthétique, le chargeur échoue : `IndexError: index 46 is out of bounds for axis 1 with size 46`.

Un second défaut subsiste après correction de la dimension : `load_team_mapping()` est appelé sans transmettre le XML correspondant à la source. Le broadcast récupère donc le mapping tactique. Sur mes fixtures distinctes, il renvoie 46 associations tactiques au lieu des 51 associations broadcast.

**Correction recommandée :** définir les chemins et le nombre de pistes par source, lire les équipes depuis le XML sélectionné et contrôler que les dimensions concordent. L'appartenance des pistes doit venir des métadonnées plutôt que d'identifiants d'équipes figés.

### Priorité haute — des entrées incomplètes peuvent devenir des tableaux apparemment complets

Référence : `src/utils/loaders.py`, lignes 248–267 et 295.

Le parseur préalloue la taille attendue, puis renvoie les tableaux sans contrôler le nombre de lignes effectivement lues. Un fichier synthétique d'une ligne, attendu sur trois images, produit trois lignes dont les identifiants sont `[1, 0, 0]`. Une ligne supplémentaire est silencieusement abandonnée. Des identifiants désordonnés sont acceptés.

Ces cas ne prouvent pas que les fichiers livrés sont corrompus. Ils montrent que le chargeur ne distingue pas une absence réelle du ballon d'un fichier incomplet ou mal aligné. Le résultat tronqué peut même être enregistré en cache.

**Correction recommandée :** vérifier le compte exact, la suite `1..N`, l'unicité, les dimensions, le format des lignes et les valeurs avant d'autoriser un cache ou une prédiction.

### Priorité haute — le cache ne suit pas les changements des sources

Référence : `src/utils/loaders.py`, lignes 337–347 et 361–370.

J'ai mis en cache un fichier synthétique, changé sa position de ballon puis rechargé : le cache renvoie encore `0,4`, tandis que la lecture directe renvoie `0,9`. Ni la source, ni son empreinte, ni la version du parseur ne sont vérifiées.

Changer `MTAH_DATA_DIR` peut aussi réutiliser le même cache local associé à un autre dossier de données.

**Correction recommandée :** enregistrer la source, les dimensions, la version du parseur et une signature des entrées ; écrire les caches de manière atomique.

### Priorité haute — une règle Git masque aussi les futurs fichiers sources

Référence : `.gitignore`, ligne 40.

Le motif `models/` s'applique à tous les dossiers portant ce nom, dont `src/models/`. Git confirme qu'un futur `src/models/new_classifier.py` serait ignoré. Les fichiers déjà suivis restent suivis, mais les nouveaux modules risquent de manquer lors d'un partage ou d'une reproduction.

**Correction recommandée :** utiliser `/models/` pour cibler seulement les artefacts à la racine.

### Reproductibilité de l'installation

Référence : `requirements.txt`, ligne 14.

`possession_metrics` est inscrit comme dépendance installable, alors que le projet utilise le fichier du dépôt officiel. La requête vers le paquet correspondant sur PyPI renvoie HTTP 404 lors de cet audit. Une installation standard avec ce fichier risque donc de s'arrêter à cette dépendance.

Les versions des autres dépendances ne sont pas fixées. Les bibliothèques des modèles annoncés ne sont pas encore présentes, ce qui est cohérent avec leur absence d'implémentation mais devrait être présenté comme tel.

**Correction recommandée :** importer les métriques depuis une révision officielle identifiée, séparer les dépendances minimales des options de recherche et figer l'environnement validé.

### Portabilité et cohérence des chemins

La configuration reconstruit le chemin du dépôt MYA à partir d'un nom de dossier imposé. Renommer la copie peut provoquer la création d'un autre dossier lors de l'import. La création automatique de répertoires à l'import rend ce comportement discret.

Le notebook contient ses propres chemins et parseurs, sans réutiliser les chargeurs et la configuration centralisée. Il ne tient pas compte de `MTAH_DATA_DIR`. L'affirmation du README selon laquelle toutes les cellules reposent sur `config.py` ne correspond donc pas au code actuel.

**Correction recommandée :** déduire la racine MYA de l'emplacement du package, rendre le dépôt officiel configurable et faire utiliser au notebook les mêmes interfaces que la chaîne finale.

## 4. Conclusions scientifiques à revoir

### Un trou de tracking long n'établit pas un arrêt de jeu

Référence : plan, lignes 161–203 ; notebook, cellule 17.

La distribution des durées de trous est une observation utile. La conclusion selon laquelle ces trous sont presque tous des arrêts réels ne découle pas de cette distribution. Le ballon peut rester hors champ ou occulté pendant une phase vivante. Inversement, un ballon visible peut être mort.

Une erreur de reprojection supérieure à `1,2` indique une difficulté géométrique, pas une décision de l'arbitre. Une mauvaise calibration existe pendant le jeu et une excellente calibration pendant un arrêt.

**Recommandation :** combiner plusieurs indices pour estimer une probabilité de ballon vivant ; réserver les règles certaines aux informations effectivement publiées comme telles.

### La fusion broadcast constitue un projet distinct

Référence : plan, lignes 189–196.

Un décalage global d'environ 304 images ne peut pas décrire une vidéo contenant des coupures et des ralentis. Une homographie valide ne prouve pas qu'une image montre le direct : un ralenti peut aussi montrer un terrain parfaitement calibré. La ressemblance géométrique est un indice d'alignement, pas une garantie d'identité temporelle.

Par ailleurs, les coordonnées ATD sont déjà sur le terrain normalisé. Appliquer une homographie inverse à ces coordonnées serait une erreur d'unité. Cette inverse est utile lorsqu'un nouveau détecteur fournit des coordonnées en pixels.

**Recommandation :** reporter cette fusion après la première solution tactique. Si elle est expérimentée, produire un alignement par segments avec confiance, possibilité de rejet et contrôle de la cohérence du ballon. Mesurer le gain sur les transitions plutôt que seulement le nombre de positions récupérées.

### Les gains et la pureté annoncés ne sont pas mesurés

Le plan annonce notamment une pureté des ancres supérieure à 98 %, une couverture de 60 à 70 %, une incertitude résiduelle sous 5 %, des gains de fusion et des objectifs de scores progressifs. Aucun résultat expérimental trouvé ne les établit.

Les scores cibles peuvent servir à exprimer une ambition. Ils ne constituent ni une prévision fiable ni une estimation de place au podium. Les indications « Dépassé » du tableau des références doivent également être retirées tant qu'une soumission MYA n'a pas été évaluée.

### Les pseudo-labels ne remplacent pas une vérité indépendante

Des règles de proximité peuvent créer des exemples faciles, mais aussi étiqueter à tort un joueur qui attend une remise en jeu. Le Smart Tagging et le tracking proviennent en partie de la même chaîne automatique : leur accord n'implique pas des erreurs indépendantes.

Valider un modèle contre des pseudo-labels issus de ces règles mesure surtout sa capacité à reproduire les règles. Des blocs temporels réduisent certaines dépendances mais ne résolvent pas ce problème. Il faut aussi éviter de partager une même possession ou des fenêtres de contexte chevauchantes entre apprentissage et validation.

La calibration isotonique sur seulement 17 possessions et l'ajustement de nombreux seuils sur les mêmes cinq minutes sont particulièrement fragiles.

**Recommandation :** mesurer séparément couverture et erreurs des ancres sur les annotations publiques disponibles, conserver l'incertitude sur le reste, et chercher une validation externe dont les conventions de possession et d'arrêt sont explicites.

### Les contraintes de transition doivent rester compatibles avec les erreurs des capteurs

Référence : plan, lignes 289–302.

Interdire strictement `H → A` si aucun adversaire n'est à moins de 1,2 m peut empêcher une récupération réelle pendant un trou de ballon ou de joueur. Une forte vitesse du ballon n'exclut pas non plus une interception ou une passe adverse instantanée.

Une autotransition de 0,98 donne une durée moyenne géométrique de 50 images, soit deux secondes ; elle ne garantit pas une durée minimale et ne supprime pas automatiquement tous les changements parasites. Viterbi peut lui aussi être mal réglé et surajusté.

**Recommandation :** employer des pénalités souples modulées par la fiabilité des observations, puis vérifier les effets par type de frontière. Si une durée explicite est utile, l'introduire dans le modèle plutôt que d'ajouter plusieurs lissages successifs.

### Les très courtes possessions ne sont pas mathématiquement impossibles à scorer

Référence : plan, lignes 316–324.

Une possession courte correctement localisée peut avoir une IoU de 1. Sa durée absolue ne l'empêche donc pas de franchir les seuils. La suppression automatique de toutes les possessions de moins de 18 images peut détruire de vraies transitions.

Contre-exemple synthétique avec le scoreur officiel : une séquence parfaite `H(100) A(10) H(100) D(100)` obtient 1 ; absorber les dix images `A` dans `H` fait tomber `spellF1` à 0,2. Il s'agit d'un exemple de sensibilité, pas d'un résultat sur le match.

### Remplacer tous les X ne garantit pas une hausse de macroF1

Le remplissage explicite reproduit bien la transformation appliquée par le scoreur temporel, à condition de respecter ses blocs et son traitement du début de période. Mais une mauvaise réponse remplie ajoute un faux positif à la classe prédite, en plus du faux négatif de la vraie classe. Une abstention ajoute seulement le faux négatif.

Contre-exemple synthétique : le remplissage conserve `spellF1 = 0,5333`, mais fait baisser `macroF1` de `0,6667` à `0,6000`. La politique sans X peut être raisonnable en pratique ; sa domination mathématique annoncée dans le PDF est fausse.

### Quelques détails physiques demandent de la précision

- La vitesse d'approche du plan, avec `Δx = x_joueur - x_ballon`, a un signe opposé à une approche positive et ne tient pas compte de la vitesse du ballon. Pour une vitesse de fermeture positive : `-Δr · (v_joueur - v_ballon) / ||Δr||`, avec protection à distance nulle.
- `distance / max(vitesse, 2)` est un indicateur grossier, pas un temps physique d'interception tenant compte de la direction et de l'accélération.
- Lisser une piste de joueur à travers une rupture d'identité crée une trajectoire fictive. Les dérivées doivent être calculées par tronçons continus et accompagnées d'indicateurs de fiabilité.
- Le pitch control estime un contrôle potentiel de l'espace ; ce n'est pas directement la possession selon les conventions du concours. Sa valeur ajoutée doit être comparée aux simples distances et à leur historique.
- L'origine du repère ne peut pas être « centre ou corner » indifféremment : la conversion indiquée suppose un coin comme origine. Tout changement doit aussi transformer vitesses, limites et projections.

## 5. Audit du notebook et du PDF

### Des calculs utiles, mais une séparation insuffisante entre mesure et interprétation

Le notebook parcourt les fichiers réels et calcule des statistiques. Cependant plusieurs légendes et conclusions sont écrites en dur : elles ne deviennent pas démontrées simplement parce qu'elles figurent après un calcul. La présentation « 100 % empirique » devrait être réservée aux valeurs effectivement calculées et contrôlées.

Exemples :

- La cellule 8 prétend vérifier les périodes sans constantes, mais les intervalles et les repères sont prédéfinis ; certains marqueurs de ballon sont placés à une valeur fixe.
- La cellule 22 nomme la première situation « Barcelona engage », alors que les annotations publiques officielles donnent `A` aux images 11185 et 11187.
- La cellule 17 calcule les séquences manquantes après concaténation des deux périodes évaluées. Deux absences séparées par la mi-temps peuvent alors fusionner. Ce risque est confirmé sur un exemple synthétique ; je n'affirme pas qu'il modifie les chiffres du match sans nouvelle exécution locale.
- L'histogramme des trous s'arrête à 2 000 images alors que le plan mentionne un maximum supérieur à 5 000. Il peut ainsi omettre la partie la plus importante de la distribution.
- Les nombres d'exécution montrent une reprise partielle du notebook. Une exécution propre du début à la fin reste nécessaire pour valider la cohérence de l'ensemble.

### Les figures du PDF comportent des valeurs erronées

La figure de la page 3 donne notamment `spellF1 = 0,3654` sur les cinq minutes pour smooth50. Le résultat officiel que j'ai recalculé est `0,3256`. Ses valeurs de macroF1 public divergent aussi des résultats reproductibles : par exemple smooth50 y vaut `0,6920`, contre `0,6207` dans le scoreur.

Les références recalculées sont :

| Référence | macroF1 public | spellF1 public | Possessions prédites dans la fenêtre |
|---|---:|---:|---:|
| raw | 0,5972 | 0,0378 | 131 |
| smooth25 | 0,6200 | 0,2868 | 36 |
| smooth50 | 0,6207 | 0,3256 | 26 |
| smooth125 | 0,5812 | 0,4242 | 16 |

**Recommandation :** générer les figures directement depuis les résultats enregistrés du scoreur, sans ressaisie intermédiaire.

### La notation officielle n'utilise pas l'algorithme hongrois pour les possessions

Le README, le notebook et le PDF le mentionnent pourtant. Le fichier officiel `possession_metrics.py`, fonctions `matched_gt_flags` et `match_spells`, trie les couples par IoU décroissante puis réalise un appariement glouton un-pour-un. Les labels d'équipe doivent aussi correspondre.

La réutilisation actuelle du module officiel protège le notebook de cette erreur descriptive. En revanche, compléter `src/utils/metrics.py` en suivant le texte pourrait créer un score local différent.

### La bibliographie est une piste de recherche, pas un benchmark MYA

Les méthodes citées existent pour plusieurs d'entre elles et leurs idées sont pertinentes, mais elles n'ont pas été comparées expérimentalement sur votre chaîne. Les formules « optimal », « garantit », « aucun risque de surapprentissage » et « surpasse structurellement » sont excessives.

Une erreur vérifiable : la référence 10, `arXiv:2007.06866`, porte sur ASRF, qui combine classification et détection de frontières. Elle ne correspond pas à l'article MS-TCN++. Ce dernier est `arXiv:2006.09220`. Cette confusion fournit aussi une idée utile : une tête explicite de frontière mérite d'être étudiée.

La supervision par timestamps de l'article CVPR 2021 repose sur des annotations localisées ; des ancres automatiques imparfaites qui peuvent manquer des possessions n'offrent pas les mêmes garanties. De même, l'existence de BallRadar n'établit pas qu'un entraînement sur les seules positions visibles de ce match résoudra ses occultations longues.

## 6. Règlement et publication

Le PDF indique encore que des annotations manuelles limitées du match pourraient servir à l'entraînement ou à la validation. Cette lecture doit être remplacée par la précision des organisateurs du 22 octobre : aucune annotation manuelle de BAR-ATH, même pour ces usages. Les annotations externes d'autres matchs sont possibles sous les conditions de droits, d'accès et de documentation.

Le dépôt contient un notebook avec des sorties enregistrées. La cellule 11 affiche des événements détaillés issus du XML et conserve une sortie tabulaire ; la cellule 22 trace des configurations de joueurs et conserve une image. Leur publication doit être vérifiée au regard des conditions signées, car le règlement interdit la redistribution des données et de dérivés permettant leur reconstruction. Je recommande de retirer les sorties détaillées de la version publique et de traiter les éventuelles copies historiques après vérification, sans réécrire l'historique partagé unilatéralement.

Les vidéos, données privées et leurs extraits ne doivent pas être transmis à un LLM hébergé. L'assistance doit donc porter sur les sources, la méthode et les traitements locaux, sans faire remonter ces contenus dans la discussion.

Enfin, nommer X hors période évaluée est une convention pratique ; les prédictions de ces périodes sont ignorées par le scoreur, il ne s'agit pas d'une obligation donnant un gain de score. Le D publié avant le deuxième coup d'envoi est, lui, une information officielle exploitable.

## 7. L'architecture que je privilégierais

### Première version complète et légère

1. Entrées contrôlées, dimensions par source et provenance des caches.
2. Descripteurs tactiques simples : distances par équipe, visibilité et fiabilité du ballon, cinématique locale fiable, activité collective, indices tactiques et proximités des reprises.
3. Estimation distincte de la probabilité de ballon vivant et des indices de contrôle de chaque équipe.
4. Mémoire de la dernière équipe ayant contrôlé le ballon pendant les passes et les duels.
5. Décodeur temporel souple, réinitialisé entre les périodes, puis contraintes publiques et validation officielle.

L'intérêt de séparer ballon vivant et équipe est qu'une équipe proche d'un ballon immobile ne suffit pas à distinguer une conservation tranquille d'une préparation de coup franc.

Le système doit pouvoir décider de la possession sans inventer une position précise du ballon sur chaque image. Une estimation manquante, accompagnée d'une incertitude, est parfois plus utile qu'une interpolation qui paraît crédible et entraîne une mauvaise transition.

### Idées supplémentaires à tester

**Détecter d'abord les frontières candidates.** Changements brusques de proximité relative, freinage du ballon, apparitions/disparitions et reprises fournissent des candidats. Une segmentation peut ensuite départager les explications cohérentes. Cela rapproche les décisions de l'objet évalué par spellF1.

**Confirmer dans le futur puis revenir au début du contrôle.** L'analyse est hors ligne. Si plusieurs images ultérieures confirment une récupération, le système peut dater son début au premier indice crédible, au lieu d'attendre la confirmation avant de changer l'étiquette. Cela réduit les retards artificiels sans accepter chaque contact parasite.

**Conserver plusieurs hypothèses sur les longs trous.** Comparer « même possession », « récupération adverse » et « arrêt » en utilisant les indices avant et après le trou. Une pénalité souple est préférable à un verrouillage irréversible fondé sur une seule observation manquante.

**Mesurer le gain près des frontières.** Si les chiffres du plan sont reproduits, les trous de 50 images ou moins ne totalisent que 75 images manquantes. Un gros module de reconstruction de ces seuls trous aura peu de couverture, même si quelques-uns peuvent être importants pour une transition. La priorité doit suivre les erreurs effectivement observées.

**Apprendre des pseudo-labels avec un droit de désaccord.** Stocker l'origine et la confiance de chaque ancre, exclure les conflits, éviter d'utiliser ces mêmes ancres comme preuve indépendante de qualité. Si elles ne couvrent que les situations faciles, il faut le mesurer et garder une stratégie spécifique pour les frontières.

**Mettre l'incertitude au centre.** Ajouter l'âge depuis la dernière observation, le temps jusqu'à la suivante, la longueur du trou, la continuité des pistes et les désaccords entre indices. Le modèle peut alors réduire sa confiance plutôt que durcir ses règles lorsque les capteurs deviennent moins fiables.

## 8. Validation et expérimentation

Conserver trois niveaux de preuve distincts :

- **Conformité et fonctionnement :** schéma du CSV, alignement, bornes, lecture/cache, reproduction exacte. Les tests synthétiques sont adaptés ici.
- **Diagnostic public :** scoreur officiel sur les cinq minutes, résultats par classe et seuil d'IoU, erreurs autour des transitions. Les marges de bootstrap donnent une idée de l'incertitude d'échantillonnage ; elles ne corrigent ni un biais du début de match ni un choix répété d'hyperparamètres.
- **Validation externe :** autres matchs avec conventions documentées, contrôle de l'alignement et dégradations synthétiques réalistes. Les jeux Metrica Sample Data sont une piste d'entrée ; il faut vérifier la disponibilité et la définition des labels nécessaires, pas supposer qu'ils constituent directement un corrigé compatible.

Effectuer une comparaison par ajouts successifs : référence officielle ; indices tactiques ; détection des arrêts ; mémoire de contrôle ; décodage ; puis éventuellement apprentissage et fusion vidéo. Pour chaque expérience, enregistrer le commit, la configuration, la provenance des entrées, la graine éventuelle, la durée, le score public, les statistiques des prédictions et l'empreinte de la soumission.

Sur le match entier non annoté, les durées et le nombre de possessions servent à repérer une anomalie, pas à imposer une distribution que l'on ne connaît pas. Ne pas régler la sortie pour atteindre les nombres de possessions approximatifs du tableau du plan.

## 9. Priorités proposées jusqu'au rendu

| Période proposée | Travail | Critère d'achèvement |
|---|---|---|
| Première étape — 1 à 2 jours | Fiabiliser ingestion, dépendances, Git et publication ; brancher une première référence complète | Un CSV régénérable et accepté par le validateur officiel |
| Étape suivante — quelques jours | Indices tactiques, arrêts de jeu, mémoire de contrôle, premier décodeur | Comparaisons isolées et diagnostics de transitions |
| Avant le 6 novembre | Validation externe et apprentissage léger si les règles atteignent leurs limites | Une amélioration étayée et un protocole documenté |
| 6–10 novembre | Une seule piste plus coûteuse, choisie sur les erreurs persistantes | Gain mesuré suffisant pour justifier le coût |
| 11–14 novembre | Stabilisation, reproduction propre et rédaction | Même CSV produit depuis un environnement neuf |
| 15–16 novembre | Vérification des livrables et dépôt avec marge | Fichiers définitifs validés et accessibles |

Ce calendrier est une recommandation d'organisation, pas une estimation de charge garantie. Le plan actuel reporte la première validation finale et le raffinement complexe trop près de l'échéance.

À trois, je répartirais provisoirement : une personne sur les entrées et la reproduction, une sur les indices de contrôle/arrêt et le décodage, une sur le protocole d'évaluation, les expériences et la documentation. Chacun doit livrer des interfaces utilisables par les autres, pas trois systèmes indépendants.

Je mettrais MS-TCN++, BallRadar et la fusion broadcast en réserve jusqu'à disposer de preuves qu'ils répondent à une erreur importante. Une chaîne légère avec des décisions temporelles fiables me paraît une meilleure première cible.

## Sources de l’audit initial

- [Dépôt MYA](https://github.com/maxoubvd/MYA-more-than-a-hack-2027), état local `0d44f2c`.
- [Définition du défi](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md).
- [Données et coordonnées](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md).
- [Évaluation](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/EVALUATION.md) et [code du scoreur](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/evaluation/possession_metrics.py).
- [Règles](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/RULES.md), [FAQ](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/FAQ.md) et [clarification des annotations du 22 octobre](https://github.com/metrica-sports/more-than-a-hack-2027/issues/8).
- [ASRF — arXiv:2007.06866](https://arxiv.org/abs/2007.06866).
- [MS-TCN++ — arXiv:2006.09220](https://arxiv.org/abs/2006.09220).
- [Temporal Action Segmentation from Timestamp Supervision, CVPR 2021](https://openaccess.thecvf.com/content/CVPR2021/html/Li_Temporal_Action_Segmentation_From_Timestamp_Supervision_CVPR_2021_paper.html).
- [Ball Trajectory Inference from Multi-Agent Sports Contexts, KDD 2023](https://arxiv.org/abs/2306.08206).
- [Fernandez et Bornn, Wide Open Spaces, 2018](https://www.lukebornn.com/papers/fernandez_ssac_2018.pdf).
- [Metrica Sample Data](https://github.com/metrica-sports/sample-data).

Les résultats détaillés des vérifications ont été conservés dans l'espace de travail de l'audit et ne sont pas publiés dans ce commit. Les expériences et résultats décrits ci-dessus concernent des exemples synthétiques et les seules annotations publiques, pas une performance MYA sur le match entier.


## 10. Couverture du benchmark : quelles familles pourraient être compétitives ?

### Réponse et portée

La recherche initiale couvre plusieurs familles crédibles : modèles tabulaires, pitch control, réseaux d'ensembles ou de graphes, reconstruction du ballon, modèles temporels et décodage structuré. Elle ne permet pas encore de fermer le choix de l'architecture. Certaines formulations très proches de la tâche méritent une analyse distincte.

Cette section complète la revue bibliographique. Les modèles ci-dessous n'ont pas été exécutés dans le cadre de cet audit. « Prioritaire » exprime une appréciation de pertinence pour le concours, pas une performance démontrée ni une promesse de classement.

### 10.1 PathCRF — chemin de possession depuis les joueurs seuls

**Référence :** Kim et al., *PathCRF: Ball-Free Soccer Event Detection via Possession Path Inference from Player Trajectories*, KDD 2026. [Article](https://arxiv.org/abs/2602.12080), [code et modèles](https://github.com/hyunsungkim-ds/pathcrf).

Le modèle infère une séquence décrivant le contrôle d'un joueur, le déplacement du ballon entre joueurs et les sorties du terrain. Un CRF à scores dynamiques et un décodage de Viterbi imposent une cohérence entre ces situations.

**Pourquoi l'étudier :** il traite directement l'inférence de possession sans exiger une observation du ballon, ce qui correspond à une difficulté centrale du concours. Il va au-delà d'une classification indépendante de H/A/D en représentant des états internes plus riches.

**Disponibilité vérifiée lors de la recherche :** le dépôt annonce du code, des modèles entraînés et une préparation des données Sportec Open DFL sur sept matchs. Cela rend l'étude plus concrète qu'une architecture disponible uniquement dans un article.

**Limites pour MYA :** le suivi temporel des joueurs n'est pas stable dans les données du concours. L'invariance à l'ordre des joueurs ne résout pas automatiquement les changements d'identité au cours du temps. Les états et événements du modèle doivent aussi être traduits dans les conventions de possession contrôlée et de ballon mort du concours.

**Priorité proposée : élevée pour l'étude et un essai de transfert.** Une version inspirée de ses principes, simplifiée au niveau des équipes, peut aussi être comparée au transfert du modèle complet.

### 10.2 Prédiction directe de H/A/D et séparation vivant–mort / équipe

**Référence :** Borghesi et al., *Using Temporal Convolutional Networks to estimate ball possession in soccer games*, Expert Systems with Applications, 2023. [Article et résumé](https://www.sciencedirect.com/science/article/pii/S0957417423002816), [DOI](https://doi.org/10.1016/j.eswa.2023.119780).

Ce travail est particulièrement proche de la sortie demandée : distinguer le ballon mort, la possession de l'équipe à domicile et celle de l'équipe à l'extérieur à partir de trajectoires. Il compare une prédiction ternaire à une formulation en deux décisions : ballon vivant ou mort, puis équipe en possession. Il étudie aussi des représentations invariantes à l'ordre des objets, avec réseaux temporels et attention.

**Question structurante :** faut-il reconstruire précisément le ballon avant de déterminer la possession ? Un modèle direct peut apprendre des indices collectifs utiles, même lorsque la position du ballon est indisponible.

**Limites :** les données de l'article sont confidentielles ; l'existence de l'article ne donne donc pas accès à son jeu d'entraînement. Les métriques et conventions publiées ne sont pas directement comparables au spellF1 du concours.

**Priorité proposée : élevée.** Cette formulation devrait être une alternative centrale à l'architecture en cascade, et pas seulement une variante du choix de réseau.

### 10.3 TranSPORTmer — trajectoires et états appris ensemble

**Référence :** Capellera et al., *TranSPORTmer: A Holistic Approach to Trajectory Understanding in Multi-Agent Sports*, ACCV 2024. [Article](https://arxiv.org/abs/2410.17785).

TranSPORTmer, déjà présent dans la bibliographie initiale, mérite une analyse spécifique. Son intérêt dépasse l'imputation : il combine compréhension des trajectoires et classification d'états comme les passes, le contrôle, les situations non contrôlées et les intervalles hors jeu.

**Pourquoi l'étudier :** l'apprentissage conjoint permet que la compréhension du jeu aide à inférer les trajectoires, et réciproquement. Cette famille remet en question la nécessité de fixer les sorties d'une étape avant que les étapes suivantes puissent les interpréter.

**Limites :** vérifier l'accès effectif aux poids et aux données, la supervision nécessaire, la gestion des observations manquantes et les différences de convention des états. La qualité d'imputation ne suffit pas à conclure sur la récupération des possessions complètes.

**Priorité proposée : élevée comme comparaison d'architecture ; faisabilité à établir avant engagement.**

### 10.4 Tracking et images locales des joueurs

**Référence :** Peral et al., *Multi-Modal Soccer Scene Analysis with Masked Pre-Training*, WACV 2026. [Article officiel](https://openaccess.thecvf.com/content/WACV2026/papers/Peral_Multi-Modal_Soccer_Scene_Analysis_with_Masked_Pre-Training_WACV_2026_paper.pdf).

Le modèle associe trajectoires, types de joueurs et images centrées sur les joueurs pour prédire la trajectoire du ballon, son état et son possesseur. Le préentraînement CropDrop masque des séquences visuelles afin de limiter la dépendance excessive à cette modalité.

**Pourquoi l'étudier :** les images peuvent apporter des indices absents des positions : orientation du corps, préparation d'un contrôle, geste de passe ou situation de remise en jeu. Cette approche est plus ciblée que l'analyse générale de clips par un grand modèle vidéo.

**Hypothèse pour MYA :** exploiter des images locales autour des joueurs pourrait aider sur les transitions ambiguës, éventuellement avec un encodeur visuel préentraîné et figé. Ce bénéfice reste à mesurer.

**Limites :** coût d'extraction des images, qualité de localisation des joueurs, disponibilité du code et des poids, quantité de supervision externe et fragilité des pistes temporelles.

**Priorité proposée : élevée pour la couverture bibliographique ; essai conditionné à la faisabilité et aux ressources.**

Un travail antérieur des mêmes auteurs, [*Temporally Accurate Events Detection Through Ball Possessor Recognition in Soccer*, VISAPP 2025](https://www.scitepress.org/Papers/2025/133177/133177.pdf), étudie la reconnaissance du possesseur via des séquences d'images centrées sur les joueurs, puis la détection des passes et réceptions. Il fournit une seconde entrée pour cette famille.

### 10.5 Classification et détection explicite des frontières

**Référence :** Ishikawa et al., *Alleviating Over-segmentation Errors by Detecting Action Boundaries*, WACV 2021. [Projet ASRF](https://yiskw713.github.io/asrf/), [article](https://arxiv.org/abs/2007.06866).

ASRF sépare une branche de classification des états et une branche de prédiction des frontières. Les frontières servent ensuite à affiner la segmentation.

**Pourquoi l'étudier :** spellF1 porte sur les intervalles. Une amélioration de la localisation des changements peut donc être plus utile qu'une amélioration de la classification au milieu des longues possessions.

**Adaptation possible :** prédire les probabilités de changement H/A, de passage vers D et de reprise du jeu, puis combiner ces indices avec les probabilités d'état dans un décodeur. Les frontières doivent rester conditionnées au type de transition ; chaque contact de balle n'est pas une nouvelle possession d'équipe.

**Limites :** les performances ASRF sur d'autres jeux de segmentation ne démontrent aucun gain sur ce concours. La supervision des frontières devra être définie avec les seules données autorisées.

**Priorité proposée : élevée pour une formulation simple inspirée du principe.**

### 10.6 Segmentation générative par diffusion

**Référence :** Liu et al., *Diffusion Action Segmentation*, ICCV 2023. [Article](https://openaccess.thecvf.com/content/ICCV2023/papers/Liu_Diffusion_Action_Segmentation_ICCV_2023_paper.pdf), [code DiffAct](https://github.com/Finspire13/DiffAct).

DiffAct formule la segmentation comme un débruitage conditionné par les observations et combine des objectifs de classification, de continuité temporelle et d'alignement des frontières.

**Pourquoi l'inclure :** cette famille complète la recherche au-delà de MS-TCN++ et des Transformers temporels. Elle peut produire des séquences cohérentes selon une formulation différente.

**Limites :** transfert depuis des jeux de segmentation non football, supervision nécessaire et complexité d'entraînement. Les résultats publiés ne sont pas des résultats sur H/A/D ni sur spellF1 du concours.

**Priorité proposée : secondaire.** Son absence ne justifierait pas, à elle seule, de retarder les comparaisons plus directement liées à la possession.

## 11. Transformer le benchmark en comparaison de stratégies

| Stratégie | Hypothèse principale | Point de vigilance |
|---|---|---|
| Géométrie, règles et décodage | Les indices physiques et tactiques suffisent avec peu de supervision | Seuils et confiance des observations |
| Prédiction directe H/A/D | Les trajectoires permettent d'éviter une reconstruction préalable du ballon | Supervision et généralisation |
| Deux décisions vivant–mort / équipe | Les deux difficultés profitent d'une modélisation distincte | Propagation d'erreurs si les décisions sont trop rigides |
| Chemin de possession structuré | Les interactions et la logique des passes améliorent la cohérence | Fragmentation des pistes et convention des états |
| Apprentissage conjoint trajectoire–état–possesseur | Des tâches liées s'améliorent mutuellement | Coût de supervision et erreurs communes |
| Tracking et images locales | Les indices visuels résolvent les ambiguïtés de la géométrie | Calcul, transfert et qualité des images |
| Classification et frontières explicites | Les limites des possessions méritent un objectif propre | Alignement et vraies possessions courtes |

Pour chacune, consigner :

1. La tâche et les conventions exactes de l'article.
2. Les entrées requises, notamment l'identité temporelle des joueurs et la disponibilité du ballon.
3. Le code, les poids, les données et leurs conditions d'utilisation effectivement disponibles.
4. La supervision nécessaire et celle que l'équipe peut légalement obtenir.
5. Les adaptations aux pistes instables, au bruit et aux absences du concours.
6. Les métriques d'origine, sans les présenter comme des prévisions de spellF1.
7. Un essai limité capable de décider si la piste mérite plus de travail.

Le choix « LightGBM + MS-TCN++ + Viterbi » reste crédible, mais ne devrait pas être considéré comme acquis avant comparaison de ces formulations. La priorité de recherche proposée est PathCRF, la prédiction directe avec séparation vivant–mort / équipe, puis la fusion tracking–images locales. Les approches à frontières explicites peuvent être testées dans plusieurs de ces stratégies.

Une combinaison finale peut aussi réunir des spécialistes dont les erreurs sont complémentaires. Ce choix doit venir d'une mesure des désaccords et des erreurs, plutôt que du nombre de modèles disponibles. Une moyenne de prédictions très corrélées ne constitue pas automatiquement un progrès.
