# Jalon 7 — Livraison préparée et reproduction vérifiée

Réalisé le 29 octobre 2026. Aucun label public BAR-ATH n’est ouvert et aucun réglage n’est modifié après le test final.

## Fichiers prêts à remettre

- **`submissions/final/MYA.csv`**, distinct de la baseline historique `submissions/MYA.csv`.
- **`MYA.md`**, document technique, également copié dans le dossier final local.
- Sources, poids `release/model.json`, manifeste de gel et cinq dépendances d’inférence prêts à publier dans le dépôt.

La soumission au formulaire et la publication Git ne sont pas exécutées par le jalon local. Le lien et l’heure d’envoi restent à vérifier dans le courriel des organisateurs. Aucun formulaire ni destinataire n’est inventé.

## Inférence autonome

La commande `python mya.py --data-dir <dossier fourni> --fresh` utilise uniquement le TXT et le XML ATD tactiques. Les poids, le contexte d’activité, le prior et les réglages sont inclus dans `release/model.json`. Elle ne dépend d’aucun ancien cache, label, jeu DFL, dépôt officiel, Git ou accès réseau après installation des dépendances.

Le modèle est exactement la candidate J6 : têtes logistiques complètes, Viterbi statique, multiplicateurs H/A=1 et D=2, aucun minimum de durée. Le passage des observations en float32 avant logarithme préserve le contrat numérique des archives J4/J6. Les sources et le modèle sont contrôlés ; le fichier temporaire doit avoir l’empreinte attendue avant tout remplacement.

## Reproduction depuis des installations isolées

La copie isolée ne possède ni `.git`, ni dépôt officiel voisin, ni anciens caches, ni annotations, ni données externes. Les deux fichiers bruts sont fournis par liens physiques pour éviter une duplication volumineuse. Le Python neuf n’installe que NumPy, Pandas, python-dateutil, six et tzdata aux versions figées. Il s’agit d’un environnement neuf sur le même ordinateur Windows, pas d’un autre système matériel.

| Cas | Cache tracking réutilisé | Durée mesurée | SHA256 identique |
|---|---|---:|---|
| fresh environment, original raw inputs | non | 120.6 s | oui |
| isolated source copy, empty cache | non | 24.6 s | oui |
| isolated source copy, reused tracking cache | oui | 10.2 s | oui |

Les caractéristiques et le décodage sont recalculés dans chaque cas. L’écart de durée entre les exécutions peut refléter les caches disque/OS, la charge et la fréquence CPU ; il ne constitue pas une comparaison contrôlée du matériel. Le chemin CPU est vérifié sur Intel i7-1355U, environ 16 Gio de RAM, sans GPU.

SHA256 du CSV final :

```text
8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7
```

Les trois reconstructions possèdent les mêmes 199 319 lignes. Le fichier final et la copie isolée sont vérifiés séparément par le validateur officiel sans vérité terrain. La baseline et le CSV J6 conservent leurs empreintes d’origine. Voir [la preuve agrégée](JALON_7_REPRODUCTION.json).

## Dernier match externe : J03WR9

Le paquet et les conditions sont figés avant téléchargement des fichiers du dernier match. L’XML fournisseur contient à la fois tracking et états : le parseur sépare les observations et les cibles ; aucune cible n’entre dans le constructeur de caractéristiques. Les 19 prédictions candidate/baseline sont sauvegardées et signées avant ouverture de l’archive de cibles pour le score. Les chargeurs de développement restent verrouillés, y compris après cette évaluation.

Le test n’entraîne ni réapprentissage, ni recherche de réglages, ni choix de repli. Une seconde ouverture après résultat complet est refusée. Une interruption n’est reprenable qu’avec le même gel et les mêmes prédictions.

| Méthode | spellF1 moyen | macroF1 moyen | Rappel possessions <2 s | F1 frontières ±25 images |
|---|---:|---:|---:|---:|
| baseline | 0.2399 | 0.4209 | 0.0146 | 0.1677 |
| candidate | 0.4064 | 0.8288 | 0.0823 | 0.4573 |

Volume observé : **146,810 images**, deux périodes, 40 slots, terrain 105 × 68 m. Les 19 conditions du protocole produisent 38 lignes de mesures. Le temps complet du test (téléchargement, préparation, prédictions et score) est 164.1 s.

### Détail par condition

| Condition | spellF1 baseline | spellF1 candidate | macroF1 candidate |
|---|---:|---:|---:|
| clean | 0.3152 | 0.4741 | 0.8961 |
| short_gaps | 0.3069 | 0.4278 | 0.8786 |
| long_gaps | 0.1863 | 0.3830 | 0.8023 |
| spatial_noise | 0.3103 | 0.4420 | 0.8121 |
| crowded_gaps | 0.1878 | 0.3653 | 0.8172 |
| fragmented_tracks | 0.2584 | 0.4575 | 0.8853 |
| combined | 0.1650 | 0.3399 | 0.7549 |

Les graines répètent **un seul match**, pas 19 matchs indépendants. Le tracking DFL et les conventions de labels diffèrent potentiellement du concours ; les dégradations restent des tests de robustesse. Aucun score privé BAR-ATH ni classement n’est déduit. Les possessions courtes restent une faiblesse ; aucune durée minimale n’est ajoutée pour masquer cette limite. J03WR9 ne peut plus être présenté comme un nouveau test vierge dans une future sélection. Voir [les mesures détaillées](JALON_7_FINAL_TEST.csv) et [le registre complet agrégé](JALON_7_FINAL_TEST.json).

## Contrôles

- **192 tests** : intégrité poids/sources, versions, quantification float32, coût final, export atomique, refus des mauvais CSV, refus d’un test terminé et absence d’ouverture de cibles sans instantané complet.
- Notebook : les 40 cellules des explorations J0–J5 restent inchangées ; la lecture J6 utilise les empreintes historiques et la section J7 lit les preuves sans relancer les tests. Total : 46 cellules dont 30 cellules de code. Les sorties partagées sont vides.
- Les contrôles J3 sont rejoués après rafraîchissement des empreintes avec le même contexte appris ; aucun ajustement du modèle.
- Le validateur officiel vérifie les octets du CSV final, sans annotations du match. Les périodes, la zone D connue et les X hors périodes sont conservés.
- Les résultats, poids et sources gardent le même gel entre reproduction et test final. Les données, caches et prédictions par image restent ignorés par Git.

## Ce qui reste hors de cette étape

Le dossier est prêt pour l’envoi humain. Le dépôt doit encore recevoir le commit/push J7 quand demandé ; les fichiers privés du dossier final ne doivent pas être poussés. L’envoi au formulaire n’est pas réalisé. Les bonus (reconstruction de ballon, vision, modèles temporels profonds, fusion TV) ne sont pas des conditions de cette livraison et ne sont pas présentés comme implémentés.

Instructions complètes : [docs/DELIVERY.md](../docs/DELIVERY.md). Document à remettre : [MYA.md](../MYA.md).
