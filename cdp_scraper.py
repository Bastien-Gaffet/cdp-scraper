#!/usr/bin/env python3
"""
cdp_scraper.py — Scraper pour cahier-de-prepa.fr

Connexion depuis le terminal, exploration complète de l'arborescence
« Documents à télécharger » d'une classe et téléchargement organisé par
répertoire (la même structure que sur le site).

Deux façons de l'utiliser :

  1. Mode interactif (le plus simple) — lancez sans rien :
         python cdp_scraper.py
     Le script vous pose les questions (URL, identifiant, mot de passe, dossier…).

  2. Mode arguments (pour automatiser) :
         python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe \
                               --login moi@exemple.fr --mdp secret -s ./cours

Fonctionnement (conforme au logiciel Cahier de prépa) :
  • Connexion : POST AJAX sur <classe>/ajax.php  (champs login + motdepasse)
  • Documents : page <classe>/docs, dossiers via ?rep=N / ?categorie,
                fichiers via download?id=N&v=hash
"""

import os
import re
import sys
import html
import time
import getpass
import argparse
from pathlib import Path
from datetime import datetime
import cdp_manifeste
import cdp_config
from urllib.parse import urljoin, urlsplit, unquote

__version__ = "1.3.0"
# URL du dépôt, reprise dans le User-Agent (transparence vis-à-vis du serveur).
DEPOT = "https://github.com/Bastien-Gaffet/cdp-scraper"

# Fichier marquant que l'utilisateur a accepté les conditions d'usage.
ACCORD_FICHIER = Path.home() / ".cdp-scraper" / "accord.txt"

def _init_terminal():
    """Sortie UTF-8 (accents) + activation des couleurs ANSI sous Windows."""
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    # Active le traitement des séquences ANSI dans la console Windows 10/11
    if os.name == "nt":
        try:
            import ctypes
            noyau = ctypes.windll.kernel32
            for std in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
                handle = noyau.GetStdHandle(std)
                mode = ctypes.c_uint32()
                if noyau.GetConsoleMode(handle, ctypes.byref(mode)):
                    # 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
                    noyau.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


_init_terminal()

def _assurer_dependances(paquets=("requests",)):
    """Vérifie les dépendances et propose de les installer via pip si besoin."""
    import importlib.util
    manquants = [p for p in paquets if importlib.util.find_spec(p) is None]
    if not manquants:
        return

    liste = " ".join(manquants)
    print(f"Dépendance(s) manquante(s) : {liste}")

    # En mode non interactif, on ne tente pas d'installer tout seul.
    interactif = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    if interactif:
        rep = input(f"Installer maintenant avec pip ? [O/n] : ").strip().lower()
        accepte = rep in ("", "o", "oui", "y", "yes")
    else:
        accepte = False

    if not accepte:
        print(f"Installez-les puis relancez :  pip install {liste}")
        sys.exit(1)

    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *manquants])
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"Échec de l'installation automatique ({e}).")
        print(f"Installez-les manuellement :  pip install {liste}")
        sys.exit(1)


_assurer_dependances()
import requests

# ─── Couleurs terminal ────────────────────────────────────────────────────────
# Couleurs ANSI brutes (pas de dépendance externe). Désactivées si la sortie
# n'est pas un terminal (fichier/pipe) pour ne pas polluer avec des codes.

_COULEURS = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code, t):
    return f"\033[{code}m{t}\033[0m" if _COULEURS else t

def rouge(t): return _c("31",   t)
def vert(t):  return _c("32",   t)
def jaune(t): return _c("33",   t)
def cyan(t):  return _c("36",   t)
def gras(t):  return _c("1",    t)
def dim(t):   return _c("2",    t)

# ─── Petits utilitaires ──────────────────────────────────────────────────────

def fmt_taille(octets: float) -> str:
    for unite in ["o", "Ko", "Mo", "Go"]:
        if octets < 1024:
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}"
        octets /= 1024
    return f"{octets:.1f} To"


def nom_sur(nom: str) -> str:
    """Nettoie un nom de fichier/dossier des caractères interdits par l'OS."""
    nom = html.unescape(nom)
    nom = re.sub(r'[\\/*?:"<>|]', "_", nom)
    return nom.strip(". ").strip()[:200] or "document"


EXT_PAR_TYPE = {
    "pdf": ".pdf", "jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "gif": ".gif",
    "zip": ".zip", "rar": ".rar", "txt": ".txt", "doc": ".doc", "docx": ".docx",
    "xls": ".xls", "xlsx": ".xlsx", "ppt": ".ppt", "pptx": ".pptx", "odt": ".odt",
    "ods": ".ods", "odp": ".odp", "py": ".py", "ipynb": ".ipynb", "csv": ".csv",
    "mp4": ".mp4", "mp3": ".mp3", "ggb": ".ggb", "tex": ".tex", "html": ".html",
}

