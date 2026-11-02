# Plan d’implémentation — phase 2 : bonus, comparaison et nouvelle livraison

> **Mise à jour du 2 novembre 2026.** Jalons 0–8 réalisés ; jalons 9–19 à commencer. J8 a figé le protocole et validé les observations, sans entraîner ni sélectionner de nouveau modèle. Voir [les preuves J8](JALON_8_VALIDATION.md). Il complète [le plan du socle](Implementation_Plan.md).
>
> **Objectif :** tester les bonus, conserver les apports externes mesurés, puis comparer les candidats et repréparer une soumission reproductible. **J18 = nouvel équivalent du jalon 6. J19 = nouvel équivalent du jalon 7.** Si aucun bonus ne convainc, conserver la livraison actuelle.

## 1. Référence et objectifs

La référence **C0** est la version J7 au commit `e5d40baa352ef70feacb7125e5ca667629da58ca` : modèle logistique complet, Viterbi statique, coûts H/A=1 et D=2. Son CSV SHA256 :

```text
8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7
```

Sur les deux matchs externes de confirmation et les 19 conditions historiques, C0 obtient macroF1 **0,8340** et spellF1 **0,4280** en moyenne. Sur J03WR9, ouvert après gel : **0,8288 / 0,4064**. Les possessions courtes restent peu reconnues. Le diagnostic public a montré une fragilité de D ; il ne devient pas un objectif de réglage.

Trois faits doivent rester distincts :

- Les sept matchs DFL natifs fournissent des coordonnées du ballon à toutes les images. Les absences des essais sont artificielles.
- BAR–ATH a **40,69 %** de coordonnées manquantes sur les périodes évaluées, mais **11,80 %** sur les cinq minutes publiques. L’absence de ballon ne suffit donc pas à expliquer le résultat public.
- Le score historique DFL mélange des conditions à 0 %, 20 % et 41 % d’absences ; ce n’est pas un score exclusivement mesuré à 41 %.

Priorités : robustesse de D, vraies possessions courtes, frontières et information pendant les trous. Un bon RMSE de trajectoire ou une hausse de macroF1 ne suffit pas si spellF1 se dégrade. Les causes de l’écart DFL/BAR–ATH restent des hypothèses à vérifier sur d’autres matchs. Voir [les mesures détaillées](DIAGNOSTIC_PUBLIC_JALON_7.md).

## 2. Tableau des nouveaux jalons

| Jalon | Travail | Origine / priorité | Livrable |
|---|---|---|---|
| **J8 — réalisé** | Préserver C0 et figer le protocole V2 | Indispensable | Sources/budgets figés, 88 validations d’observations, aucun entraînement |
| **J9** | Renforcer D et le transfert entre capteurs | Priorité 1 | Observations/calibration évaluées hors BAR–ATH |
| **J10** | Imputation courte et contrôle géométrique | Ancien B1 | Imputation distincte des observations et gain de tâche mesuré |
| **J11** | Durées souples et états internes | Ancien B2 | HSMM / extension structurée face au Viterbi |
| **J12** | Frontières apprises | Ancien B3 | Petite branche de frontières ou TCN |
| **J13** | Joueurs et contexte sans reconstruire la balle | Ancien B4 | Encodeur invariant face au collectif actuel |
| **J14** | PathCRF / TranSPORTmer / BallRadar | Ancien B5, conditionnel | Audit des trois pistes et essai d’une famille recevable |
| **J15** | Alignement et fusion TV | Ancien B7, conditionnel | Correspondances avec rejet et bénéfice validé |
| **J16** | Gestes visuels, détection ciblée, diffusion | Anciens B6/B8, conditionnels | Trois essais distincts selon données et moyens |
| **J17** | Fusion de spécialistes utiles | Ancien B8, conditionnel | Fusion limitée de scores et ablations |
| **J18** | Comparer, décider et geler | **Équivalent J6** | Rapport comparatif et choix final, éventuellement C0 |
| **J19** | Reproduire et repréparer la soumission | **Équivalent J7** | Paquet vérifié, CSV et document technique |

