# 📚 cdp_scraper.py — Documentation

Scraper dédié à [cahier-de-prepa.fr](https://cahier-de-prepa.fr) : connexion depuis le terminal, exploration complète de l'arborescence **Documents à télécharger** d'une classe, téléchargement organisé selon la même structure de répertoires que le site.

> ⚖️ **Usage personnel uniquement.** L'outil ne télécharge que les contenus déjà accessibles à votre compte et ne doit pas servir à rediffuser des documents protégés. Les conditions d'usage (droits d'auteur, RGPD) s'affichent et doivent être acceptées au premier lancement — voir le [README](../README.md).

---

## 🚀 Deux façons de l'utiliser

### 1. Mode interactif (le plus simple)

Lancez sans rien — le script pose les questions :

```bash
python cdp_scraper.py
```

```
══════════ Scraper cahier-de-prepa.fr ══════════

Mode interactif — répondez aux questions (Entrée = valeur par défaut).

URL de la classe [https://cahier-de-prepa.fr/] : https://cahier-de-prepa.fr/pcsi2-descartes
Identifiant / email : moi@exemple.fr
Mot de passe : ********              ← saisie masquée
Dossier de destination [cours_cdp] : C:\Users\moi\Documents\cours
Mode simulation (ne rien télécharger) ? [o/N] : n
```

### 2. Mode arguments (pour automatiser)

```bash
# Télécharger tous les documents d'une classe
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe --login moi@ex.fr --mdp secret -s ./cours

# Mode simulation (voir ce qui serait téléchargé)
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe --simulation

# Exporter la liste des URLs (pour telechargeur_batch.py) + cookies
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe --liste urls.txt --cookie-sortie cookies.txt
```

> Les arguments fournis sautent la question correspondante. Tout argument manquant (sauf en mode pleinement scripté) est demandé au clavier.

---

## ⚙️ Arguments

| Argument | Type | Défaut | Description |
|----------|------|--------|-------------|
| `--url URL` | string | *(demandé)* | URL de la classe (ex : `https://cahier-de-prepa.fr/ma-classe`) |
| `--login NOM` | string | *(demandé)* | Identifiant / email de connexion |
| `--mdp MDP` | string | *(demandé, masqué)* | Mot de passe |
| `-s / --sortie DIR` | string | `cours_cdp` | Dossier de destination |
| `--liste FICHIER` | string | — | Exporter les URLs trouvées (compatible `telechargeur_batch.py`) |
| `--simulation` | flag | non | Lister les documents sans télécharger |
| `--profondeur N` | int | illimité | Profondeur maximale de sous-dossiers explorés |
| `--delai SECONDES` | float | 0 | Pause entre requêtes pour ménager le serveur |
| `--sans-colles` | flag | non | Ne pas récupérer les programmes de colles |
| `--cookie-sortie FICHIER` | string | — | Sauvegarder les cookies de session |
| `--accepter-conditions` | flag | non | Accepter les conditions d'usage sans invite (1er lancement) |
| `--version` | flag | — | Afficher la version et quitter |

> ⚠️ Si votre mot de passe contient des caractères spéciaux (`#`, `$`, espace…), entourez-le de guillemets simples en ligne de commande : `--mdp '#MonMotDePasse2025'`. Le plus sûr reste de le laisser être demandé interactivement.

---

## 🔐 Connexion

La connexion reproduit exactement le mécanisme du logiciel *Cahier de prépa* :

- **POST AJAX** sur `<classe>/ajax.php` avec les champs `login`, `motdepasse` et `connexion=1`
- Le serveur répond en JSON : `{"etat":"ok"}` en cas de succès, sinon un message d'erreur (ex : *« Mauvais couple identifiant/mot de passe »*)
- Le cookie de session `CDP_SESSION` est conservé pour tous les téléchargements suivants

Si `--login` ou `--mdp` sont absents, ils sont demandés (le mot de passe via une saisie masquée `getpass`).

---

## 🗂️ Organisation des téléchargements

Les documents sont rangés selon **l'arborescence exacte du site**, sur plusieurs niveaux :

```
cours_cdp/
├── Général/
│   └── reglement_interieur.pdf
├── Physique/
│   ├── 01 écrits concours.pdf
│   ├── DM/
│   │   └── DM01.pdf
│   ├── DS/
│   └── TD/
│       └── TD 29 Induction.pdf
└── Chimie/
    ├── Cours/
    └── TP et corrigés/
```

Le nom de chaque fichier provient de l'en-tête `Content-Disposition` renvoyé par le serveur (le vrai nom du fichier), avec repli sur le nom affiché + extension déduite du type.

---

## 🕷️ Fonctionnement du crawl

1. **Connexion** : POST AJAX sur `ajax.php`, vérification du JSON `etat == "ok"`
2. **Point de départ** : la page `<classe>/docs` (racine des documents)
3. **Exploration en largeur** : suit chaque répertoire (`<p class="rep">` → liens `?categorie` ou `?rep=N`) et descend dans toute l'arborescence
4. **Extraction des fichiers** : chaque document (`<p class="doc">` → `download?id=N&v=hash`) est collecté avec son chemin
5. **Téléchargement** : requêtes séquentielles (une seule à la fois). Pas de pause par défaut ; ajoutez `--delai 0.2` pour ménager davantage le serveur

Particularités gérées :
- Seul le `<section>` de contenu est analysé → le menu de navigation est ignoré
- Le bloc **« Documents récents »** présent en bas de chaque page (noms du type `Physique/TD/…`) est écarté pour éviter les doublons : chaque fichier est récupéré dans son vrai répertoire
- Déduplication des dossiers et des fichiers (par `id`) → pas de boucle ni de double téléchargement
- Les dossiers verrouillés inaccessibles sont simplement ignorés

---

## 🎓 Programmes de colles

Le script récupère aussi les programmes de colles (`progcolles?matiere`), qui suivent trois fonctionnements selon la matière :

- **PDF par semaine** : chaque semaine est un PDF → tous les PDF sont téléchargés dans `<Matière>/Programme de colles/`.
- **Texte** : le programme est rédigé directement sur le site → la page complète de l'année est sauvegardée en HTML autonome (`<Matière>/Programme de colles.html`, avec rendu LaTeX via MathJax).
- **Redirection vers un dossier** : le lien pointe simplement vers un dossier de documents déjà existant → c'est donc déjà couvert par le crawl normal.

Ces programmes contiennent souvent des PDF qui ne sont **pas** dans l'arborescence des documents classiques. Désactivable avec `--sans-colles`.

## 🔗 Compatibilité avec telechargeur_batch.py

Le flag `--liste` génère un fichier d'URLs (avec le chemin de chaque document en commentaire). Couplé à `--cookie-sortie`, il permet de séparer découverte et téléchargement :

```bash
# Étape 1 : découvrir, exporter les URLs + cookies
python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe --liste urls.txt --cookie-sortie cookies.txt

# Étape 2 : télécharger en parallèle (4 threads)
python telechargeur_batch.py urls.txt --cookie-fichier cookies.txt -t 4 -s ./cours
```

---

## 📋 Mode simulation

Avec `--simulation`, aucun fichier n'est écrit ; le script affiche ce qu'il téléchargerait, avec la taille annoncée :

```
138 document(s) trouvé(s).

  [1/138] [SIM] Général/reglement_interieur.pdf  (212.4 Ko)
  [2/138] [SIM] Physique/DM/DM01.pdf  (1.2 Mo)
  ...
```

---

## 🧩 Dépendances

| Bibliothèque | Rôle | Obligatoire |
|---|---|---|
| `requests` | Requêtes HTTP, gestion des cookies/session | ✅ oui |

Les couleurs du terminal sont gérées par des codes ANSI bruts (activation du mode VT sous Windows) : **aucune dépendance à `colorama`**. L'analyse des pages se fait par expressions régulières sur le HTML : **aucune dépendance à `beautifulsoup4`**.

---

## 💡 Conseils d'utilisation

- **Premier lancement** : `--simulation` pour vérifier ce qui est trouvé avant de télécharger
- **Gros volume** : `--liste` puis `telechargeur_batch.py --threads 4`
- **Usage régulier** : `--cookie-sortie` pour relancer sans re-saisir les identifiants
- **Affichage des accents** : la sortie console est forcée en UTF-8 ; les noms de fichiers sont de toute façon écrits correctement sur le disque
