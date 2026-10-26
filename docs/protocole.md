# Protocole des sources et de validation — jalon 0

Référence : règlement et FAQ du dépôt officiel, révision indiquée dans
`official-revision.txt`, consultés le 25 octobre 2026. Les règles officielles
prévalent sur les suggestions des anciens rapports et du benchmark.

## Sources et usages

Le registre versionné est `docs/sources.json`. Aucun chemin personnel ni contenu
privé ne doit y figurer. Les emplacements sont des chemins relatifs aux racines
configurables. L'exécution crée un manifeste **local et ignoré** dans
`.cache/manifests/ingestion.json`, avec chemins résolus, empreintes SHA-256,
dimensions et version de parseur. Les vidéos sont enregistrées mais ne sont pas
nécessaires aux deux premiers jalons.

Les entrées automatiques BAR-ATH peuvent servir à des algorithmes et à des
pseudo-labels automatiques. Aucun humain ne doit décider ces labels. Un résultat
mesuré sur des pseudo-labels n'est pas une mesure indépendante de justesse.

Les cinq minutes publiques sont réservées au diagnostic : fichier bien formé,
images alignées, sens des labels. Aucun apprentissage, calibration, seuil ou choix
de variante ne peut les utiliser. Les chargeurs publics imposent cet usage via
`purpose="diagnostic"` et refusent `training`, `calibration` et `selection`.
Ce garde-fou ne remplace pas la revue du code : un accès direct aux fichiers
pourrait le contourner. La future chaîne de prédiction ne doit importer aucun
chargeur de vérité terrain.

Toute annotation ou correction humaine de ce match est exclue, y compris sur le
tracking et sur les seules transitions, ainsi que les événements humains
externes sur ce même match. L'observation pour comprendre/debugger est autorisée,
mais ne doit pas produire de labels, de corrections ou de constantes liées à des
images particulières. Seules les bornes temporelles officiellement publiées sont
consignées dans la configuration.

Avant d'ajouter un jeu externe, enregistrer un **autre match**, la version,
l'URL d'accès, la licence/droit d'usage, les annotateurs et le volume, les usages
prévus et le découpage apprentissage/validation par match. Vérifier que les
organisateurs peuvent l'inspecter. Aucun jeu externe n'est adopté à ce stade ; la référence ouverte de Metrica Sports est conservée pour mémoire si besoin : https://github.com/metrica-sports/sample-data.

## Trois preuves distinctes

1. **Tests synthétiques** : formats, alignement, masques, géométrie, corruption et
   invalidation des caches. Ils ne lisent aucune donnée réelle ni label public.
2. **Diagnostic public** : uniquement après gel d'une version candidate ; noter
   commit, configuration et révision du scoreur. Corriger un défaut de format ou
   d'alignement identifié, jamais choisir un modèle sur son score public.
3. **Comparaison externe** : départager les variantes sur d'autres matchs
   autorisés, séparés par match, avec graines/configuration figées, ablations,
   coût et incertitude. Le jalon 6 réalisera cette comparaison. Aucun gain de
   modèle n'est revendiqué par les jalons 0 et 1.

## Publication et données privées

Le code ne doit envoyer aucune entrée privée, image, extrait XML/TXT/CSV ou dérivé
reconstructible à un LLM hébergé. Traitement et inspection des données restent
locaux. Les tests partagés ne contiennent que des fixtures générées synthétiquement.

Avant un commit, lancer `python -m src.hygiene.repository_check` et examiner
`git diff --cached --name-status`. Les notebooks suivis doivent avoir toutes leurs
sorties effacées et `execution_count=null`. Conserver les exécutions détaillées
dans `.cache/`, jamais dans le dépôt public. Ne pas ajouter caches, tracking par
image, séquences vidéo ou annotations privées. Le contrôle automatique détecte
des catégories de fichiers ; une revue humaine reste nécessaire pour les textes.

Le nettoyage concerne la version courante ; il ne réécrit pas l'historique Git.

## Conventions d'ingestion — jalon 1

- Configuration déduite de `src/config.py`, sans écriture à l'import. Variables :
  `MTAH_CHALLENGE_DIR`, `MTAH_DATA_DIR`, `MTAH_CACHE_DIR`.
- Sources indépendantes : tactique 199 319 × 46 ; TV 164 488 × 51. La TV conserve
  sa propre chronologie, sans offset global ni fusion implicite.
- Identifiant ATD consécutif depuis 1 ; indice vidéo = identifiant − 1.
  L'ordre des pistes suit les **références de colonnes du XML**, pas l'ordre des
  éléments Player. Leur équipe vient du XML, sans identifiants d'équipe figés.
- `players` et `ball` : x/y normalisés et vitesse scalaire brute dans l’unité déclarée par le XML. Les copies
  `players_metres` et `ball_metres` multiplient seulement x/y par 105,3 et 68.
  Aucune inversion automatique au changement de mi-temps. Les positions hors du
  rectangle ne sont pas écrêtées. Une piste n'est pas une identité de joueur.
- Masques `*_observed` : x et y finis. Masques `*_speed_observed` indépendants.
  NaN explicite conservé, infini rejeté ; aucune interpolation ni inférence de D.
- Homographie : frame vidéo depuis 0 ; normalisé → pixels, inverse pour pixels →
  normalisé ; `valid` strictement 0/1, matrice invalide explicitement NaN.
- Smart Tagging : intervalles `[start_frame,end_frame)`, arrondi à l'image la plus
  proche (demi vers le haut). Casse des groupes normalisée pour lecture ; N/A et
  champs inconnus conservés, jamais convertis en équipe.
- Chaque cache porte source, chemins, SHA-256 complets, taille/date, dimensions,
  conventions et version du parseur. Les anciens caches sont ignorés. Écriture
  atomique ; un aperçu valide aussi le fichier entier et ne crée aucun cache
  partiel. Le hachage complet ajoute un coût de lecture volontaire.

## Vérification reproductible

Depuis la racine, avec le Python de `.venv` :

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m src.validate_inputs
.venv\Scripts\python.exe -m src.hygiene.repository_check
```

La validation des entrées charge les deux ATD, les deux homographies et le Smart
Tagging ; elle vérifie l’égalité des valeurs après retour cache (NaN équivalents). Son
rapport local ne contient aucun label ou échantillon de tracking. Elle ne lit pas
les cinq minutes publiques et ne calcule aucun score de prédiction.

### Incohérence d’unité de vitesse à conserver explicitement

La prose officielle DATA.md annonce des m/s, mais les métadonnées XML livrées
déclarent le canal de vitesse en `kph`. Les chargeurs exposent donc `speed_unit`
et `speed_documentation_conflict`; ils ne convertissent pas la troisième composante
et ne la présentent pas silencieusement comme une vitesse en m/s. Les copies
métriques ne changent que x/y. Aucune méthode des jalons 0/1 n’utilise de seuil
de vitesse. Avant un futur seuil physique, clarifier cette incohérence auprès des
organisateurs ou valider explicitement l’unité par une méthode indépendante.
Ce point est consigné, sans inventer une correction des données.

Les erreurs d’homographie négatives livrées sont conservées dans la table brute,
mais marquées non observées (`reprojection_error_observed=False`) et rendues NaN
dans le tableau numérique d’erreurs : elles ne doivent pas paraître meilleures
que des erreurs positives. Cela ne change pas le drapeau de validité de la matrice.
