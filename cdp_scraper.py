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
from urllib.parse import urljoin, urlsplit, unquote

__version__ = "1.0.0"
# URL du dépôt, reprise dans le User-Agent (transparence vis-à-vis du serveur).
# Remplacez par l'URL réelle après publication.
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


def sauvegarder_cookies(session: requests.Session, chemin: Path):
    """Écrit les cookies (CDP_SESSION…) au format attendu par telechargeur_batch.py."""
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("# Cookies de session cahier-de-prepa\n")
        f.write(f"# Utilisable avec : python telechargeur_batch.py urls.txt --cookie-fichier {chemin}\n\n")
        for c in session.cookies:
            f.write(f"{c.name}={c.value}\n")
    print(vert(f"Cookies sauvegardés : {chemin}"))

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
      documents     : [{"url": abs, "id": str, "nom": str, "type": str}]

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
            if don_m:
                type_ = don_m.group(1).split(",")[0].strip().lower()
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


def telecharger(session, doc, dossier_base: Path, simulation: bool, i: int, total: int):
    chemin_rel = doc.get("chemin", "")
    dossier = dossier_base / chemin_rel if chemin_rel else dossier_base
    prefixe = f"[{i}/{total}]"

    # Contenu généré localement (programme de colles textuel) : pas de requête.
    if "contenu_html" in doc:
        donnees = doc["contenu_html"].encode("utf-8")
        affiche = f"{chemin_rel + '/' if chemin_rel else ''}{doc['nom']}"
        if simulation:
            print(f"  {prefixe} {cyan('[SIM]')} {affiche}  {dim('(' + fmt_taille(len(donnees)) + ')')}")
            return "simulation", len(donnees)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / nom_sur(doc["nom"])).write_bytes(donnees)
        print(f"  {prefixe} {vert('[OK]')}  {affiche}  {dim('(' + fmt_taille(len(donnees)) + ')')}")
        return "ok", len(donnees)

    try:
        resp = session.get(doc["url"], timeout=60, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(rouge(f"  {prefixe} [ERR] {doc['nom']} -> {e}"))
        return "echec", 0

    nom = nom_fichier(resp, doc)
    affiche = f"{chemin_rel + '/' if chemin_rel else ''}{nom}"

    if simulation:
        taille = int(resp.headers.get("Content-Length", 0))
        print(f"  {prefixe} {cyan('[SIM]')} {affiche}  {dim('(' + (fmt_taille(taille) if taille else '?') + ')')}")
        resp.close()
        return "simulation", taille

    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / nom
    if cible.exists() and cible.stat().st_size > 0:
        print(dim(f"  {prefixe} [DEJA] {affiche}"))
        resp.close()
        return "existe", cible.stat().st_size

    taille = 0
    try:
        with open(cible, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    taille += len(chunk)
    except (requests.RequestException, OSError) as e:
        print(rouge(f"  {prefixe} [ERR] {affiche} -> {e}"))
        return "echec", 0

    print(f"  {prefixe} {vert('[OK]')}  {affiche}  {dim('(' + fmt_taille(taille) + ')')}")
    return "ok", taille

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

def parse_args():
    p = argparse.ArgumentParser(
        description="Scraper cahier-de-prepa.fr — connexion + téléchargement de tous les documents.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples :
  python cdp_scraper.py                         (mode interactif, le plus simple)
  python cdp_scraper.py --url https://cahier-de-prepa.fr/ma-classe
  python cdp_scraper.py --url https://... --login moi@ex.fr --mdp secret -s ./cours
  python cdp_scraper.py --url https://... --simulation
  python cdp_scraper.py --url https://... --liste urls.txt --cookie-sortie cookies.txt
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
    p.add_argument("--liste", metavar="FICHIER",
                   help="Exporter les URLs au lieu de télécharger (pour telechargeur_batch.py)")
    p.add_argument("--simulation", action="store_true",
                   help="Lister les documents sans rien télécharger")
    p.add_argument("--profondeur", type=int, default=None, metavar="N",
                   help="Profondeur max de sous-dossiers (défaut : illimité)")
    p.add_argument("--delai", type=float, default=0.0, metavar="SECONDES",
                   help="Pause entre requêtes pour ménager le serveur (défaut : 0)")
    p.add_argument("--sans-colles", action="store_true",
                   help="Ne pas récupérer les programmes de colles")
    p.add_argument("--cookie-sortie", metavar="FICHIER",
                   help="Sauvegarder les cookies de session dans un fichier")
    p.add_argument("--accepter-conditions", action="store_true",
                   help="Accepter les conditions d'usage sans invite (1er lancement)")
    p.add_argument("--version", action="version", version=f"cdp-scraper {__version__}")
    return p.parse_args()


def main():
    args = parse_args()

    print(gras(cyan("\n══════════ Scraper cahier-de-prepa.fr ══════════\n")))

    # Conditions d'usage (affichées + acceptées une seule fois).
    verifier_accord(args.accepter_conditions)

    # Mode interactif si l'essentiel manque : on complète au clavier.
    interactif = not args.url
    if interactif:
        print("Mode interactif — répondez aux questions (Entrée = valeur par défaut).\n")

    url    = normaliser_url(args.url) if args.url else normaliser_url(
                 demander("URL de la classe", defaut="https://cahier-de-prepa.fr/"))
    login  = args.login or demander("Identifiant / email")
    mdp    = args.mdp   or demander("Mot de passe", secret=True)
    sortie = args.sortie or (demander("Dossier de destination", defaut="cours_cdp")
                             if interactif else "cours_cdp")

    simulation = args.simulation
    if interactif and not simulation:
        simulation = demander_oui_non("Mode simulation (ne rien télécharger) ?", defaut=False)

    # ── Connexion ────────────────────────────────────────────────────────────
    print(f"\nConnexion à {cyan(url)} …")
    session = creer_session()
    ok, message = connexion(session, url, login, mdp)
    if not ok:
        print(rouge(f"Connexion échouée : {message}"))
        print(jaune("Vérifiez l'URL de la classe, l'identifiant et le mot de passe."))
        sys.exit(1)
    print(vert("Connexion réussie."))

    if args.cookie_sortie:
        sauvegarder_cookies(session, Path(args.cookie_sortie))

    # ── Exploration ──────────────────────────────────────────────────────────
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
        sys.exit(0)

    print(f"\n{gras(str(len(documents)))} document(s) trouvé(s).\n")

    # ── Export liste seule ───────────────────────────────────────────────────
    if args.liste:
        with open(args.liste, "w", encoding="utf-8") as f:
            f.write(f"# URLs de documents — {url}\n")
            f.write(f"# python telechargeur_batch.py {args.liste} --cookie-fichier cookies.txt\n\n")
            for d in sorted(documents, key=lambda x: (x.get("chemin", ""), x["nom"])):
                if "url" not in d:          # programme de colles textuel : pas d'URL
                    continue
                chemin = d.get("chemin", "")
                f.write(f"{d['url']}  # {chemin + '/' if chemin else ''}{d['nom']}\n")
        print(vert(f"Liste exportée : {args.liste}  ({len(documents)} URLs)"))
        if not args.cookie_sortie:
            print(jaune("Astuce : ajoutez --cookie-sortie cookies.txt pour pouvoir télécharger ensuite."))
        sys.exit(0)

    # ── Téléchargement ───────────────────────────────────────────────────────
    # Tout est rangé dans un sous-dossier nommé d'après la classe.
    nom_classe = nom_sur(urlsplit(url).path.strip("/").split("/")[-1]) or "classe"
    dossier = Path(sortie) / nom_classe
    if not simulation:
        dossier.mkdir(parents=True, exist_ok=True)
        print(f"Destination : {gras(str(dossier.resolve()))}\n")

    total = len(documents)
    documents.sort(key=lambda d: (d.get("chemin", ""), d["nom"]))
    compteur = {"ok": 0, "existe": 0, "echec": 0, "simulation": 0}
    volume   = {"ok": 0, "existe": 0, "simulation": 0}
    for i, doc in enumerate(documents, 1):
        statut, taille = telecharger(session, doc, dossier, simulation, i, total)
        compteur[statut] = compteur.get(statut, 0) + 1
        if statut in volume:
            volume[statut] += taille
        if not simulation and args.delai:
            time.sleep(args.delai)

    # ── Résumé ───────────────────────────────────────────────────────────────
    print()
    print(gras("─── RÉSUMÉ " + "─" * 40))
    if simulation:
        print(f"  Documents à télécharger : {gras(str(compteur['simulation']))}")
        print(f"  Volume estimé           : {gras(fmt_taille(volume['simulation']))}")
        print(jaune("  (mode simulation — relancez sans --simulation pour télécharger)"))
    else:
        print(f"  Téléchargés   : {vert(str(compteur['ok']))}   ({fmt_taille(volume['ok'])})")
        if compteur["existe"]:
            print(f"  Déjà présents : {dim(str(compteur['existe']))}   ({fmt_taille(volume['existe'])})")
        if compteur["echec"]:
            print(f"  Échecs        : {rouge(str(compteur['echec']))}")
        total_disque = volume["ok"] + volume["existe"]
        print(f"  Volume total  : {gras(fmt_taille(total_disque))}")
        print(f"\n  Fichiers dans : {cyan(str(dossier.resolve()))}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(jaune("\nInterrompu par l'utilisateur."))
        sys.exit(130)