Statuts autorisés : **à tester**, **en cours**, **testé et retenu**, **testé et écarté**, **non testé : condition manquante**. Un audit ou une absence de données ne compte pas comme un test de performance. Tous les bonus passent par un audit ; tous ne doivent pas être empilés ou entraînés lourdement.

Ordre recommandé : J8 → J9 → essais J10–J13 → pistes recevables J14–J16 → J17 si utile → **J18 et J19 dans tous les cas**. Une piste arrêtée ne bloque pas la comparaison et la livraison.

## 3. Règles pour toute la phase

Les cinq minutes publiques servent au diagnostic technique, jamais à apprendre, calibrer, choisir un seuil ou classer les nouvelles variantes. Aucun score public n’entre dans la sélection. Aucun label humain, événement tiers ou correctif manuel de BAR–ATH n’entre dans l’apprentissage. Les observations non annotées peuvent décrire localement les capteurs ; les corrections doivent venir d’un algorithme. Ces contraintes reprennent les [règles officielles consultées le 2 novembre](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/RULES.md).

Conserver H/A/D/X, les deux chronologies, les périodes et contraintes officielles. Ne pas assimiler un slot à un joueur stable, une position absente à D, un contact à un contrôle ou une balle stationnaire à un coup de sifflet. L’observation D reste séparée de l’attribution H/A ; le décodeur peut ensuite combiner ces scores.

Données privées, images, trajectoires, embeddings par image et CSV restent locaux et ignorés. Aucun extrait privé n’est envoyé à un LLM hébergé. Préparer pour publication seulement les sources, droits, paramètres externes et agrégats. Garder les dépendances des bonus dans un environnement séparé de l’inférence C0.

## 4. J8 — Préserver C0 et construire l’évaluation V2

### 8.1. Référence, code et interfaces

- Conserver commit, `release/`, CSV et empreintes C0. Prévoir un tag et une branche ou un worktree d’expériences ; ne pas modifier le paquet C0 pour accepter un autre CSV.
- Préparer `src/bonus/`, `configs/bonus_v2/` et `.cache/bonus_v2/`. Ces emplacements et les interfaces de préparation sont créés au J8 ; les modèles des jalons suivants restent à implémenter. Éviter de modifier les modules dont dépend C0 ; utiliser des adaptateurs ou une copie versionnée.
- Sortie commune : scores H/A/D, masques, frame IDs, period IDs, cadence, qualité et provenance. Séparer positions **observées**, **imputées** et incertitude. Chaque colonne a un nom, une unité et une règle de disponibilité.
- Vérifier repères, dimensions natives, index, fragments et unités. Les vitesses livrées ne remplacent pas les dérivées de coordonnées sans justification.

### 8.2. Matchs disponibles et test déjà consommé

| Données | Usage phase 2 |
|---|---|
| J03WMX, J03WN1, J03WOH, J03WOY | Apprentissage et validation interne par match |
| J03WPY, J03WQQ | Confirmation de développement limitée ; déjà connus |
| **J03WR9** | **Résultat historique C0 uniquement ; exclu de l’apprentissage, du réglage et du choix des bonus** |
| BAR–ATH, observations seules | Diagnostic de capteurs et traitement automatique local |
| BAR–ATH, cinq minutes annotées | Hors sélection ; diagnostic technique éventuel après gel |
| Nouveaux matchs externes recevables | Répartition par match figée avant consultation des résultats |

**Ne pas supprimer la consommation du test et ne pas rouvrir J03WR9 comme s’il était vierge.** Chercher au J8 un ou plusieurs nouveaux matchs avec droits vérifiables et labels compatibles. Vérifier leur identité réelle : un autre fichier, extrait ou prétraitement du même match ne constitue pas un nouveau test.

