# Restauration de l'exploration du notebook

Réalisation du **27 octobre 2026**, à la demande de l'équipe, depuis le contenu
fonctionnel du notebook au commit `94b4435`. Les rubriques d'origine sont
réintégrées au notebook courant, avec les chargeurs contrôlés et les interfaces
des jalons 3 et 4. Les anciennes sorties privées ne sont pas restaurées.

## Correspondance des cellules historiques

| Cellules d'origine | Rubrique rétablie | Adaptation |
|---|---|---|
| 0–5 | Objectifs, imports, style, chemins et constantes | Racines déduites du package et constantes communes, sans chemin personnel |
| 6–9 | Chronologie, contrôles empiriques et frises | Intervalles officiels demi-ouverts, statistiques recalculées par plage, tags de coup d'envoi et distance au centre |
| 10–12 | Exploration et distributions du Smart Tagging | Chargeur commun, casse normalisée, inconnus conservés et remises en jeu descriptives |
| 13–14 | Homographie : distribution et évolution des erreurs | Erreurs négatives exclues, validité de matrice distinguée de la qualité de reprojection |
| 15–17 | Tracking et absences du ballon | Mapping XML, supports par équipe, trous analysés séparément par période et censure conservée |
| 18–20 | Répartition, durées et frise des labels publics | Diagnostic explicite facultatif, bornes communes et segments calculés depuis les labels fournis |
| 21–22 | Visualiseur spatial 2D | Positions métriques déjà validées, accès direct à une image vidéo, équipes XML et ballon manquant conservé |
| 23–24 | Calcul et graphiques des références officielles | Commande partagée de diagnostic, nombres de possessions calculés et agrégats du match complet publiés dans EVALUATION.md |
| 25 | Synthèse stratégique | Constats actualisés et séparation entre mesures, hypothèses et étapes futures |

Chaque cellule adaptée conserve une référence à ses cellules d'origine dans ses
métadonnées. Les 26 rôles historiques sont couverts. La structure actuelle compte
**37 cellules, dont 24 cellules de code**, comprenant également le contrôle TV,
les caractéristiques du jalon 3 et les scores du jalon 4.

## Utilisation

Ouvrir `analysis/data_exploration.ipynb` avec le noyau **Python (MYA foot)**, puis
exécuter les cellules dans l'ordre. Les deux options sont regroupées dans la
première cellule de code :

- `RUN_PUBLIC_DIAGNOSTIC=False` par défaut : mettre à `True` pour l'exploration
  des cinq minutes publiques et la reproduction des références publiées ; aucun
  apprentissage, calibration ni sélection de variante n'est effectué.
- `VERIFY_BROADCAST=False` par défaut : mettre à `True` pour vérifier le tracking
  TV sur sa chronologie propre, sans synchronisation ou fusion implicite.

`plot_frame_situation(image_video, ax=None, title_prefix="", show_slots=False)`
permet de visualiser une image au choix. Les indices de pistes affichables ne
sont pas des dossards. Les exemples reposent sur les seules bornes officielles,
sans attribution humaine de contact, d'engagement ou de possession.

L'exploration initiale fonctionne sans avoir entraîné le modèle. Les sections
des jalons 3 et 4 affichent leurs artefacts lorsqu'ils existent ; sinon elles
indiquent les commandes de génération et laissent l'exploration fonctionner.

## Vérification

- Notebook exécuté intégralement en mode normal : **24 cellules de code**.
- Copie locale exécutée avec diagnostic public et contrôle TV activés : mêmes
  cellules exécutées, quatre scores officiels de référence reproduits.
- Visualiseur vérifié sur l'alignement vidéo, les coordonnées manquantes, les
  copies indépendantes et le refus des indices hors limites.
- Vérification que chaque trou reste dans sa période et que la somme de ses
  longueurs correspond aux observations absentes.
- Repli en absence d'artefacts J3/J4 vérifié dans le noyau.
- **123 tests du projet réussis**, dépendances cohérentes et contrôle de
  publication réussi. Aucun module de prédiction n'a été changé pour cette
  restauration ; modèle et soumission de référence restent inchangés.

Les copies exécutées et leurs tableaux/graphiques restent uniquement sous
`.cache/notebooks/restoration/`. Le notebook partagé est sans sorties, compteurs
ou pièces jointes. Les coefficients ajustés, données, positions et prédictions
par image restent exclus du dépôt.
