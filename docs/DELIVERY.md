# Livraison MYA : reproduction du CSV final

## Fichiers à remettre

- **`submissions/final/MYA.csv`** : la candidate définitive, 199 319 images.
- **`MYA.md`** : document technique, aussi copié dans le dossier final local.
- **Dépôt public** : sources, configurations, poids JSON, versions et commande.

`submissions/MYA.csv` conserve la **baseline historique**. Ce n'est pas le fichier
final à envoyer. Le dossier `submissions/final/` est ignoré par Git : les données
et prédictions du match ne doivent pas être publiées dans le dépôt.

## Installer l'inférence

Python **3.12.6**, CPU, Windows 64 bits vérifié. Aucun GPU. Les cinq dépendances
sont figées séparément des bibliothèques de notebook et de développement.
Depuis la racine du dépôt de l'équipe :

```powershell
py -3.12 -m venv .venv-inference
.venv-inference\Scripts\python.exe -m pip install -r requirements-inference.txt
.venv-inference\Scripts\python.exe mya.py --verify
.venv-inference\Scripts\python.exe mya.py --data-dir "C:\chemin\Projet foot" --fresh
```

Le Python doit être exactement 3.12.6. Le contrôle des versions bloque une
exécution avec un environnement différent. Le lanceur limite les bibliothèques
numériques à un thread avant d'importer NumPy. Sur un autre système ou CPU,
l'empreinte attendue du CSV doit toujours être vérifiée : une égalité sur une
machine ne démontre pas une égalité universelle entre toutes les architectures.

Seuls ces deux fichiers fournis sont nécessaires :

```text
Projet foot/
  tactical/
    BAR-ATH_tactical_atd.txt
    BAR-ATH_tactical_atd.xml
```

`--data-dir` accepte aussi directement `tactical/`. Aucun ancien cache, jeu DFL,
label public, vidéo, notebook, dépôt officiel ou connexion réseau n'est nécessaire
pour **prédire**, une fois les dépendances installées. Les poids et le contexte
sont inclus dans `release/model.json`. Ne pas relancer les jalons d'apprentissage
pour produire la soumission finale.

Sortie par défaut : `submissions/final/MYA.csv`. Options :

```powershell
.venv-inference\Scripts\python.exe mya.py --data-dir "C:\chemin\Projet foot" --output "C:\sortie\MYA.csv" --cache-dir ".cache\delivery\inference" --fresh
```

`--fresh` reparse les entrées brutes. Sans cette option, seul le cache validé du
tracking peut être réutilisé ; les caractéristiques et le décodage sont recalculés.
Les empreintes de contenu des entrées empêchent de réutiliser un cache différent.
Le rapport local est dans `<cache-dir>/inference.json`. Les positions originales
ne sont jamais interpolées.

## Contrats figés

Le modèle est la candidate J6 : trois têtes logistiques externes, contexte figé,
Viterbi statique, multiplicateur H/A=1 et multiplicateur D=2. Les probabilités et
métadonnées flottantes des observations passent par float32 avant le logarithme,
comme les archives J4/J6. Cette frontière numérique est nécessaire à la reproduction.

Le CSV est UTF-8 avec LF, `frame,label`, frames 0 à 199318 et labels H/A/D/X. Les
périodes sont décodées séparément ; X est conservé hors des intervalles évalués.
La zone D publiée dans la FAQ est imposée dans le décodeur. Il n'y a pas de durée
minimale, de recalage manuel ou d'ajustement au nombre de possessions.

SHA256 attendu :

```text
8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7
```

Le fichier temporaire est contrôlé avant remplacement. Une empreinte différente
bloque l'export et préserve tout fichier de sortie déjà présent. Les sources,
configurations et poids sont vérifiés avant de lire le tracking. Aucun Git ni
dépôt officiel n'est nécessaire pour ce contrôle.

Le validateur officiel reste un contrôle de livraison séparé, sans vérité terrain :

```powershell
.venv-inference\Scripts\python.exe ..\more-than-a-hack-2027\evaluation\validate_submission.py submissions\final\MYA.csv
Get-FileHash -Algorithm SHA256 submissions\final\MYA.csv
```

Ce validateur vérifie le format, pas la justesse des possessions. Le dépôt officiel
utilisé pour les mesures est figé par `official-revision.txt`. Sa présence n'est
requise que pour ces mesures et ce contrôle séparé.

## Évaluation finale externe

`src.final_test` est réservé au gel de livraison. Il permet J03WR9 uniquement,
les 19 conditions initiales et deux méthodes prédéfinies : candidate et baseline.
Les chargeurs de développement refusent toujours ce match. Les entrées XML DFL
contiennent aussi les états du fournisseur : le parseur les sépare dans une archive
de cibles qui n'est jamais transmise au constructeur de caractéristiques.
Les 19 prédictions sont signées avant ouverture de cette archive pour les mesures.

L'évaluation terminée est archivée sous `.cache/delivery/final-test/`. Une seconde
exécution de `--run` est refusée. `--show` relit le résultat sans nouvelle mesure.
Une interruption peut être reprise uniquement avec le même paquet et protocole.
Aucun réglage, repli ou choix de modèle n'est effectué sur ce résultat. Le test
n'est désormais plus un ensemble disponible pour une nouvelle sélection.

Les résultats agrégés et limites figurent dans `analysis/JALON_7_VALIDATION.md` et
`analysis/JALON_7_FINAL_TEST.json`. Les cinq minutes publiques BAR-ATH ne sont pas
ouvertes par cette étape.

## Préparer l'envoi

Le dossier local final contient le CSV et une copie de `MYA.md`. Vérifier ces
fichiers exacts et utiliser le lien du formulaire reçu par les membres inscrits.
Le formulaire n'est pas rempli et aucun fichier n'est envoyé automatiquement.
Le nom d'équipe doit rester MYA ; la référence officielle locale annonce le
17 novembre 2026, mais l'heure et le lien doivent être confirmés dans le courriel
récent des organisateurs. Aucune heure ou adresse de formulaire n'est inventée.