Auditer accès pour les organisateurs, droits, provenance et définition des labels, couverture H/A/D, cadence et recouvrements. Des événements de passe seuls ou nos pseudo-labels ne forment pas une vérité terrain complète vivant/mort. Des annotations d’autres matchs sont possibles avec provenance et accès documentés.

Si un test inédit existe, le réserver **avant** les essais sans parcourir ses résultats pour choisir les bonus. Sinon, poursuivre validation interne et confirmation connue en l’annonçant : le rapport ne revendiquera **aucun nouveau test aveugle**. Cette absence ne justifie pas de recycler J03WR9 ou le public BAR–ATH.

### 8.3. Suite de robustesse V2

Conserver les 19 conditions historiques pour comparaison rétrospective. Ajouter la suite V2 suivante, trois graines 20261102/03/04 sauf S0 propre avec une seule : **22 conditions par match**.

| Cas | Ballon manquant | Défaut étudié |
|---|---:|---|
| S0 | 0 % | Tracking natif |
| S1 | 20 % | Trous courts |
| S2 | 41 % | Trous longs |
| S3 | 41 % | Trous corrélés à la densité et aux lignes |
| S4 | 60 % | Trous longs sévères |
| S5 | 0 % | Positions présentes mais bruitées, biaisées ou aberrantes |
| S6 | 41 % | Trous + erreurs spatiales + ruptures/pertes de pistes joueurs |
| S7 | 60 % | Même combinaison, plus sévère |

Figer au J8 distributions exactes des durées, amplitudes et corrélations avant les scores. Décrire les observations BAR–ATH complètes sans labels : durée/censure des trous, qualité des coordonnées, joueurs observés et activité. Ces agrégats peuvent informer une simulation ; ils ne la valident pas. Ne pas adapter les masques au résultat des cinq minutes publiques.

Les erreurs synthétiques dépendent des **observations uniquement**, jamais des labels D ou H/A. Ne pas traverser une mi-temps. La vérité terrain externe reste séparée et identique entre méthodes.

**Mesure principale proposée, S41 :** spellF1 officiel sur les séquences complètes S2/S3/S6, moyenne des graines puis des familles puis des matchs, à poids égaux. Le niveau 41 % vient du profil non annoté du match complet, pas d’un score public.

**Robustesse R4 :** moyenne équilibrée des quatre niveaux 0/20/41/60 %, après moyenne des familles et graines à chaque niveau. Rapporter aussi chaque sévérité, match et suite historique séparément. Ne plus nommer une moyenne de conditions un score « avec 41 % d’absences ».

Suivre macroF1, F1/précision/rappel D, résultats H/A, frontières ±12/25 images, fragmentation, abstentions, possessions <1/<2/<5 s et durées D. Garder spellF1 sur la séquence entière : retirer et concaténer les images visibles crée de fausses frontières. Stratifier les métriques par image selon visibilité et qualité, à part.

### 8.4. Validation et budgets avant essais

Quatre plis externes : trois matchs apprennent, le quatrième est évalué entier. Prétraitement, contexte, prior, durées, calibration et seuils sont appris sans ce quatrième match. Calibration et early stopping utilisent des sous-plis **internes aux trois matchs d’apprentissage**. Des prédictions hors pli ne deviennent pas une évaluation valide si leurs propres labels ajustent ensuite le calibrateur évalué dessus.

Le comparateur interne **C0-OOF** réapprend la recette C0 sur les trois matchs du pli ; il n'utilise pas les poids publiés C0, qui ont déjà vu les quatre matchs. Sur la confirmation et un éventuel nouveau test, **C0** désigne le paquet publié, inchangé. Après choix interne d'une configuration bonus, réapprendre ses paramètres sur les quatre matchs autorisés avant confirmation, sans ajustement sur J03WPY/J03WQQ.

Les jalons J9–J17 utilisent uniquement cette sélection interne. Ne pas rouvrir les deux matchs de confirmation après chaque essai : la liste fermée est examinée une fois au J18. Un échec à cette confirmation conduit au maintien de C0, pas à une nouvelle grille pilotée par ces scores.

