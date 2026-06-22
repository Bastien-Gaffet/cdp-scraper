# Journal des modifications

Toutes les modifications notables de ce projet sont consignées ici.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).
La version est unique pour l'ensemble du projet : `cdp_scraper.py` et
`cdp_viewer.py` portent le même numéro et sont publiés ensemble.

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
