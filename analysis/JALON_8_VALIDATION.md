# Jalon 8 — Protocole V2 et préparation des bonus

Réalisé le 2 novembre 2026. **Préparation uniquement : aucun nouveau modèle entraîné, aucun score de possession calculé.**

## Publication et préservation de C0

Le plan et le diagnostic de référence ont été commités et poussés sur `main` : `a913db3248a13b355690f4b521a3dd2e5c01c820`. Les travaux J8 sont isolés sur la branche locale **`bonus-phase2`**. Le tag local **`delivery-v1`** conserve `e5d40baa352ef70feacb7125e5ca667629da58ca`. Aucun module de la livraison V1 ni son paquet de poids n’a été modifié.

CSV C0 préservé : `8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7`. Le paquet est toujours vérifié par `mya.py --verify`. La baseline J2 et le marqueur de consommation du test J03WR9 sont conservés. Les travaux J8 restent locaux tant que leur commit/push n’est pas demandé.

## Réalisations

- Contrats pour observations, positions imputées/incertitude et scores, avec masques, unités, périodes et provenance.
- Garde-fous des plis : le modèle, le contexte, le prétraitement, le prior et le calibrateur excluent le match évalué. Les poids publiés à quatre matchs ne peuvent pas servir de comparateur C0-OOF.
- Protocole figé : huit familles, trois graines sauf propre, soit **22 conditions par match**.
- Budgets : **48 configurations** au maximum, 48 h CPU et 24 h de jobs GPU. Le registre atomique exige une grille scellée avant les essais et conserve les dépassements réels.
- **Huit configurations J9** exactes scellées, sans entraînement. Les autres grilles devront être enregistrées avant leur bloc.
- Profil des capteurs à partir des observations des quatre matchs d’apprentissage et de BAR–ATH complet sur ses périodes évaluées, sans annotations et sans découpe de la fenêtre publique.
- Validation des **88 jeux d’observations** des quatre matchs : comptes de trous exacts par période, déterminisme, copie native inchangée et chronologie préservée.

## Suite V2 enregistrée

| Cas | Absence cible | Défaut |
|---|---:|---|
| S0 clean | 0 % | aucun trou ajouté |
| S1 short_gaps | 20 % | [5, 25] |
| S2 long_gaps | 41 % | [100, 500] |
| S3 context_gaps | 41 % | [25, 150] |
| S4 severe_long_gaps | 60 % | [100, 500] |
| S5 visible_corruption | 0 % | aucun trou ajouté |
| S6 combined_41 | 41 % | [25, 250] |
| S7 combined_60 | 60 % | [25, 250] |

La suite inclut aussi des positions livrées mais erronées : bruit balle 0,25 m, joueurs 0,15 m, biais balle par blocs de 125 images de sigma 0,5 m, bursts aberrants sur 1 % des images de sigma 4 m. Les combinaisons ajoutent réassignation au sein des équipes et perte de joueurs par blocs de 250 images, probabilité 0,10. Ce sont des paramètres de stress fixés avant tout score, pas des erreurs estimées comme vraies sur BAR–ATH.

Le masque S3 utilise densité de joueurs et distance aux lignes, jamais D/H/A. Les vérités de corruption restent dans l’audit et ne sont pas passées au modèle. Le taux demandé est total par période, à une image d’arrondi près ; les absences natives ne sont pas comblées.

**S41** moyenne équitablement graines, cas S2/S3/S6 puis matchs. **R4** équilibre les quatre niveaux 0/20/41/60 %. L’agrégateur vérifie toute la couverture ; ces formules sont testées sur des fixtures, pas mesurées sur des candidats au J8. La confirmation J03WPY/J03WQQ n’est pas ouverte avant la liste fermée J18. J03WR9 et le public ne participent pas à la sélection.

## Profil des observations

| Source | Ballon manquant | Médiane des trous | Ballon hors terrain parmi les positions présentes |
|---|---:|---:|---:|
| J03WMX | 0.00 % | — | 30.89 % |
| J03WN1 | 0.00 % | — | 32.98 % |
| J03WOH | 0.00 % | — | 29.67 % |
| J03WOY | 0.00 % | — | 27.56 % |
| BAR-ATH | 40.69 % | 10.72 s | 4.19 % |