Les plafonds suivants sont **enregistrés au J8** dans `configs/bonus_v2/budgets.json`. La grille J9 est scellée dans `j9_grid.json`, sans essai exécuté ; les grilles ultérieures devront être scellées avant leur bloc. Une configuration inclut architecture, caractéristiques, pertes et réglages. Graines et plis ne sont pas de nouvelles configurations mais leurs entraînements et coûts sont comptés séparément.

| Jalon | Configurations nouvelles maximales |
|---|---:|
| J9 | 8 |
| J10 | 8 |
| J11 | 6 |
| J12 | 6 |
| J13 | 6 |
| J14 | 2 |
| J15 | 4 |
| J16 | 4 au total entre ses trois branches |
| J17 | 4 |
| **Total** | **48** |

Méthodes déterministes : une graine fixe ; stochastiques : deux au plus. Plafonds proposés : **48 heures CPU et 24 heures GPU** pour la phase, à réduire selon les moyens disponibles. Inclure sous-plis et prétraitement. Aucun GPU n’est supposé disponible : ses expériences restent conditionnelles. Arrêter les pistes non prometteuses sans épuiser leur budget.

Écrire les configurations exactes et règles d’arrêt avant chaque bloc. Tout ajustement après lecture des scores est une nouvelle expérience déclarée et consomme le budget.

**Livrables J8 :** protocole V2, registre sources/recouvrements, matériel, référence C0 vérifiée et budgets. **Sortie :** aucun score public ni résultat de J03WR9 dans les fonctions de sélection.

## 5. J9 — D plus robuste et calibration hors du concours

**Hypothèse :** des indices physiques accompagnés de leur qualité et une estimation mieux calibrée transfèrent mieux entre capteurs. Le diagnostic public motive une question ; il ne fixe aucun seuil ou correctif.

Essais isolés :

1. C0, puis apprentissage avec les dégradations V2, sans changer les têtes.
2. Ajouter qualité des dérivées, support temporel, incertitude de projection, continuité et cohérence sortie/reprise. Une position présente mais aberrante n’est pas une preuve fiable.
3. Comparer des variantes limitées de pondération de perte et calibration séparée D/équipe : aucune, température ou Platt, selon la grille enregistrée. Éviter les paramètres redondants entre température globale et échelle temporelle.
4. Maintenir la factorisation D / H|vivant. Proximité et attribution d’équipe restent hors des entrées D. Une immobilité ou absence ne force jamais seule un arrêt.

Mesurer log-loss/Brier et calibration externe, mais adopter sur les métriques de possession. Une meilleure calibration DFL ne démontre pas une calibration BAR–ATH. Auditer la convention des labels avant d’attribuer un écart aux capteurs.

**Tests :** balle immobile en jeu, balle mobile après arrêt, reprise près d’un joueur, absence de balle, tous capteurs indisponibles, échange H/A et périodes séparées. **Livrable :** tête d’observation facultative et rapport par qualité/visibilité.

## 6. J10 — B1 : imputation courte et contrôle géométrique

**Hypothèse :** une géométrie locale prudente améliore des transitions sans fabriquer de contrôle pendant les longs trous.

- Commencer par interpolation linéaire et Kalman/lissage simple. Exemple de grille : trous maximaux 5/10/25 images, deux méthodes = six configurations ; deux autres pour l’ajout séparé d’un contrôle potentiel.
- Imputer seulement avec des bornes observées et un déplacement compatible dans une période. Pas d’extrapolation systématique des longs trous ou de liaison de fragments incompatibles.
- Garder observé/imputé, âge, méthode et incertitude. Ne pas remplacer le masque original ni utiliser le point imputé comme preuve de D.
- Comparer le contrôle potentiel aux distances existantes, puis à l’imputation seule. Un champ de contrôle n’est pas une possession observée.

Mesurer l’erreur de position sur les trous artificiels connus, puis **spellF1, frontières et possessions courtes**. Un bon RMSE sans gain de tâche ne suffit pas.

