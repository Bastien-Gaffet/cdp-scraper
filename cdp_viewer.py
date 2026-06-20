#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
import json
import mimetypes
import socketserver
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

PAGE_HTML = "<!doctype html><title>cdp-viewer</title>"  # remplacé en Task 5


def resoudre_dans_racine(racine: Path, demande: str) -> Path | None:
    """Résout `demande` (chemin relatif) sous `racine` et garantit qu'il y reste.

    Renvoie le Path résolu si la cible est la racine ou un descendant, sinon
    None (protection contre les `..` / chemins absolus / liens hors racine).
    L'existence n'est PAS vérifiée ici (404 géré ailleurs).
    """
    racine = racine.resolve()
    cible = (racine / demande).resolve()
    if cible == racine or racine in cible.parents:
        return cible
    return None


def lister_classes(racine: Path) -> list[str]:
    """Noms des sous-dossiers de `racine` (= les classes scrapées), triés."""
    if not racine.is_dir():
        return []
    return sorted(p.name for p in racine.iterdir() if p.is_dir())


def _noeud(racine: Path, chemin_abs: Path) -> dict:
    """Construit récursivement le nœud (dossier ou fichier) pour `chemin_abs`."""
    rel = chemin_abs.relative_to(racine).as_posix()
    if chemin_abs.is_dir():
        enfants = [_noeud(racine, p) for p in chemin_abs.iterdir()]
        # Dossiers d'abord, puis tri alphabétique insensible à la casse.
        enfants.sort(key=lambda n: (n["type"] != "dossier", n["nom"].lower()))
        return {"nom": chemin_abs.name, "type": "dossier", "chemin": rel, "enfants": enfants}
    ext = chemin_abs.suffix.lstrip(".").lower()
    return {
        "nom": chemin_abs.name,
        "type": "fichier",
        "chemin": rel,
        "taille": chemin_abs.stat().st_size,
        "ext": ext,
    }


def construire_arbre(racine: Path, classe: str) -> dict | None:
    """Arbre de la classe `classe` sous `racine`, ou None si elle n'existe pas.

    Les `chemin` des nœuds sont relatifs à `racine` (ils incluent le dossier de
    classe) et utilisables tels quels dans /file/<chemin>.
    """
    racine = racine.resolve()
    base = resoudre_dans_racine(racine, classe)
    if base is None or not base.is_dir():
        return None
    return _noeud(racine, base)


class GestionnaireCDP(BaseHTTPRequestHandler):
    """Sert la page, l'API JSON et les fichiers. `self.server.racine` = racine."""

    def _envoyer_octets(self, code: int, octets: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(octets)))
        self.end_headers()
        self.wfile.write(octets)

    def _envoyer_json(self, code: int, donnees):
        self._envoyer_octets(code, json.dumps(donnees).encode("utf-8"),
                             "application/json; charset=utf-8")

    def _erreur(self, code: int, message: str):
        self._envoyer_octets(code, message.encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self):
        parties = urllib.parse.urlparse(self.path)
        chemin = parties.path
        racine = self.server.racine

        if chemin == "/":
            self._envoyer_octets(200, PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if chemin == "/api/classes":
            self._envoyer_json(200, lister_classes(racine))
            return

        if chemin == "/api/tree":
            params = urllib.parse.parse_qs(parties.query)
            classe = (params.get("classe") or [""])[0]
            arbre = construire_arbre(racine, classe)
            if arbre is None:
                self._erreur(404, "Classe introuvable")
                return
            self._envoyer_json(200, arbre)
            return

        if chemin.startswith("/file/"):
            rel = urllib.parse.unquote(chemin[len("/file/"):])
            cible = resoudre_dans_racine(racine, rel)
            if cible is None:
                self._erreur(403, "Acces refuse")
                return
            if not cible.is_file():
                self._erreur(404, "Fichier introuvable")
                return
            ctype = mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
            self._envoyer_octets(200, cible.read_bytes(), ctype)
            return

        self._erreur(404, "Introuvable")

    def log_message(self, *args):  # silence: pas de log par requête
        pass


class ServeurCDP(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, adresse, handler, racine: Path):
        self.racine = racine.resolve()
        super().__init__(adresse, handler)


def creer_serveur(racine: Path, port: int) -> ServeurCDP:
    """Crée (sans démarrer) le serveur lié à 127.0.0.1 sur `port` (0 = éphémère)."""
    return ServeurCDP(("127.0.0.1", port), GestionnaireCDP, Path(racine))
