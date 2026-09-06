# 📚 cdp-scraper

[![Licence : CeCILL-2.1](https://img.shields.io/badge/Licence-CeCILL--2.1-blue.svg)](LICENSE)

> Sauvegarde personnelle de **vos** documents sur [cahier-de-prepa.fr](https://cahier-de-prepa.fr).

`cdp-scraper` se connecte avec **vos identifiants**, explore l'arborescence
« Documents à télécharger » de votre classe et la recopie à l'identique sur
votre disque (mêmes dossiers, mêmes noms de fichiers), programmes de colles
compris. Pensé pour les élèves de prépa qui veulent garder leurs cours après
l'année.

---

## ⚠️ À lire avant tout — usage légal

`cdp-scraper` est un **outil de sauvegarde personnelle**, pas un outil de
collecte ni de rediffusion. En l'utilisant, vous vous engagez à :

- **N'accéder qu'à vos propres contenus**, avec vos propres identifiants.
  L'outil ne télécharge **que ce que votre compte voit déjà** sur le site : il
  ne contourne aucun contrôle d'accès et ne casse aucun mot de passe.
- **Respecter le droit d'auteur.** Les cours, sujets et corrigés sont la
  propriété intellectuelle de leurs auteurs (vos professeurs). Réservez-les à
  un **usage strictement personnel et pédagogique**.
- **Ne pas rediffuser massivement** ces documents (site public, réseau social,
  plateforme de partage…). C'est exactement ce que demande l'avertissement
  affiché par cahier-de-prepa lui-même.
- **Ménager le serveur** : l'outil fait une requête à la fois ; utilisez
  `--delai` pour ajouter une pause si vous le souhaitez.

> Ce projet **n'est pas affilié** à cahier-de-prepa.fr ni à l'association qui
> l'édite. Il interagit simplement avec le site comme le ferait un navigateur,
> en s'identifiant honnêtement (User-Agent `cdp-scraper/…`).

Au **premier lancement**, ces conditions s'affichent et vous devez les accepter
(`j'accepte`). L'accord est mémorisé localement et n'est plus redemandé.

### 🔒 Données personnelles (RGPD)

- Vos **identifiants ne sont ni stockés ni transmis à un tiers**. Ils servent
  uniquement à la requête de connexion **directe au site**.
- Aucune donnée n'est envoyée vers un serveur externe : tout reste **entre
  votre machine et cahier-de-prepa.fr**.
- Les fichiers téléchargés et les éventuels cookies de session restent **chez
  vous** ; le `.gitignore` fourni évite de les versionner par accident.

---

## 🚀 Installation

Python ≥ 3.10 requis (seule dépendance : `requests`).

### Pour utiliser l'outil — le plus simple

Pas besoin de Git. Téléchargez directement le dépôt :

1. Sur la page GitHub, cliquez sur **`Code` ▾ → `Download ZIP`**
   (ou récupérez directement [l'archive `main.zip`](https://github.com/Bastien-Gaffet/cdp-scraper/archive/refs/heads/main.zip)).
2. Décompressez l'archive, puis ouvrez un terminal dans le dossier obtenu.
3. Lancez le script : `python cdp_scraper.py`.

> 💡 Rien à installer à la main : au premier lancement, le script détecte si
> `requests` manque et propose de l'installer pour vous (`pip install requests`).

### Pour contribuer ou suivre les mises à jour — avec Git

Si vous comptez modifier le code, proposer des correctifs (*pull requests*) ou
récupérer facilement les futures versions :

```bash
git clone https://github.com/Bastien-Gaffet/cdp-scraper.git
cd cdp-scraper
pip install -r requirements.txt
```

## ▶️ Utilisation

### Mode interactif (le plus simple)

```bash
python cdp_scraper.py
```

Le script pose les questions (URL de la classe, identifiant, mot de passe
masqué, dossier de destination).

### Mode arguments (automatisation)

```bash
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe -s ./cours
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe --simulation
```

> Conseil : laissez le mot de passe être demandé **interactivement** (saisie
> masquée) plutôt que de l'écrire dans la ligne de commande.

Les documents sont rangés dans `<dossier>/<nom-de-la-classe>/`, en respectant
l'arborescence exacte du site.

Principaux arguments :

| Argument | Description |
|----------|-------------|
| `--url URL` | URL de la classe sur cahier-de-prepa.fr |
| `--login NOM` | Identifiant / email de connexion |
| `-s / --sortie DIR` | Dossier de destination (défaut : `cours_cdp`) |
| `--simulation` | Lister les documents sans télécharger |
| `--complet` | Ignorer le manifeste et tout re-télécharger |
| `--reprise` | Reprendre uniquement les téléchargements en échec |
| `CLASSE...` | Noms de classes mémorisées à traiter (toutes / menu si aucun). |
| `--config CHEMIN` | Chemin du fichier de config (défaut : `.cdp-scraper/config.json`). |
| `--tout` | Traiter toutes les classes mémorisées, sans menu. |
| `--config-lister` | Afficher les classes mémorisées puis quitter. |
| `--config-supprimer NOM` | Retirer une classe de la config puis quitter. |
| `--coffre CHEMIN` | Chemin du fichier de coffre chiffré (défaut : `.cdp-scraper/coffre.json`). |
| `--coffre-ajouter NOM` | Enregistrer le mot de passe d'une classe mémorisée dans le coffre. |
| `--coffre-supprimer NOM` | Retirer le mot de passe d'une classe du coffre. |
| `--coffre-lister` | Afficher les classes ayant un mot de passe dans le coffre. |
| `--coffre-changer-mdp` | Changer le mot de passe maître du coffre. |

### 🔄 Synchronisation intelligente

Relancer `cdp_scraper.py` sur une classe déjà téléchargée ne retélécharge que
les documents **nouveaux ou modifiés** : la synchronisation est **incrémentale**
par défaut, sans requête superflue. Un manifeste `.cdp-manifest.json` est tenu à
jour dans le dossier de chaque classe pour suivre l'état des fichiers.

```bash
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe -s ./cours --complet
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe -s ./cours --reprise
```

- `--complet` : ignore le manifeste et **retélécharge tout** (resynchronisation
  complète).
- `--reprise` : retente uniquement les téléchargements en échec, **sans
  réexplorer** l'arborescence.

Dans le visualiseur, chaque fichier affiche sa **date d'ajout** et une vue
**« Récemment ajoutés »** regroupe les documents récents (7 / 30 / 90 jours).

### ⚙️ Config mémorisée et multi-classes

Après un téléchargement interactif réussi, le scraper propose de **mémoriser**
la classe (URL, identifiant, dossier — **jamais le mot de passe**). Les classes
mémorisées sont relançables par leur nom :

```bash
python cdp_scraper.py              # menu : choisir les classes à mettre à jour
python cdp_scraper.py mpsi pcsi    # seulement ces classes
python cdp_scraper.py --tout       # toutes, sans menu
python cdp_scraper.py --config-lister
```

Le fichier de config est cherché dans `./.cdp-scraper/config.json` (s'il existe),
sinon dans `~/.cdp-scraper/config.json`. Le **mot de passe n'est jamais stocké**
et reste demandé à chaque lancement (un par classe).

### 🔐 Coffre de mots de passe (optionnel)

Retaper un mot de passe à chaque run devient vite pénible avec plusieurs
classes. Le coffre chiffré résout ça, en restant **désactivé par défaut**.

Après le traitement d'une classe déjà mémorisée, le scraper propose :

```
Enregistrer le mot de passe de « mpsi » dans le coffre chiffré ?
  [o] Oui, l'enregistrer maintenant
  [n] Non, redemander la prochaine fois   (défaut)
  [j] Non, ne plus jamais demander pour cette classe
```

En répondant **o**, vous choisissez un **mot de passe maître** : le mot de
passe de la classe est alors chiffré (AES-256-GCM, clé dérivée par Scrypt)
dans `.cdp-scraper/coffre.json`. Au prochain run avec plusieurs classes,
une seule question suffit :

```bash
python cdp_scraper.py --tout
# « Utiliser le coffre chiffré pour déverrouiller les mots de passe enregistrés ? »
```

Un mot de passe maître incorrect est toléré 3 fois avant un repli automatique
sur la saisie manuelle. Commandes de gestion :

```bash
python cdp_scraper.py --coffre-ajouter mpsi       # activer plus tard pour une classe
python cdp_scraper.py --coffre-supprimer mpsi     # désactiver
python cdp_scraper.py --coffre-lister             # voir quelles classes sont enregistrées
python cdp_scraper.py --coffre-changer-mdp        # changer le mot de passe maître
```

> ⚠️ Le coffre protège contre un accès **occasionnel** au fichier (clé USB
> perdue, dossier partagé par erreur) — pas contre quelqu'un ayant un accès
> complet et prolongé à votre machine déjà déverrouillée. Utilisez un mot de
> passe maître **différent** de votre mot de passe cahier-de-prepa.

📖 **Documentation complète** (tous les arguments, fonctionnement du crawl,
programmes de colles, mode simulation) : [docs/cdp_scraper_doc.md](docs/cdp_scraper_doc.md).

---

## 🖥️ Parcourir ses cours (visualiseur local)

Une fois vos documents téléchargés, `cdp_viewer.py` lance un petit site **local**
pour les parcourir confortablement (arborescence, aperçu PDF/images/texte,
recherche, mode sombre). Aucune dépendance supplémentaire, rien n'est exposé sur
le réseau (le serveur n'écoute que sur `127.0.0.1`).

```bash
python cdp_viewer.py                     # sert ./cours_cdp et ouvre le navigateur
python cdp_viewer.py --dossier ./cours   # autre dossier racine
python cdp_viewer.py --port 8080 --no-browser
```

Le navigateur s'ouvre sur `http://127.0.0.1:8000`. Choisissez la classe en haut,
naviguez dans l'arbre à gauche, l'aperçu s'affiche à droite.

- Les fichiers **Python** (`.py`) s'affichent dans le navigateur avec
  **coloration syntaxique** et indentation préservée (coloration faite côté
  serveur avec le module standard `tokenize` : aucune dépendance, fonctionne
  hors-ligne). Un bouton **« Lancer sur la machine »** ouvre le script dans un
  IDE installé (VS Code, PyCharm, Sublime, Thonny, Spyder…) ou, à défaut,
  l'exécute dans un terminal. La coloration couvre aussi **C, C++, Java, SQL,
  R, OCaml et JSON**.
- Les fichiers **Markdown** (`.md`/`.markdown`) s'affichent **formatés**
  (titres, listes, tableaux, citations, liens, images locales, code) via un
  bouton **« Voir la source »** pour revenir au texte brut à tout moment.
- Les fichiers **GeoGebra** (`.ggb`) s'ouvrent dans un nouvel onglet via
  **GeoGebra en ligne** ; en l'absence d'Internet, repli sur l'**application
  installée** sur le PC, puis à défaut sur l'**explorateur de fichiers**.
- Les autres fichiers non affichables par le navigateur (ex. `.docx`) suivent la
  même logique appli installée → explorateur (jamais de téléchargement silencieux).

---

## 📄 Licence

Distribué sous licence **CeCILL-2.1** (licence libre française, compatible GPL).
Voir le fichier [LICENSE](LICENSE).

Le logiciel *Cahier de prépa* est un projet indépendant de Cyril Ravat,
également sous CeCILL : <https://forge.apps.education.fr/cyrilravat/cahier-de-prepa>.

## 🤝 Contribution

Les retours et contributions sont bienvenus via *issues* et *pull requests*.
Merci de ne **jamais** inclure de documents de cours, d'identifiants ou de
cookies dans une contribution.