**Tests :** ligne, accélération, trou censuré en bord de période, point terminal absent, joueur manquant et doublon. **Livrable :** couche facultative et ablations imputation/contrôle distinctes.

## 7. J11 — B2 : durées souples et états internes

**Hypothèse :** les durées conservent mieux les récupérations brèves tout en supprimant les bascules sans contrôle.

Comparer avec les mêmes observations : Viterbi C0, puis HSMM ou extension d’états, six configurations au plus. Apprendre les durées sur les matchs d’apprentissage du pli. Prévoir les queues longues sans forcer une frontière à une durée maximale arbitraire.

Pas de règle « D ≥2 s » ni suppression automatique des segments <2 s. Distinguer durée de contrôle et durée d’un contact. Les états internes de passe/duel reviennent vers H/A/D avec une convention explicite ; ne pas prétendre avoir des labels plus fins qu’ils ne le sont.

**Tests :** optimalité exhaustive sur petites séquences, récupération d’une image, arrêt court, longue interruption, passe, déviation, égalités, inconnus et mi-temps. **Livrable :** décodeur facultatif, coût et bilan des courts segments. Écarter s’il gagne surtout en effaçant les vraies possessions.

## 8. J12 — B3 : frontières apprises

**Hypothèse :** une branche de frontières distingue changement de contrôle et bruit local.

