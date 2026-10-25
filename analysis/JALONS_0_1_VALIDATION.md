# Validation des jalons 0 et 1

Réalisée le 25 octobre 2026 sur Windows, Python 3.12.6, dans le dépôt MYA.
Le code et la documentation sont versionnés ; les données privées et résultats
détaillés restent locaux et ignorés par Git. Le PDF a été renommé pour Windows,
car son ancien nom contenant `:` ne peut pas exister sur NTFS. Son contenu est identique.

## Livrables

- **Jalon 0 :** `docs/protocole.md`, `docs/sources.json`, contrôle des usages dans
  `src/source_policy.py`, nettoyage du notebook, commande de contrôle de publication.
- **Jalon 1 :** chemins configurables indépendants du nom du dépôt et sans
  écriture à l’import ; contrats tactique/TV ; parseur texte/XML strict ; masques
  de coordonnées et de vitesse ; conversions de positions et homographie ;
  cache signé par contenu et écriture atomique ; versions d’environnement et
  révision officielle figées ; notebook utilisant ces interfaces communes.

## Résultats observés

| Contrôle | Résultat |
|---|---|
| Suite synthétique `unittest` | 27 tests réussis |
| ATD tactique | 199 319 images, 46 pistes, XML et alignement validés |
| ATD TV | 164 488 images, 51 pistes, XML et alignement validés |
| Lecture directe / cache | Toutes les valeurs et tous les masques comparés égaux pour les deux sources, NaN équivalents |
| Homographies | Deux sources intégralement contrôlées |
| Smart Tagging | Bornes, casse, valeurs inconnues et convention demi-ouverte contrôlées |
| Notebook | 6 cellules de code exécutées ; aucune sortie dans le fichier partagé |
| Scoreur officiel | Import local vérifié à la révision figée |
| Dépendances | `pip check` réussi |
| Publication | Catégories de fichiers, compatibilité Windows et sorties de notebook contrôlées |

Les tests synthétiques couvrent notamment fichiers valides/tronqués/trop longs,
désordre, doublons et offsets, champs mal formés, infinis et NaN explicites,
XML avec namespaces et ordre de joueurs différent de celui des colonnes,
51 pistes TV, cache périmé/corrompu/incomplet, changement de source ou de parseur,
échec d’écriture atomique, géométrie, métadonnées d’unité et séparation des usages.

Les rapports détaillés restent ignorés dans `.cache/manifests/ingestion.json` et
`.cache/notebooks/`. Ils ne contiennent dans le manifeste aucun échantillon de
tracking ni label. Le notebook exécuté local peut contenir des tableaux privés et
ne doit pas être publié. Les tests partagés ne lisent que des fixtures synthétiques.

## Points à conserver pour la suite

1. **Unité de vitesse ambiguë :** le XML déclare kph, la prose officielle m/s.
   Les valeurs brutes restent intactes ; `speed_unit` et
   `speed_documentation_conflict` exposent le problème. Aucun seuil physique ni
   conversion automatique n’est adopté avant clarification.
2. **Erreur d’homographie négative :** valeur conservée dans la table brute,
   remplacée par NaN dans les erreurs utilisables et accompagnée d’un masque
   `reprojection_error_observed`. La validité géométrique reste indépendante.
3. **Aucun modèle évalué :** ces vérifications ne prouvent aucun gain de possession.
   Aucun label public n’est lu par la validation des entrées ; le diagnostic public
   du notebook est désactivé par défaut. La première chaîne CSV relève du jalon 2.
4. **Publication :** le contrôle automatique ne remplace pas une revue de tous les
   textes ; le nettoyage des sorties courantes ne réécrit pas l’historique Git.
5. **Cache :** chaque réutilisation relit les entrées pour le SHA-256 complet.
   Ce coût de lecture est assumé pour détecter aussi un changement de contenu à
   taille et date identiques. Un aperçu ne gagne que la mémoire, pas la validation.

## Refaire les contrôles

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m src.validate_inputs
.venv\Scripts\python.exe -m src.hygiene.repository_check
```
