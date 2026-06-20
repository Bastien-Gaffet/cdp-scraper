# Design — `cdp_viewer.py` (visualiseur local des cours)

**Date :** 2026-06-20
**Statut :** validé (design approuvé par l'utilisateur)

## Objectif

Permettre de parcourir confortablement, dans un navigateur, les documents
téléchargés par `cdp_scraper.py`. L'arborescence cible est
`cours_cdp/<nom-de-la-classe>/<arborescence du site>/fichiers` (PDF, images,
programmes de colles en texte). UI simple et efficace.

## Contraintes

- **Zéro dépendance** : bibliothèque standard Python uniquement. Rien n'est
  ajouté à `requirements.txt` (le projet ne dépend que de `requests`).
- **Python ≥ 3.8** (cohérent avec le scraper).
- **Local et privé** : serveur lié à `127.0.0.1` uniquement, jamais exposé au
  réseau. Aucune donnée envoyée à un tiers.
- **Un seul fichier** `cdp_viewer.py` à la racine du dépôt, plus un fichier de
  test. Pas de framework, pas de dossier `static/`/`templates/`.

## Architecture

Deux unités à responsabilité unique :

### 1. Serveur HTTP (la donnée)

Un handler basé sur `http.server.BaseHTTPRequestHandler`, servi par
`socketserver.TCPServer` lié à `127.0.0.1`. Routes :

| Route | Réponse |
|---|---|
| `GET /` | La page unique (HTML/CSS/JS embarqué comme chaîne dans le script). |
| `GET /api/classes` | JSON : liste des sous-dossiers de classes présents dans la racine. |
| `GET /api/tree?classe=<nom>` | JSON : arborescence dossiers/fichiers de la classe (nom, type, taille, chemin relatif). |
| `GET /file/<chemin>` | Le fichier réel, avec `Content-Type` déduit par `mimetypes`. Sert à l'aperçu et au téléchargement. |

Modules stdlib : `http.server`, `socketserver`, `webbrowser`, `urllib.parse`,
`mimetypes`, `pathlib`, `argparse`, `json`, `html`.

**Racine des cours** : `./cours_cdp` par défaut (défaut du scraper),
surchargeable par `--dossier`.

**Arguments CLI** :
- `--dossier CHEMIN` (défaut `cours_cdp`) — dossier racine à servir.
- `--port N` (défaut `8000`).
- `--no-browser` — ne pas ouvrir automatiquement le navigateur.

Au lancement : démarre le serveur, affiche l'URL `http://127.0.0.1:<port>`,
ouvre le navigateur (sauf `--no-browser`).

### 2. Frontend (la vue)

Page unique embarquée, vanilla JS + CSS (variables CSS pour les thèmes). Pas de
framework, pas de build.

**Disposition :**
- Barre supérieure : titre, sélecteur de classe, champ de recherche, bouton
  mode sombre.
- Sidebar gauche : arbre de dossiers repliable.
- Panneau principal droit : aperçu du fichier sélectionné.

**Aperçu par type :**
- PDF → `<iframe src="/file/...">`.
- Images (png, jpg, jpeg, gif, webp, svg) → `<img>`.
- Texte / markdown / code (txt, md, csv, py, tex, …) → `fetch` puis `<pre>` (échappé).
- Type inconnu → carte d'infos (nom, taille) + bouton « ⬇ Télécharger ».

**Recherche :** filtre l'arbre par nom, côté client (l'arbre est chargé une
seule fois en JSON par classe).

**Mode sombre :** bascule via variables CSS, préférence persistée dans
`localStorage`.

**Sélecteur de classe :** peuplé par `/api/classes`. S'affiche même avec une
seule classe (sélection par défaut = la première).

## Flux de données

1. Chargement de `/` → `fetch /api/classes` → peuple le sélecteur.
2. Sélection d'une classe → `fetch /api/tree?classe=...` → rendu de l'arbre.
3. Clic sur un fichier → chargement dans le panneau d'aperçu via l'URL `/file/...`.
4. Saisie dans la recherche → filtrage client de l'arbre déjà chargé.

## Sécurité

- Serveur lié à `127.0.0.1` exclusivement.
- **Anti path-traversal** : pour `/file/` et `/api/tree`, le chemin demandé est
  résolu (`Path.resolve()`) et doit être strictement contenu dans la racine
  résolue ; sinon `403`. Les `..`, chemins absolus et liens hors racine sont
  donc rejetés.
- Aucune écriture : le serveur est en lecture seule sur le dossier des cours.

## Gestion d'erreurs

- Racine inexistante ou vide → la page d'accueil affiche un message explicatif
  (« Aucun cours trouvé dans `<racine>`. Lance d'abord `cdp_scraper.py`. ») ;
  `/api/classes` renvoie une liste vide.
- Fichier inexistant → `404`.
- Chemin hors racine → `403`.
- Classe inconnue dans `/api/tree` → `404`.

## Tests

`test_cdp_viewer.py` avec `unittest` (stdlib, pas de pytest requis), sur un
dossier temporaire peuplé d'une fausse arborescence de classe :

- `/api/classes` liste correctement les sous-dossiers de classes.
- `/api/tree?classe=...` renvoie l'arborescence attendue.
- `/file/<connu>` renvoie le contenu attendu avec un `Content-Type` cohérent.
- Une requête `/file/../../secret` (ou équivalent encodé) renvoie `403`.

Le test démarre le serveur sur un port éphémère lié à `127.0.0.1` et utilise
`urllib.request` pour les requêtes.

## Hors périmètre (YAGNI)

- Pas d'authentification (usage purement local).
- Pas d'indexation plein-texte du contenu des PDF (recherche par nom seulement).
- Pas de génération de site statique ni de déploiement distant.
- Pas de modification/upload de fichiers.

## Intégration

- Une section « Parcourir ses cours (visualiseur local) » sera ajoutée au
  `README.md` et/ou à `docs/cdp_scraper_doc.md`.
- `.gitignore` couvre déjà `cours_cdp/` : aucun cours n'est versionné.