# ─── Connexion ───────────────────────────────────────────────────────────────

def creer_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        # User-Agent honnête : le script s'identifie clairement, par loyauté
        # vis-à-vis du serveur (pas d'imitation de navigateur).
        "User-Agent": f"cdp-scraper/{__version__} (+{DEPOT})",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })
    return s


def connexion(session: requests.Session, base: str, login: str, mdp: str):
    """
    Se connecte via le endpoint AJAX du site.
    Retourne (succès: bool, message: str).
    """
    # 1) Établir une session (récupère le cookie CDP_SESSION)
    try:
        session.get(base + "/", timeout=15)
    except requests.RequestException as e:
        return False, f"Site injoignable : {e}"

    # 2) POST de connexion (champs exacts du logiciel Cahier de prépa)
    try:
        resp = session.post(
            base + "/ajax.php",
            data={"login": login, "motdepasse": mdp, "connexion": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Échec de la requête de connexion : {e}"

    try:
        data = resp.json()
    except ValueError:
        return False, "Réponse inattendue du serveur (pas de JSON)."

    if data.get("etat") == "ok":
        return True, data.get("message", "Connexion réussie")
    return False, data.get("message", "Identifiants refusés")


# ─── Analyse des pages « docs » ──────────────────────────────────────────────

RE_SECTION   = re.compile(r"<section\b[^>]*>(.*?)</section>", re.IGNORECASE | re.DOTALL)
# class="rep"/"doc" peut être suivi d'autres attributs (data-id apparaît une
# fois connecté) → on autorise n'importe quels attributs dans la balise <p>.
RE_BLOC      = re.compile(r'<p\s+[^>]*?class="(rep|doc)"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)
RE_HREF      = re.compile(r'href="([^"]+)"', re.IGNORECASE)
RE_NOM       = re.compile(r'<span\s+class="nom">(.*?)</span>', re.IGNORECASE | re.DOTALL)
RE_DONNEES   = re.compile(r'<span\s+class="docdonnees">\((.*?)\)</span>', re.IGNORECASE | re.DOTALL)
RE_ID        = re.compile(r'download\?id=(\d+)', re.IGNORECASE)


def _texte(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def analyser_page(html_page: str, url_page: str):
    """
    Analyse une page docs et renvoie (sous_dossiers, documents).

      sous_dossiers : [{"url": abs, "nom": str}]
      documents     : [{"url": abs, "id": str, "nom": str, "type": str, "empreinte": str}]

    On se limite au <section> (le contenu réel), ce qui ignore le menu de
    navigation. Le bloc « Documents récents » (noms contenant « / ») est
    écarté : ces fichiers sont récupérés dans leur vrai répertoire.
    """
    m = RE_SECTION.search(html_page)
    corps = m.group(1) if m else html_page

    sous_dossiers, documents = [], []

    for classe, bloc in RE_BLOC.findall(corps):
        href_m = RE_HREF.search(bloc)
        nom_m  = RE_NOM.search(bloc)
        if not href_m:
            continue
        href = html.unescape(href_m.group(1))
        nom  = _texte(nom_m.group(1)) if nom_m else ""
        url_abs = urljoin(url_page, href)

        if classe == "rep":
            sous_dossiers.append({"url": url_abs, "nom": nom or "dossier"})
        else:  # doc
            id_m = RE_ID.search(href)
            if not id_m:
                continue
            if "/" in nom:          # entrée du bloc « Documents récents » → ignorée
                continue
            don_m = RE_DONNEES.search(bloc)
            type_ = ""
            empreinte = ""
            if don_m:
                empreinte = don_m.group(1).strip()
                type_ = empreinte.split(",")[0].strip().lower()
            id_doc = id_m.group(1)
            # Pour audio/vidéo/py/sql, le bloc <p class="doc"> contient D'ABORD un
            # lien « icon-play » en download?id=N&voir (page lecteur HTML, ou
            # redirection Basthon) AVANT le vrai lien de téléchargement. On ne se
            # fie donc pas au premier href : on reconstruit une URL propre depuis
            # l'id et on force &dl (download.php renvoie alors le binaire brut,
            # quel que soit le type, sans page lecteur ni redirection).
            documents.append({
                "url":  urljoin(url_page, f"download?id={id_doc}&dl"),
                "id":   id_doc,
                "nom":  nom or f"document_{id_doc}",
                "type": type_,
                "empreinte": empreinte,
            })

    return sous_dossiers, documents


def _cle_rep(url: str) -> str:
    """Clé de déduplication d'un répertoire (query sans paramètres d'affichage)."""
    q = urlsplit(url).query
    q = re.sub(r"(?:^|&)(ordre|v)=[^&]*", "", q).strip("&")
    return q  # "" = racine docs


def crawler(session: requests.Session, base: str, profondeur_max=None, delai=0.0):
    """
    Parcourt toute l'arborescence des documents à partir de <classe>/docs.
    Renvoie la liste des documents trouvés, chacun avec son chemin relatif.
    """
    racine = base + "/docs"
    a_visiter = [(racine, "", 0)]      # (url, chemin_relatif, profondeur)
    reps_vus  = set()
    documents = {}                     # id -> doc (déduplication)

    while a_visiter:
        url, chemin, prof = a_visiter.pop(0)
        cle = _cle_rep(url)
        if cle in reps_vus:
            continue
        reps_vus.add(cle)

        try:
            resp = session.get(url, timeout=20)
        except requests.RequestException as e:
            print(jaune(f"  [!] {url} : {e}"))
            continue
        if resp.status_code != 200:
            continue

        affichage = chemin if chemin else "(racine)"
        print(dim(f"  Dossier : {affichage}"))

        sous_dossiers, docs = analyser_page(resp.text, url)

        for d in docs:
            if d["id"] not in documents:
                d["chemin"] = chemin
                documents[d["id"]] = d

        if profondeur_max is None or prof < profondeur_max:
            for sd in sous_dossiers:
                if _cle_rep(sd["url"]) not in reps_vus:
                    sous_chemin = f"{chemin}/{nom_sur(sd['nom'])}" if chemin else nom_sur(sd["nom"])
                    a_visiter.append((sd["url"], sous_chemin, prof + 1))

        if delai:
            time.sleep(delai)

    return list(documents.values())


# ─── Programmes de colles ─────────────────────────────────────────────────────

RE_PC_LIEN = re.compile(r'href="download\?id=(\d+)[^"]*">([^<]*)</a>', re.IGNORECASE)


def _html_progcolles(page: str, matiere: str):
    """Construit une page HTML autonome à partir du programme de colles textuel."""
    m = RE_SECTION.search(page)
    corps = m.group(1) if m else ""
    corps = re.sub(r'<p id="recherchecolle".*?</p>', "", corps, flags=re.DOTALL)
    corps = re.sub(r"<script.*?</script>", "", corps, flags=re.DOTALL)
    corps = re.sub(r'<div id="icones".*?</div>', "", corps, flags=re.DOTALL)
    corps = corps.strip()
    if not corps:
        return None
    titre = html.escape(f"Programme de colles - {matiere}")
    return (
        '<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{titre}</title>\n"
        '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>\n'
        "<style>body{font-family:sans-serif;max-width:820px;margin:auto;padding:1em}"
        "article{border-bottom:1px solid #ccc;margin-bottom:1em}h3{color:#234}</style>\n"
        f"</head>\n<body>\n<h1>{titre}</h1>\n{corps}\n</body>\n</html>\n"
    )


def crawler_progcolles(session: requests.Session, base: str):
    """
    Récupère les programmes de colles (page progcolles?matiere&tout).
      • mode « PDF par semaine » → chaque PDF devient un document à télécharger
      • mode « texte »            → la page est sauvegardée en HTML autonome
    Le mode « redirection vers un dossier » est déjà couvert par le crawl des docs.
    """
    try:
        menu = session.get(base + "/docs", timeout=20).text
    except requests.RequestException:
        return []

    cles = []
    for m in re.finditer(r'href="progcolles\?([A-Za-z0-9_]+)"', menu):
        if m.group(1) not in cles:
            cles.append(m.group(1))
    if not cles:
        return []

    print(dim(f"  Programmes de colles : {', '.join(cles)}"))
    resultat = []
    for cle in cles:
        url = f"{base}/progcolles?{cle}&tout"
        try:
            page = session.get(url, timeout=20).text
        except requests.RequestException:
            continue

        if "Ce contenu est protégé" in page:   # non accessible avec ce compte
            continue

        mt = re.search(r"<title>\s*Programme de colles\s*-\s*([^<]+)</title>", page)
        matiere = nom_sur(mt.group(1).strip()) if mt else cle

        liens = {}
        for did, nom in RE_PC_LIEN.findall(page):
            nom = re.sub(r"\s*\(pdf\)\s*$", "", html.unescape(nom).strip(), flags=re.IGNORECASE)
            liens.setdefault(did, nom or f"semaine_{did}")

        if liens:  # mode PDF par semaine
            for did, nom in liens.items():
                resultat.append({
                    "url":    f"{base}/download?id={did}&dl",
                    "id":     did,
                    "nom":    nom,
                    "type":   "pdf",
                    "chemin": f"{matiere}/Programme de colles",
                })
        else:       # mode texte → page HTML autonome
            contenu = _html_progcolles(page, matiere)
            if contenu:
                resultat.append({
                    "id":           f"pc_{cle}",
                    "nom":          "Programme de colles.html",
                    "chemin":       matiere,
                    "contenu_html": contenu,
                })

    return resultat

# ─── Téléchargement ──────────────────────────────────────────────────────────

def nom_fichier(resp: requests.Response, doc: dict) -> str:
    """Détermine le nom de fichier (Content-Disposition prioritaire)."""
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";\r\n]+)", cd, re.IGNORECASE)
    if m:
        return nom_sur(unquote(m.group(1)))

    nom = doc["nom"]
    if "." not in nom and doc.get("type"):
        nom += EXT_PAR_TYPE.get(doc["type"], "")
    return nom_sur(nom)


def _ecrire_atomique(cible: Path, donnees: bytes):
    """Écrit `donnees` dans `cible` via un fichier .part puis renommage atomique."""
    part = cible.with_name(cible.name + ".part")
    part.write_bytes(donnees)
    os.replace(part, cible)


def telecharger(session, doc, dossier_base: Path, simulation: bool, i: int, total: int):
    """Télécharge `doc` sous `dossier_base`. Écriture atomique (.part puis
    renommage). Écrase toujours la cible (la décision de sauter est prise en
    amont par la planification). Renvoie (statut, taille, nom_reel) où statut ∈
    {ok, echec, simulation}."""
    chemin_rel = doc.get("chemin", "")
    dossier = dossier_base / chemin_rel if chemin_rel else dossier_base
    prefixe = f"[{i}/{total}]"

    # Contenu généré localement (programme de colles textuel) : pas de requête.
    if "contenu_html" in doc:
        donnees = doc["contenu_html"].encode("utf-8")
        nom = nom_sur(doc["nom"])
        affiche = f"{chemin_rel + '/' if chemin_rel else ''}{doc['nom']}"
        if simulation:
            print(f"  {prefixe} {cyan('[SIM]')} {affiche}  {dim('(' + fmt_taille(len(donnees)) + ')')}")
            return "simulation", len(donnees), nom
        dossier.mkdir(parents=True, exist_ok=True)
        _ecrire_atomique(dossier / nom, donnees)
        print(f"  {prefixe} {vert('[OK]')}  {affiche}  {dim('(' + fmt_taille(len(donnees)) + ')')}")
        return "ok", len(donnees), nom

    try:
        resp = session.get(doc["url"], timeout=60, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(rouge(f"  {prefixe} [ERR] {doc['nom']} -> {e}"))
        return "echec", 0, doc["nom"]

    nom = nom_fichier(resp, doc)
    affiche = f"{chemin_rel + '/' if chemin_rel else ''}{nom}"

    if simulation:
        taille = int(resp.headers.get("Content-Length", 0))
        print(f"  {prefixe} {cyan('[SIM]')} {affiche}  {dim('(' + (fmt_taille(taille) if taille else '?') + ')')}")
        resp.close()
        return "simulation", taille, nom

    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / nom
    part = cible.with_name(cible.name + ".part")
    taille = 0
    try:
        with open(part, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    taille += len(chunk)
        os.replace(part, cible)
    except (requests.RequestException, OSError) as e:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        print(rouge(f"  {prefixe} [ERR] {affiche} -> {e}"))
        return "echec", 0, nom

    print(f"  {prefixe} {vert('[OK]')}  {affiche}  {dim('(' + fmt_taille(taille) + ')')}")
    return "ok", taille, nom

# ─── Mode interactif ─────────────────────────────────────────────────────────

def demander(question: str, defaut: str = None, secret: bool = False) -> str:
    suffixe = f" [{defaut}]" if defaut else ""
    while True:
        if secret:
            val = getpass.getpass(f"{question}{suffixe} : ").strip()
        else:
            val = input(f"{question}{suffixe} : ").strip()
        if val:
            return val
        if defaut is not None:
            return defaut
        print(jaune("  (réponse obligatoire)"))


def demander_oui_non(question: str, defaut: bool = False) -> bool:
    d = "O/n" if defaut else "o/N"
    rep = input(f"{question} [{d}] : ").strip().lower()
    if not rep:
        return defaut
    return rep in ("o", "oui", "y", "yes")


def _indices_menu(saisie: str, total: int) -> list:
    """Convertit une saisie de menu en indices 0-based valides.
    '' ou 'tout' → tous ; '1,3' → [0,2]. Ignore hors-plage / non numérique /
    doublons (en conservant l'ordre de saisie)."""
    s = saisie.strip().lower()
    if s == "" or s == "tout":
        return list(range(total))
    indices = []
    for morceau in s.replace(" ", "").split(","):
        if morceau.isdigit():
            i = int(morceau) - 1
            if 0 <= i < total and i not in indices:
                indices.append(i)
    return indices


def normaliser_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")

# ─── Conditions d'usage (acceptation au premier lancement) ────────────────────

AVERTISSEMENT = """\
┌──────────────────────── CONDITIONS D'USAGE ────────────────────────┐

 cdp-scraper télécharge UNIQUEMENT les documents auxquels VOTRE compte
 a déjà accès sur cahier-de-prepa.fr. C'est une sauvegarde personnelle.

 En l'utilisant, vous vous engagez à :

   • Ne récupérer que les contenus de VOTRE/VOS classe(s), avec vos
     propres identifiants. Aucun contournement de droits d'accès.
   • Réserver ces documents à un usage strictement personnel et
     pédagogique. Les cours, sujets et corrigés restent la propriété
     intellectuelle de leurs auteurs (vos professeurs).
   • NE PAS rediffuser ni republier massivement ces documents (site
     public, réseau social, plateforme de partage…), conformément à
     l'avertissement affiché par cahier-de-prepa lui-même.
   • Rester mesuré : un seul flux de requêtes, option --delai pour
     ménager le serveur de l'association qui héberge le site.

 Vos identifiants ne sont JAMAIS stockés ni transmis à un tiers : ils
 servent seulement à la connexion directe au site (RGPD : aucune
 collecte, aucun envoi vers un serveur externe au vôtre).

└────────────────────────────────────────────────────────────────────┘
"""


def verifier_accord(accepter_sans_demander: bool = False):
    """Affiche les conditions au 1er lancement et exige une acceptation.

    L'accord est mémorisé dans ~/.cdp-scraper/accord.txt ; les lancements
    suivants ne réaffichent rien. `--accepter-conditions` permet d'accepter
    sans invite (utile en mode automatisé).
    """
    if ACCORD_FICHIER.exists():
        return

    print(jaune(AVERTISSEMENT))

    if accepter_sans_demander:
        print(dim("  Conditions acceptées via --accepter-conditions."))
    else:
        try:
            rep = input("Tapez « j'accepte » pour continuer : ").strip().lower()
        except EOFError:
            rep = ""
        if rep not in ("j'accepte", "j’accepte", "jaccepte"):
            print(rouge("Conditions non acceptées. Arrêt."))
            sys.exit(1)

    try:
        ACCORD_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        ACCORD_FICHIER.write_text(
            f"Conditions d'usage cdp-scraper {__version__} acceptées le "
            f"{datetime.now().isoformat(timespec='seconds')}.\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # impossible d'écrire le marqueur : on n'empêche pas l'usage
    print(vert("Merci. Conditions acceptées (ne sera plus redemandé).\n"))


# ─── Programme principal ─────────────────────────────────────────────────────

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Scraper cahier-de-prepa.fr — connexion + téléchargement de tous les documents.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples :
  python cdp_scraper.py                         (mode interactif, le plus simple)
  python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe
  python cdp_scraper.py --url https://... --login moi@ex.fr --mdp secret -s ./cours
  python cdp_scraper.py --url https://... --simulation
""",
    )
    p.add_argument("--url", metavar="URL_CLASSE",
                   help="URL de la classe (demandée si absente)")
    p.add_argument("--login", metavar="IDENTIFIANT",
                   help="Identifiant / email (demandé si absent)")
    p.add_argument("--mdp", metavar="MOT_DE_PASSE",
                   help="Mot de passe (demandé de façon masquée si absent)")
    p.add_argument("-s", "--sortie", metavar="DOSSIER",
                   help="Dossier de destination (défaut : cours_cdp)")
    p.add_argument("--simulation", action="store_true",
                   help="Lister les documents sans rien télécharger")
    p.add_argument("--profondeur", type=int, default=None, metavar="N",
                   help="Profondeur max de sous-dossiers (défaut : illimité)")
    p.add_argument("--delai", type=float, default=0.0, metavar="SECONDES",
                   help="Pause entre requêtes pour ménager le serveur (défaut : 0)")
    p.add_argument("--sans-colles", action="store_true",
                   help="Ne pas récupérer les programmes de colles")
    p.add_argument("--accepter-conditions", action="store_true",
                   help="Accepter les conditions d'usage sans invite (1er lancement)")
    synchro = p.add_mutually_exclusive_group()
    synchro.add_argument("--complet", action="store_true",
                         help="Ignorer le manifeste et tout re-télécharger (resynchro intégrale)")
    synchro.add_argument("--reprise", action="store_true",
                         help="Reprendre uniquement les téléchargements en échec, sans re-explorer\n"
                              "(les programmes de colles en texte ne sont pas concernés)")
    p.add_argument("noms", nargs="*", metavar="CLASSE",
                   help="Noms de classes mémorisées à traiter (toutes/menu si aucun)")
    p.add_argument("--config", metavar="CHEMIN",
                   help="Chemin du fichier de config (défaut : .cdp-scraper/config.json)")
    p.add_argument("--tout", action="store_true",
                   help="Traiter toutes les classes mémorisées, sans menu")
    p.add_argument("--config-lister", action="store_true",
                   help="Afficher les classes mémorisées puis quitter")
    p.add_argument("--config-supprimer", metavar="NOM",
                   help="Retirer une classe de la config puis quitter")
    p.add_argument("--version", action="version", version=f"cdp-scraper {__version__}")
    return p.parse_args(argv)


def executer_reprise(session, dossier: Path, delai: float):
    """Mode --reprise : retélécharge les seuls échecs/manquants listés au
    manifeste, sans re-explorer l'arborescence."""
    try:
        manifeste = cdp_manifeste.charger(dossier)
    except cdp_manifeste.ManifesteVersionFuture as e:
        print(rouge(f"\n{e}"))
        sys.exit(1)

    if not manifeste.get("documents"):
        print(jaune("\nAucun manifeste à reprendre."))
        print(jaune("Lancez d'abord une synchronisation normale."))
        return

    a_faire = cdp_manifeste.entrees_a_reprendre(manifeste, dossier)
    if not a_faire:
        print(vert("\nRien à reprendre : tout est à jour."))
        return

    a_faire.sort(key=lambda d: (d.get("chemin", ""), d["nom"]))
    total = len(a_faire)
    print(f"\nReprise de {gras(str(total))} téléchargement(s) en échec …\n")

    repris = 0
    for i, doc in enumerate(a_faire, 1):
        statut, taille, nom = telecharger(session, doc, dossier, False, i, total)
        erreur = "échec de téléchargement" if statut == "echec" else None
        cdp_manifeste.maj_entree(manifeste, doc, statut, nom, taille,
                                 datetime.now().isoformat(timespec="seconds"),
                                 erreur=erreur)
        if statut == "ok":
            repris += 1
        if delai:
            time.sleep(delai)

    manifeste["derniere_synchro"] = datetime.now().isoformat(timespec="seconds")
    cdp_manifeste.enregistrer(dossier, manifeste)

    persistants = total - repris
    print()
    print(gras("─── RÉSUMÉ " + "─" * 40))
    print(f"  Repris            : {vert(str(repris))}")
    if persistants:
        print(f"  Échecs persistants : {rouge(str(persistants))}")
    print()


def _afficher_resume_classe(simulation, compteur, volume, plan, dossier):
    print()
    print(gras("─── RÉSUMÉ " + "─" * 40))
    if simulation:
        print(f"  À télécharger : {gras(str(compteur['simulation']))}")
        print(f"  Volume estimé : {gras(fmt_taille(volume['simulation']))}")
        print(f"  À jour (ignorés) : {dim(str(len(plan['a_jour'])))}")
        print(jaune("  (mode simulation — relancez sans --simulation pour télécharger)"))
    else:
        print(f"  Nouveaux / mis à jour : {vert(str(compteur['ok']))}   ({fmt_taille(volume['ok'])})")
        print(f"  À jour (ignorés)      : {dim(str(len(plan['a_jour'])))}")
        if compteur["echec"]:
            print(f"  Échecs                : {rouge(str(compteur['echec']))}   (relançables avec --reprise)")
        if plan["disparus"]:
            print(f"  Disparus du serveur   : {jaune(str(len(plan['disparus'])))}   (fichiers conservés)")
        print(f"\n  Fichiers dans : {cyan(str(dossier.resolve()))}")
    print()


def traiter_classe(cfg: dict, args, mdp: str, simulation: bool) -> dict:
    """Traite une classe de bout en bout. `cfg` = {nom, url, login, dossier}
    (sans mot de passe). Renvoie un résumé agrégeable :
    {nom, ok, compteur, volume}."""
    nom_classe = cfg["nom"]
    url = cfg["url"]
    print(gras(cyan(f"\n── Classe : {nom_classe} ──")))
    print(f"Connexion à {cyan(url)} …")
    session = creer_session()
    ok, message = connexion(session, url, cfg["login"], mdp)
    if not ok:
        print(rouge(f"Connexion échouée : {message}"))
        print(jaune("Vérifiez l'URL de la classe, l'identifiant et le mot de passe."))
        return {"nom": nom_classe, "ok": False, "compteur": {}, "volume": {}}
    print(vert("Connexion réussie."))

    dossier = Path(cfg["dossier"]) / nom_classe

    if args.reprise:
        executer_reprise(session, dossier, args.delai)
        return {"nom": nom_classe, "ok": True, "compteur": {}, "volume": {}}

    prof = "illimitée" if args.profondeur is None else args.profondeur
    print(f"\nExploration des documents (profondeur {prof}) …")
    documents = crawler(session, url, args.profondeur, args.delai)

    if not args.sans_colles:
        colles = crawler_progcolles(session, url)
        if colles:
            fusion = {d["id"]: d for d in documents}
            ajoutes = 0
            for d in colles:
                if d["id"] not in fusion:
                    fusion[d["id"]] = d
                    ajoutes += 1
            documents = list(fusion.values())
            print(dim(f"  + {ajoutes} élément(s) de programmes de colles"))

    if not documents:
        print(jaune("\nAucun document trouvé."))
        print(jaune("La classe n'a peut-être pas de documents accessibles avec ce compte."))
        return {"nom": nom_classe, "ok": True, "compteur": {}, "volume": {}}

    print(f"\n{gras(str(len(documents)))} document(s) trouvé(s).")

    try:
        manifeste = cdp_manifeste.charger(dossier)
    except cdp_manifeste.ManifesteVersionFuture as e:
        print(rouge(f"\n{e}"))
        return {"nom": nom_classe, "ok": False, "compteur": {}, "volume": {}}

    plan = cdp_manifeste.planifier(documents, manifeste, dossier, complet=args.complet)
    a_faire = plan["nouveau"] + plan["modifie"] + plan["a_reprendre"]
    a_faire.sort(key=lambda d: (d.get("chemin", ""), d["nom"]))

    print(f"  {gras(str(len(plan['nouveau'])))} nouveau(x), "
          f"{gras(str(len(plan['modifie'])))} mis à jour, "
          f"{gras(str(len(plan['a_reprendre'])))} à reprendre, "
          f"{dim(str(len(plan['a_jour'])) + ' à jour')}.\n")

    if not simulation:
        dossier.mkdir(parents=True, exist_ok=True)
        print(f"Destination : {gras(str(dossier.resolve()))}\n")

    total = len(a_faire)
    compteur = {"ok": 0, "echec": 0, "simulation": 0}
    volume = {"ok": 0, "simulation": 0}
    for i, doc in enumerate(a_faire, 1):
        statut, taille, nom = telecharger(session, doc, dossier, simulation, i, total)
        compteur[statut] = compteur.get(statut, 0) + 1
        if statut in volume:
            volume[statut] += taille
        if not simulation:
            erreur = "échec de téléchargement" if statut == "echec" else None
            cdp_manifeste.maj_entree(manifeste, doc, statut, nom, taille,
                                     datetime.now().isoformat(timespec="seconds"),
                                     erreur=erreur)
        if not simulation and args.delai:
            time.sleep(args.delai)

    if not simulation:
        cdp_manifeste.marquer_disparus(manifeste, plan["disparus"])
        manifeste["version"] = cdp_manifeste.VERSION
        manifeste["classe"] = nom_classe
        manifeste["url"] = url
        manifeste["derniere_synchro"] = datetime.now().isoformat(timespec="seconds")
        cdp_manifeste.enregistrer(dossier, manifeste)

    _afficher_resume_classe(simulation, compteur, volume, plan, dossier)
    return {"nom": nom_classe, "ok": True, "compteur": compteur, "volume": volume}


def menu_selection(classes: list) -> list:
    """Affiche la liste numérotée des classes et renvoie celles choisies."""
    print("\nClasses mémorisées :")
    for i, c in enumerate(classes, 1):
        print(f"  {i}. {gras(c['nom'])}  {dim(c.get('url', ''))}")
    saisie = input("\nLesquelles traiter ? (ex. « 1,3 », « tout », Entrée = tout) : ")
    return [classes[i] for i in _indices_menu(saisie, len(classes))]


def afficher_config(config: dict):
    classes = cdp_config.lister(config)
    if not classes:
        print(jaune("\nAucune classe mémorisée."))
        return
    print(gras(f"\n{len(classes)} classe(s) mémorisée(s) :\n"))
    for c in classes:
        print(f"  • {gras(c['nom'])}")
        print(f"      url     : {c.get('url', '')}")
        print(f"      login   : {c.get('login', '')}")
        print(f"      dossier : {c.get('dossier', '')}")
    print()


def afficher_resume_global(resumes: list):
    """Résumé agrégé d'un run multi-classes (rien si une seule classe : son
    résumé a déjà été affiché)."""
    if len(resumes) <= 1:
        return
    print()
    print(gras("═══ RÉSUMÉ GLOBAL " + "═" * 33))
    total_ok = total_echec = 0
    for r in resumes:
        c = r.get("compteur", {})
        ok = c.get("ok", 0)
        echec = c.get("echec", 0)
        total_ok += ok
        total_echec += echec
        etat = vert("OK") if r.get("ok") else rouge("connexion échouée")
        ligne = f"  {gras(r['nom'])} : {ok} téléchargé(s)"
        if echec:
            ligne += f", {rouge(str(echec))} échec(s)"
        print(f"{ligne}   [{etat}]")
    suffixe = f", {rouge(str(total_echec))} échec(s)" if total_echec else ""
    print(f"\n  Total : {vert(str(total_ok))} téléchargé(s){suffixe}.")
    print()


def run_classe_unique(args, config, chemin_cfg):
    """Mode mono-classe : --url fourni OU config vide (interactif). Complète au
    clavier ce qui manque, traite la classe, puis propose de la mémoriser."""
    interactif = not args.url
    if interactif:
        print("Mode interactif — répondez aux questions (Entrée = valeur par défaut).\n")
    url = normaliser_url(args.url) if args.url else normaliser_url(
              demander("URL de la classe", defaut="https://cahier-de-prepa.fr/"))
    login = args.login or demander("Identifiant / email")
    mdp = args.mdp or demander("Mot de passe", secret=True)
    sortie = args.sortie or (demander("Dossier de destination", defaut="cours_cdp")
                             if interactif else "cours_cdp")

    simulation = args.simulation
    if interactif and not simulation:
        simulation = not demander_oui_non(
            "Télécharger les fichiers maintenant ? (« non » = simulation, ne rien écrire)",
            defaut=True)

    nom = nom_sur(urlsplit(url).path.strip("/").split("/")[-1]) or "classe"
    cfg = {"nom": nom, "url": url, "login": login, "dossier": sortie}
    resume = traiter_classe(cfg, args, mdp, simulation)

    if (resume.get("ok") and not args.reprise and interactif
            and not cdp_config.contient(config, nom)):
        if demander_oui_non(
                f"Mémoriser la classe « {nom} » dans la config ? (jamais le mot de passe)",
                defaut=True):
            cdp_config.ajouter_ou_maj(config, cfg)
            cdp_config.enregistrer(chemin_cfg, config)
            print(vert(f"Classe « {nom} » mémorisée dans {chemin_cfg}."))


def main():
    args = parse_args()

    print(gras(cyan("\n══════════ Scraper cahier-de-prepa.fr ══════════\n")))

    # Conditions d'usage (affichées + acceptées une seule fois).
    verifier_accord(args.accepter_conditions)

    chemin_cfg = cdp_config.chemin_config(args.config)
    try:
        config = cdp_config.charger(chemin_cfg)
    except cdp_config.ConfigVersionFuture as e:
        print(rouge(f"\n{e}"))
        sys.exit(1)

    # Commandes de gestion : exécutées puis sortie immédiate.
    if args.config_lister:
        afficher_config(config)
        return
    if args.config_supprimer:
        if not cdp_config.contient(config, args.config_supprimer):
            print(jaune(f"\nClasse « {args.config_supprimer} » absente de la config."))
            return
        cdp_config.retirer(config, args.config_supprimer)
        cdp_config.enregistrer(chemin_cfg, config)
        print(vert(f"\nClasse « {args.config_supprimer} » retirée de la config."))
        return

    # Mono-classe : --url explicite, ou config vide → interactif mono-classe.
    if args.url or not cdp_config.lister(config):
        run_classe_unique(args, config, chemin_cfg)
        return

    # Multi-classes piloté par la config.
    try:
        if args.noms:
            choisies = cdp_config.selectionner(config, args.noms)
        elif args.tout:
            choisies = cdp_config.lister(config)
        else:
            choisies = menu_selection(cdp_config.lister(config))
    except cdp_config.ClasseInconnue as e:
        print(rouge(f"\n{e}"))
        sys.exit(1)

    if not choisies:
        print(jaune("\nAucune classe sélectionnée."))
        return

    resumes = []
    for cfg in choisies:
        mdp = args.mdp or demander(f"Mot de passe pour « {cfg['nom']} »", secret=True)
        resumes.append(traiter_classe(cfg, args, mdp, args.simulation))
    afficher_resume_global(resumes)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(jaune("\nInterrompu par l'utilisateur."))
        sys.exit(130)