BAR–ATH contient 150 trous dans les périodes évaluées ; le maximum est 221.48 s. Les blocs synthétiques se recouvrent et peuvent former des trous plus longs, mais la suite ne prétend pas reproduire parfaitement cette longue queue.

Le fort écart de disponibilité des coordonnées hors terrain est un indice de différence de capteur à étudier : il ne prouve pas la cause des erreurs D et ne transforme pas une position extérieure en label D. Les vitesses du profil sont des déplacements apparents entre observations adjacentes, sans vitesse livrée ni correction d’identité. Les statistiques de joueurs tiennent compte du nombre de slots livrés ; il ne s’agit pas d’une vérité terrain de qualité.

## Audit de nouvelles sources

| Source | Résultat J8 |
|---|---|
| [SkillCorner Open Data](https://github.com/SkillCorner/opendata) | Match 2017461 réservé sur sa seule identité publique ; non admis. Tracking documenté à 10 Hz, possession et phases décrites, mais couverture D/provenance/droits/cadence à établir. |
| [Metrica Sample Data](https://github.com/metrica-sports/sample-data) | Tracking/événements documentés ; pas de preuve suffisante de labels denses H/A/D compatibles. Non admis. |
| [SoccerNet GSR](https://github.com/SoccerNet/sn-gamestate) | Tâche de localisation/identification des joueurs ; pas un benchmark dense H/A/D établi. Non admis. |
| [PathCRF](https://github.com/hyunsungkim-ds/pathcrf) | Reprend les mêmes sept matchs DFL ; pas de nouveau test et chevauchement des poids à auditer. |

Les documents et métadonnées d’identité ont été archivés localement avec SHA256 ; aucun nouveau tracking, label ou checkpoint n’est téléchargé. **Aucun nouveau test aveugle n’est encore admis.** Cette limite n’empêche pas les essais internes, mais devra rester explicite au J18. Un changement d’admission exige un protocole déclaré avant l’usage des nouvelles données.

## Matériel et coût de la préparation

Machine auditée : Intel i7-1355U, 10 cœurs/12 processeurs logiques, environ 16 Gio RAM, Intel Iris Xe. Aucun CUDA/NVIDIA vérifié ; les bonus GPU restent conditionnels. Aucune dépendance supplémentaire installée.

Commande de précontrôle : 41.2 s murales, 40.1 s CPU, comptées au budget (hors audit documentaire, tests et rédaction). Aucun temps GPU. Configurations effectivement commencées : **0/48**. Les huit réglages J9 sont seulement scellés.

## Vérifications et suite

**211 tests passent**, dont 19 nouveaux tests J8 : 22 conditions, exactitude des masques, séparation des périodes/RNG, non-mutation, équipes non échangées, aucun point ressuscité, audit non exposé au modèle, accès de données, provenance hors pli, moyennes pondérées et budget concurrent/atomique. Une exécution du validateur de suite sur fixtures refuse toute tentative de charger les cibles/publiques ou de fitter le modèle.

Les profils et les 88 validations réelles ne lisent aucune archive de cibles, aucun label public, aucune observation de confirmation ni le test consommé. Ils ne constituent donc **pas un benchmark de performance du modèle**. Le J9 reste à implémenter et à entraîner avec ses sous-plis de calibration.

Prochaine étape : J9, comparaison interne des huit variantes d’augmentation, qualité et calibration. Le registre doit enregistrer chaque configuration avant son premier ajustement, les sous-plis et tous les coûts. Ne pas consulter la confirmation après chaque variante.

Guides : [protocole et commandes](../docs/BONUS_V2.md), [plan phase 2](Implementation_Plan_Phase_2_Bonus.md). Preuves agrégées : [registre](JALON_8_REGISTRATION.json), [profils](JALON_8_SENSOR_PROFILES.json), [suite validée](JALON_8_SUITE_VALIDATION.json), [résumé du précontrôle](JALON_8_PREFLIGHT.json), [tableau des stress](JALON_8_STRESS_CHECKS.csv).

Notebook vérifié : **49 cellules, dont 32 cellules de code exécutées**, et les 46 sources précédentes conservées sans changement. Les nouvelles cellules ne font que lire les preuves agrégées ; aucun précontrôle, entraînement ou score n’est lancé à l’ouverture.
