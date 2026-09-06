# Journal des modifications

Toutes les modifications notables de ce projet sont consignées ici.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).
La version est unique pour l'ensemble du projet : `cdp_scraper.py` et
`cdp_viewer.py` portent le même numéro et sont publiés ensemble.

## [1.4.0] - 2026-09-06

### Ajouté
- **Coffre de mots de passe chiffré (optionnel)** : après le traitement d'une
  classe mémorisée, le scraper propose de chiffrer son mot de passe
  (AES-256-GCM, clé dérivée par Scrypt d'un mot de passe maître) dans
  `.cdp-scraper/coffre.json`. Un seul mot de passe maître par run suffit
  ensuite à déverrouiller toutes les classes du coffre lors d'un run
  multi-classes — plus besoin de retaper chaque mot de passe.
  Commandes `--coffre-ajouter NOM`, `--coffre-supprimer NOM`,
  `--coffre-lister`, `--coffre-changer-mdp`, `--coffre CHEMIN`.
- Nouveau module `cdp_coffre.py` (fonctions pures + I/O atomique, testable
  hors-ligne, dépendance `cryptography` installée à la demande — jamais pour
  qui n'active pas le coffre).

### Modifié
- Le texte des conditions d'usage reflète le nouveau comportement optionnel
  (mots de passe toujours non stockés par défaut, coffre chiffré en option).

## [1.3.0] - 2026-06-23

### Ajouté
- **Multi-classes en un run** : traitez plusieurs classes d'affilée, par menu
  interactif ou en passant leurs noms en argument (`cdp_scraper.py mpsi pcsi`).
- **Config mémorisée** : un fichier `.cdp-scraper/config.json` retient
  url / login / dossier de chaque classe (jamais le mot de passe, redemandé à
  chaque run). Résolution en cascade : dossier courant puis dossier personnel.
  Commandes `--config-lister`, `--config-supprimer NOM`, `--tout`, `--config CHEMIN`.
- **Viewer — pages d'erreur soignées** : 404/403/500 affichent une page thémée
  (clair/sombre) avec un message contextuel et un retour à l'accueil.
- **Viewer — navigation clavier** : flèches pour parcourir, Entrée pour ouvrir,
  ← / Retour arrière pour remonter, `/` pour chercher, Échap pour effacer,
  `t` (thème) et `c` (classe suivante).
- **Viewer — recherche améliorée** : insensible aux accents et affiche le
  dossier de chaque résultat.

## [1.2.0] - 2026-06-22

### Ajouté
- Synchronisation incrémentale : lors d'une nouvelle exécution, seuls les
  documents nouveaux ou modifiés sont retéléchargés, grâce à un manifeste JSON
  par classe (`.cdp-manifest.json`). La détection des changements s'appuie sur
  les métadonnées déjà présentes dans le listing (aucune requête supplémentaire).
- Option `--complet` : ignore le manifeste et force une resynchronisation
  complète.
- Option `--reprise` : retélécharge uniquement les éléments en échec ou
  manquants, sans réexplorer l'arborescence.
- Visualiseur : date d'ajout affichée sur chaque fichier et vue « Récemment
  ajoutés » (fenêtre glissante 7 / 30 / 90 jours).

### Corrigé
- Les téléchargements sont écrits de façon atomique (fichier `.part` puis
  renommage) : une interruption ne laisse plus un fichier tronqué pris pour
  complet.
- Un document mis à jour côté serveur est désormais retéléchargé (auparavant,
  tout fichier déjà présent était systématiquement ignoré).

## [1.1.0] - 2026-06-21

### Ajouté
- Intégration continue GitHub Actions : la suite de tests s'exécute à chaque
  push et pull request (Ubuntu sur Python 3.10 à 3.13, Windows sur 3.12).
- Option `--version` pour `cdp_viewer.py`.
- Tests de robustesse du parsing (pages HTML figées dans `tests/fixtures/`).

### Modifié
- Python 3.10 ou supérieur est désormais requis (le viewer utilise des
  annotations évaluées à la définition, incompatibles avec 3.8/3.9, tous deux
  en fin de vie).

### Supprimé
- Options `--liste` et `--cookie-sortie` de `cdp_scraper.py`, ainsi que la
  fonction `sauvegarder_cookies` : elles servaient un script `telechargeur_batch.py`
  qui ne fait pas partie du projet.

### Versioning
- Mise en place d'une version unique de projet (SemVer). `cdp_scraper.py` et
  `cdp_viewer.py` partagent désormais le même `__version__`, bumpés ensemble.

## [1.0.0]

Première version publiée.

### Ajouté
- `cdp_scraper.py` : connexion à cahier-de-prepa.fr, exploration complète de
  l'arborescence des documents et téléchargement organisé par répertoire, y
  compris les programmes de colles. Conditions d'usage affichées et acceptées
  au premier lancement.
- `cdp_viewer.py` : visualiseur web local (bibliothèque standard, lié à
  127.0.0.1) de l'arborescence téléchargée, avec coloration syntaxique Python.
