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

Python ≥ 3.8 requis (seule dépendance : `requests`).

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