Commencer par un petit TCN ou une tête temporelle sur les caractéristiques actuelles. Une branche H/A/D et une branche de frontières peuvent partager les observations, piste inspirée d’[ASRF](https://yiskw713.github.io/asrf/) à adapter et mesurer ici. Ne pas transposer son score d’un autre domaine.

Les cibles viennent des labels externes, sans traverser X ou les périodes. Figer contexte, tolérance et pondération des événements rares. Comparer au plus deux contextes et trois réglages de perte. Ne pas lancer plusieurs grandes architectures simultanément. MS-TCN++ reste une alternative à auditer si le petit modèle atteint ses limites.

Ne pas choisir l’epoch sur le match évalué. Contrôler padding et fenêtres futures ; ni vote sur labels déjà lissés, ni recalage au premier contact après coup.

**Tests :** frontières nettes/incertaines, contrôles brefs, bord de fenêtre et offsets connus sur fixtures. **Livrable :** scores de frontière tracés. Mesurer spellF1, datation et rappel court, pas seulement macroF1.

## 9. J13 — B4 : joueurs et contexte sans reconstruire la balle

**Hypothèse :** un modèle temporel du collectif apprend des indices absents de la régression quand le ballon manque.

Comparer le collectif logistique à un petit encodeur invariant à l’ordre des joueurs, puis une variante temporelle. Entrées anonymes et masques, sans noms/maillots/IDs persistants. Distinguer coordonnées et fragments, respecter H/A et ne calculer de vitesse que sur les liens valides.

Conserver D distinct du contrôle d’équipe. Tester d’abord le complément H/A pendant les trous avant de remplacer tout le modèle. Évaluer les six configurations avec permutations, pertes de joueurs et ruptures de pistes, même quand le ballon est visible.

**Livrable :** spécialiste collectif facultatif. Retenir un bénéfice hors pli et une complémentarité mesurée, pas une mémorisation du style d’équipe.

## 10. J14 — B5 : structures et apprentissage conjoint

Auditer **PathCRF**, **TranSPORTmer** et **BallRadar**, puis ouvrir au plus deux configurations d’**une seule famille**. Vérifier version, droits, code, poids, données et correspondance des états avant adaptation.

- [PathCRF](https://github.com/hyunsungkim-ds/pathcrf) propose possession/événements depuis les joueurs et fournit des modèles. Son dépôt utilise **les mêmes sept matchs Sportec/DFL**, avec des événements synchronisés. Ce n’est ni une nouvelle source indépendante ni un nouveau test.
- [TranSPORTmer](https://arxiv.org/abs/2410.17785) : piste multitâche trajectoires/états. Vérifier l’accès effectif au code, aux poids et aux données avant d’en dépendre.
- [BallRadar, article des auteurs](https://arxiv.org/abs/2306.08206) : inférence de balle depuis les joueurs. Une trajectoire reconstruite ne garantit pas H/A/D.

**Contamination possible :** les checkpoints peuvent avoir appris un match de notre validation ou du test consommé. Un fine-tuning n’efface pas cet historique. Une évaluation hors pli recevable exige une initialisation propre ou des poids dont les sources excluent le pli évalué et tout nouveau test. Une provenance inconnue interdit de revendiquer cette indépendance.

Ne pas remplacer silencieusement BallStatus/BallPossession par les labels prétraités d’un autre projet. Documenter les conventions, l’adaptateur H/A/D, les ballons libres et ruptures. Un nouveau test doit aussi être absent de l’apprentissage des poids tiers.

**Livrable :** audit des trois pistes et prototype si l’une est recevable. Sinon : « non testé : données/poids/provenance non adaptés », avec motif précis.

## 11. J15 — B7 : alignement et fusion TV

**Hypothèse :** une autre vue apporte des observations complémentaires si elle correspond au direct.

1. Charger la TV sur sa chronologie, son XML et ses 51 slots. Réutiliser les coordonnées terrain ; une détection pixel exige une projection contrôlée.
2. Aligner automatiquement par segments les configurations et mouvements. Autoriser des correspondances manquantes/non monotones autour des ralentis. Une homographie valide ne prouve pas le direct ; pas d’offset global supposé.
3. Enregistrer résidu, ambiguïté, durée cohérente et couverture. Rejeter ralentis, conflits et correspondances incertaines.
4. Fusionner les observations acceptées avec source et confiance. Garder tactique seule comme ablation et permettre le rejet complet de la TV.

Deux copies artificiellement dégradées d’un tracking vérifient le mécanisme, pas son efficacité entre deux vraies caméras. L’adoption exige des vues externes synchronisées et labels compatibles, ou une autre preuve indépendante recevable. La couverture BAR–ATH sans vérité terrain ne prouve pas la justesse des possessions.

**Tests :** décalage variable, coupure, ralenti, retour au direct, faux appariement et aucun appariement. **Livrable :** alignement et fusion locaux, quatre réglages maximum. Écarter si fiabilité ou gain reste indémontré.

## 12. J16 — B6 et B8 : trois essais conditionnels distincts

Ces branches partagent quatre configurations au maximum. Auditer données externes et moyens avant toute extraction vidéo massive.

### 16.1. Postures et gestes locaux — B6

Extraire automatiquement les fenêtres d’image via tracking et géométrie validée, puis tester un encodeur préentraîné figé. Crops, embeddings et incertitudes restent locaux. Aucune annotation ou correction de cadrage propre à des images de BAR–ATH. Comparer tracking seul et avec image sur des matchs externes vidéo/tracking annotés. Sans ces données, l’extraction est un prototype, pas un bonus validé.

### 16.2. Détection ciblée du ballon — B8

Appeler un détecteur accessible sur les zones ambiguës. Choisir les seuils hors BAR–ATH ; contrôler faux positifs, projection et cohérence temporelle. Si échec, conserver l’incertitude plutôt que forcer une détection. Mesurer localisation et possession séparément, temps et nombre d’images traitées.

### 16.3. Diffusion temporelle — B8

[DiffAct](https://github.com/Finspire13/DiffAct) fournit code et poids de segmentation pour d’autres jeux d’actions ; ce n’est pas un modèle de possession prêt pour le football. Ouvrir une configuration seulement si J12/J13 justifient une famille plus coûteuse, avec supervision, environnement et coût reproductibles. Aucun gain de spellF1 présumé.

**Livrables :** comparaison par branche réellement exécutée, accès/droits des poids, coût total. Une branche sans données externes recevables est reportée, pas « validée sur BAR–ATH ».

## 13. J17 — B8 : fusion limitée des spécialistes

Ouvrir si deux spécialistes montrent une complémentarité hors pli. Fusionner des scores avant décodage en conservant la factorisation état/équipe et la qualité des capteurs, sans vote sur labels finaux.

Apprendre calibration et poids dans les sous-plis internes. Quatre combinaisons enregistrées au plus ; pas toutes les paires de modèles. Comparer chaque composant, la fusion et les retraits. Écarter un ensemble plus lent sans gain stable.

**Livrable :** au plus une fusion dans la liste finale. Sans complémentarité, retenir un candidat individuel.

## 14. J18 — Comparer, décider et geler : équivalent du jalon 6

### 18.1. Liste fermée et comparaison reproductible

Avant la nouvelle confirmation, figer **quatre candidats au maximum, C0 compris** : meilleurs individus choisis en interne et éventuellement une fusion. Aucune nouvelle grille à ce stade. Lister aussi les bonus écartés et conditions manquantes.

Geler code, poids, prétraitements, configurations, sources, graines et prédictions. Comparer sur J03WPY/J03WQQ les 19 conditions historiques et les 22 V2. À quatre candidats : au plus **328 comparaisons rapportées**, soit 2 × (19+22) × 4. Réutiliser les prédictions identiques par empreinte sans les présenter comme des observations indépendantes.

Rapporter S41, R4 et chaque sévérité, puis macroF1, D, H/A, frontières, courts segments, fragmentation, coût et mémoire. Mesurer le coût depuis les entrées brutes en plus des temps de cache : ne pas opposer une reconstruction complète à des caractéristiques déjà calculées.

### 18.2. Adoption proposée, à figer au J8

Tous les critères sur la confirmation V2 doivent être satisfaits :

| Critère face à C0 | Proposition initiale |
|---|---:|
| Gain moyen S41, spellF1 | **≥ +0,010** |
| Perte maximale S41 d’un match | **≤ 0,010** |
| Perte de robustesse R4 | **≤ 0,005** |
| Perte macroF1 sur S41 | **≤ 0,005** |
| Perte F1 D / rappel D sur S41 | **≤ 0,010 / 0,020** |
| Perte de rappel possessions <2 s sur S41 | **≤ 0,005** |

Ces seuils de tri sont enregistrés au J8 dans `configs/bonus_v2/protocol.json` ; ce ne sont pas des seuils de significativité. Les figer avant les essais ; ne pas les assouplir après coup pour sauver une variante. Vérifier aussi une progression de l’objectif spécifique du bonus dans sa sélection interne, sans exiger d’une brique qu’elle résolve tout.

Deux matchs connus rendent les petits gains incertains. Les intervalles éventuels utilisent blocs ou matchs, jamais des images supposées indépendantes. Les graines ne remplacent pas de nouveaux matchs. À performance proche, privilégier coût et simplicité. Si aucun candidat ne satisfait la règle, **retenir C0**.

### 18.3. Éventuel test réellement inédit

Si J8 a réservé des matchs compatibles, une seule évaluation après choix : **candidate gelée et C0 uniquement**, suite V2, sans nouvelle grille. Pour M nouveaux matchs : 44 × M lignes de résultats. Auditer aussi les sources des poids tiers.

Le résultat ne déclenche ni réglage ni choix opportuniste d’une autre méthode. Ne pas recycler le test comme vierge. Une erreur logicielle avérée se documente et se corrige séparément d’une optimisation de métrique. Sans nouveau test, écrire cette limite ; garder J03WR9 comme résultat historique C0 seulement.

**Livrables J18 :** rapport V2, registre, liste testée/non testée, décision et manifeste. Chaque expérience porte ID, hypothèse, commit/empreintes, supervision, configuration, graines, coûts, mesures et motif de conservation/abandon.

## 15. J19 — Repréparer une soumission : équivalent du jalon 7

1. Construire un **paquet V2 séparé**, par exemple `release_v2/` et `mya_v2.py`, avec poids accessibles, paramètres et sources/configurations figés. V1 reste reproductible sur son commit. Sans bonus retenu, documenter le maintien de C0 au lieu de fabriquer une nouvelle version prédictive.
2. Une commande doit partir des seuls actifs nécessaires, sans caches de développement, labels, archives d’entraînement ou registres de recherche. Si TV/images sont retenues, déclarer les entrées, poids et extractions supplémentaires.
3. Tester un environnement neuf et une copie isolée : cache vide, reconstruit puis réutilisé ; comparer les octets. Documenter matériel et déterminisme, notamment GPU. Un calcul CPU équivalent doit reproduire la même sortie ; **pas de remplacement silencieux par C0** si GPU ou modalité manque.
4. Préparer `submissions/final_v2/MYA.csv` et un document de travail `MYA_v2.md`. Le dossier à envoyer contient `MYA.csv` et `MYA.md` ou `MYA.pdf`. Exclure ce dossier de Git avant sa création. Garder le dossier final V1 et ses empreintes.
5. Contrôler **le fichier exact** : 199 319 lignes, `frame,label`, indices 0…199318, H/A/D/X, périodes et zone D officielle. Figer la nouvelle empreinte après choix J18 ; ne pas modifier le contrôle V1 pour accepter une autre prédiction.
6. Actualiser le document technique : apports, essais abandonnés, actifs utilisés, labels/droits, coût, limites et reproduction. Ne pas utiliser le score public comme justification de sélection. Préserver les anciennes cellules du notebook, ajouter des lecteurs versionnés sans lancer de recherche à l’ouverture.
7. Vérifier fichiers publiables, poids et licences. Préparer commit/push lorsque demandé, séparément de l’envoi du CSV privé au formulaire. Vérifier lien et heure dans le courriel des organisateurs ; ne pas inventer de destinataire ou formulaire.

Format, dépôt reproductible et document technique suivent [SUBMISSION.md, consulté le 2 novembre](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/SUBMISSION.md). Le fichier annonce le **17 novembre 2026**, sans heure précise dans le texte consulté.

**Sortie J19 :** fichiers prêts, reproduction exacte vérifiée dans une installation propre, poids accessibles ou prêts à publier, documentation cohérente et aucune donnée privée dans le dépôt. Un diagnostic public supplémentaire n’est pas nécessaire à l’adoption ; si demandé après gel, l’archiver séparément sans changer la candidate.

## 16. Calendrier proposé et règle d’arrêt

| Fenêtre indicative | Priorité |
|---|---|
| 2–3 novembre | J8 : référence, protocole, éventuel nouveau test |
| 3–8 novembre | J9–J13 : essais accessibles et audits J14–J16 |
| 8–10 novembre | Pistes conditionnelles ayant passé leurs prérequis |
| 10–11 novembre | J17 si utile ; fermer recherches et liste finale |
| 11–13 novembre | **J18 : comparaison et gel** |
| 13–15 novembre | **J19 : installation propre, CSV et document** |
| 16 novembre | Marge : vérifications, publication demandée, préparation de l’envoi |

Proposition à partir du 2 novembre, pas promesse de tout entraîner. Toute piste non reproductible ou non prête au gel est arrêtée avec son motif. Vérifier l’échéance et l’heure dans les communications officielles. C0 permet de terminer J18/J19 même si plusieurs bonus sont écartés.

## 17. Conclusions autorisées

Un bonus retenu signifie un apport mesuré dans un protocole externe déclaré, avec ses limites. Un meilleur score DFL n’assure pas un gain sur tout BAR–ATH. Un meilleur taux de positions récupérées n’assure pas une meilleure possession. Aucun score privé ou résultat de podium n’est projeté.

Suite concrète : **tester séparément → garder les apports démontrés → comparer une liste fermée → reproduire la candidate → préparer les fichiers à remettre**. Conserver la version J7 reste une décision valide.
