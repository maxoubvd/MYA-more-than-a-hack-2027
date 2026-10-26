# Jalon 3 — observations et caractéristiques fiables

Réalisation du **26 octobre 2026**. Le jalon transforme les observations
automatiques en matrices exploitables par le futur modèle. Il n'ajoute aucune
nouvelle prédiction de possession et ne revendique aucun gain de spellF1.

## Résultat livré

| Source | Matrice complète | Chronologie |
|---|---:|---|
| Tactique du concours | 199 319 × 116 | Images vidéo d'origine ; toutes les colonnes masquées hors périodes évaluées |
| DFL J03WMX, apprentissage | 145 967 × 116 | Deux périodes conservées ; dimensions propres au terrain |

Les 116 colonnes couvrent qualité du suivi, trous, géométrie collective,
proximités par équipe, mouvements relatifs, contexte passé/futur, indices physiques,
contacts candidats, Smart Tagging et qualité de l'homographie. Les unités, groupes
et conventions sont dans [FEATURES.md](../docs/FEATURES.md) et le
[schéma sans valeurs](../docs/feature_schema.json).

La commande `python -m src.build_features --source all` construit les matrices,
leurs masques et leur provenance. `python -m src.validate_features` vérifie les
archives et les régressions d'intégration. Le notebook relit ces mêmes fichiers
avec `load_matrix` ; il ne réimplémente pas les caractéristiques.

## Vérifications réalisées

- **93 tests automatisés réussis**, dont 27 nouveaux tests du jalon 3 : mouvement
  analytique et unités, trous et censure, ruptures et mi-temps, doublons, égalités
  de proximité et permutations, tags offensifs/défensifs contradictoires, N/A,
  fenêtres temporelles, séparation observations/cibles et corruption d'archive.
- Construction intégrale des deux matrices, masques égaux à la finitude des
  valeurs, absence d'infinis et **égalité après sauvegarde/relecture**.
- Schéma identique entre sources. Tags, homographie et orientation indisponibles
  dans l'interface externe laissés manquants ; provenance des informations
  tactiques contrôlée. Hors période tactique, aucun indice actif n'est conservé.
- **19 couples scénario/graine figés** vérifiés sur 2 048 images du seul match
  externe d'apprentissage : données propres, trous courts/longs, trous en zone
  dense, bruit, fragmentation et combinaison. Chaque cas vérifie masques,
  absence d'infinis et invariance aux permutations.
- Invariance également vérifiée sur un extrait tactique de 2 048 images. Tolérance
  numérique : `rtol=1e-5`, `atol=1e-4`, due aux agrégations flottantes.
- Aucune cible externe ni annotation publique BAR-ATH lue par la construction ou
  sa validation. Le test externe final reste verrouillé ; aucune sélection de
  variante ni aucun nouveau score de possession dans ce jalon.
- Signature du CSV de référence du jalon 2 inchangée :
  `faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797`.
  Une nouvelle génération séparée de 199 319 lignes reproduit exactement cette
  signature et passe la validation intégrée du format.
- Notebook exécuté avec succès : **8 cellules de code**, copie exécutée conservée
  uniquement dans le cache local, version partagée sans sorties ni compteurs.
- Dépendances cohérentes (`pip check`), contrôle de publication réussi et aucune
  erreur d'espacement relevée par `git diff --check`.

Les manifestes détaillés, les matrices et les sorties exécutées du notebook restent
dans `.cache/features/`, exclu de Git. Le schéma publié décrit les colonnes sans
positions, séquences, événements ni autres valeurs privées.

## Choix et limites

Les vitesses proviennent des positions métriques à 25 Hz, pas des vitesses XML
dont l'unité est ambiguë. Lissage local et dérivées restent dans les fragments
continus, sans interpolation. Une rupture d'identité sans saut observable peut
échapper à la détection. La pondération des doublons est une précaution symétrique,
pas une reconstruction des identités ; tous les joueurs visibles sont inclus,
potentiellement les gardiens aussi.

Deux descripteurs sont ajustés sans labels sur les observations de J03WMX : un
mélange à deux modes de vitesse collective et un quantile élevé d'accélération.
Le premier donne un indice de faible activité, **pas une probabilité de ballon
mort**. Le second repère des contacts candidats avec proximité dans une fenêtre
de ±2 images du même fragment ; bruit et rebonds peuvent aussi produire un pic.
Ni une sortie en projection 2D, ni un tag de reprise ne décide automatiquement D.

Les paramètres sont initiaux et publiés dans `configs/features.json`. Leur intérêt
pour la tâche, leur transfert entre fournisseurs et les associations avec H/A/D
restent à évaluer hors des annotations publiques du concours. Ces contrôles de
robustesse sont fonctionnels et ne constituent pas une mesure de précision sur
les matchs réservés à la validation.

## Suite

Le jalon 4 peut commencer avec une interface commune, masques et provenance :
scores vivant/mort séparés des scores d'équipe, référence par règles puis
comparaison de modèles sur données externes autorisées. Le jalon 5 ajoutera la
mémoire et le décodage temporel. Les bonus de reconstruction, pitch control et
fusion TV restent indépendants et ne sont pas requis pour exploiter cette matrice.
