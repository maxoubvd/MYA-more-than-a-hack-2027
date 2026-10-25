# Jalon 2 — première chaîne de référence complète

Réalisé le 25 octobre 2026, après les jalons 0 et 1. Le code et la documentation
sont versionnés. Les données privées, CSV générés et rapports détaillés restent
locaux et ignorés par Git ; aucun envoi aux organisateurs n’est effectué.

## Résultat

Le fichier `submissions/MYA.csv` contient exactement 199 319 lignes de données,
avec les colonnes `frame,label`, les indices 0 à 199318 et uniquement H/A/D/X.
Il est accepté par `evaluation/validate_submission.py` du dépôt officiel.

Deux exécutions complètes, l’une depuis le cache validé et l’autre avec relecture
des fichiers bruts, ont produit exactement les mêmes octets. Empreinte SHA-256 :

```text
faa469cebf4e4bb25e59e03304b8cd45ebf65c8df7eeff69a4a393ed4a516797
```

## Méthode figée avant diagnostic

1. Lire uniquement le tracking tactique et ses métadonnées, par les chargeurs du
   jalon 1. Aucun label public ou privé, Smart Tagging, homographie ou vidéo
   n’intervient dans cette première prédiction.
2. Calculer les distances joueur–ballon avec x/y mis à l’échelle du terrain
   (105,3 × 68 m). Les vitesses ne sont pas utilisées. Un ex æquo exact prend la
   première piste dans l’ordre de colonnes du XML.
3. Attribuer l’équipe du joueur le plus proche lorsque ses x/y et ceux du ballon
   sont présents. Sinon, prédire D par convention de la référence officielle.
   Cette hypothèse est volontairement faible : une absence de ballon ne prouve
   pas un arrêt de jeu.
4. Appliquer un vote centré de **±50 images**, donc jusqu’à **101 images**,
   séparément à chaque mi-temps. Seuls H et A votent ; en cas d’égalité, H gagne.
   Sans vote H/A, rendre D. Ce mécanisme reproduit la référence officielle ;
   ce n’est pas un vote majoritaire sur trois classes.
5. Mettre X hors des périodes évaluées. Mettre D sur `[110808,113742[`, information
   officiellement publiée. Les masques sont appliqués avant puis après le vote.

La fenêtre ±50 vient de la référence officielle publiée `baseline_smooth50` et
du plan, pas d’une sélection sur les cinq minutes publiques. Aucun paramètre n’a
été modifié en réponse au diagnostic public.

## Début de période et abstention

Le vote n’accède jamais à la mi-temps précédente ni aux images non évaluées.
Au début d’une période, la fenêtre est limitée à cette période et peut utiliser
des observations futures, puisque le traitement est hors ligne. Sans aucune
observation d’équipe dans cette fenêtre, le résultat est D par défaut.

L’option explicite `--missing-label X` remplace ce repli par une abstention.
Elle n’est pas sélectionnée ou évaluée ici comme une variante concurrente.
Les observations voisines H/A peuvent toujours fournir un vote. Aucun maintien
explicite d’une étiquette à travers un trou ou entre les périodes n’est ajouté.

Sur les images évaluées, X compte comme une erreur pour macroF1. Le scoreur
remplit les X pour les métriques temporelles à l’intérieur de chaque bloc de
référence (propagation vers l’avant, puis remplissage du début avec la première
étiquette connue). Ce remplissage appartient au scoreur, pas au CSV exporté ;
un bloc entièrement X reste sans réponse. Il ne garantit aucun gain macroF1.

## Vérifications

- **50 tests synthétiques réussis** au total, dont 23 pour le jalon 2 : proximité
  dans un terrain rectangulaire, valeurs manquantes, égalités, fenêtres et bords,
  séparation des périodes, masques officiels, abstention, refus des labels mal
  formés, export déterministe/atomique et gel des candidats avant diagnostic.
- Validation du fichier final par le module officiel et son script autonome.
- Deux générations complètes comparées octet par octet, cache puis lecture brute.
- Le calcul sans masques MYA reproduit les quatre CSV algorithmiques officiels :
  **0 image différente** pour raw, smooth25, smooth50 et smooth125. Cette
  comparaison porte sur des sorties automatiques publiques, sans vérité terrain.
- Le scoreur officiel a été exécuté sur les quatre fichiers fournis, à la
  révision indiquée dans `official-revision.txt`. Ses rapports sont conservés
  localement sous `.cache/jalon2/public_diagnostic/`.

| Référence fournie | spellF1 public reproduit | macroF1 public reproduit |
|---|---:|---:|
| raw | 0,0378 | 0,5972 |
| smooth25 | 0,2868 | 0,6200 |
| smooth50 | 0,3256 | 0,6207 |
| smooth125 | 0,4242 | 0,5812 |

Le CSV MYA gelé avant lecture des labels donne également **spellF1 = 0,3256** et
**macroF1 = 0,6207** sur le diagnostic public. C’est une vérification de référence,
pas une mesure de progrès ni une preuve de performance sur le match complet.
Aucune comparaison ne sert à adopter une autre fenêtre.

## Commandes de reproduction

Depuis la racine du dépôt, avec les données configurées selon le README :

```powershell
.venv\Scripts\python.exe -m src.pipeline --output submissions/MYA.csv
```

Le programme valide le fichier temporaire avec le module officiel avant de
remplacer le CSV final. Les octets sont UTF-8 avec fins de ligne LF, sans index
supplémentaire ni horodatage. Un manifeste ignoré dans `.cache/runs/` conserve
les réglages, les signatures d’entrée, la révision officielle, la révision Git
MYA et les empreintes des sources Python réellement exécutées, y compris si
les changements n’ont pas encore été commités.

Pour refaire la vérification de reproductibilité :

```powershell
.venv\Scripts\python.exe -m src.pipeline --output .cache/jalon2/MYA.second.csv --no-cache
(Get-FileHash submissions/MYA.csv -Algorithm SHA256).Hash -eq (Get-FileHash .cache/jalon2/MYA.second.csv -Algorithm SHA256).Hash
```

Pour le diagnostic uniquement, après gel du CSV et de ses réglages :

```powershell
.venv\Scripts\python.exe -m src.diagnostics
.venv\Scripts\python.exe -m src.diagnostics --submission submissions/MYA.csv
```

La première commande reproduit seulement les références officielles ; la seconde
inclut un unique candidat déjà muni de son manifeste. Les prédictions n’importent
pas ce module de diagnostic et ne lisent jamais les labels publics. Les rapports
détaillés, transitions et CSV restent ignorés par Git.

## Limites et suite

Cette version ne sait pas distinguer correctement un ballon perdu par le tracking
d’un ballon réellement mort, et la proximité n’implique pas un contrôle du ballon.
Le vote peut effacer des possessions courtes. Aucun apprentissage n’est réalisé.
Le diagnostic public ne sert pas à corriger ces faiblesses par des seuils adaptés
à ce match. Les jalons 3 à 5 apporteront des observations et un modèle temporel
plus pertinents ; leur adoption devra respecter le protocole de validation externe.
