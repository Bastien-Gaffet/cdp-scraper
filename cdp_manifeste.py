#!/usr/bin/env python3
"""cdp_manifeste — schéma et logique du manifeste de synchronisation.

Module partagé par cdp_scraper (écrit) et cdp_viewer (lit). Aucune dépendance
réseau : tout est testable hors-ligne. Le manifeste recense, par classe, les
documents téléchargés et leur empreinte, pour ne re-télécharger que ce qui a
changé (synchro incrémentale) et dater les fichiers dans le viewer.
"""
import json
import hashlib
import os
from pathlib import Path

VERSION = 1
NOM_FICHIER = ".cdp-manifest.json"


class ManifesteVersionFuture(Exception):
    """Le manifeste a été écrit par une version plus récente de l'outil."""


def _vide() -> dict:
    return {"version": VERSION, "classe": "", "url": "",
            "derniere_synchro": "", "documents": {}}


def charger(dossier_classe: Path) -> dict:
    """Lit le manifeste de `dossier_classe`. Renvoie un manifeste vide s'il est
    absent ou illisible (JSON corrompu → on repart à neuf, jamais de perte de
    fichiers). Lève ManifesteVersionFuture si la version dépasse VERSION."""
    chemin = Path(dossier_classe) / NOM_FICHIER
    if not chemin.is_file():
        return _vide()
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        print(f"  [!] Manifeste illisible ({chemin}) : resynchronisation complète.")
        return _vide()
    if not isinstance(donnees, dict):
        return _vide()
    if donnees.get("version", 0) > VERSION:
        raise ManifesteVersionFuture(
            f"Manifeste en version {donnees.get('version')} > {VERSION} ; "
            "mettez l'outil à jour.")
    donnees.setdefault("documents", {})
    return donnees


def enregistrer(dossier_classe: Path, manifeste: dict) -> None:
    """Écrit le manifeste de façon atomique (fichier .tmp + renommage)."""
    dossier = Path(dossier_classe)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / NOM_FICHIER
    tmp = dossier / (NOM_FICHIER + ".tmp")
    tmp.write_text(json.dumps(manifeste, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, cible)


def empreinte(doc: dict) -> str:
    """Chaîne d'empreinte d'un document pour détecter un changement.

    - contenu généré localement (contenu_html) → hash court "h:<sha>".
    - document normal → chaîne docdonnees brute (champ "empreinte"), ou "".
    """
    contenu = doc.get("contenu_html")
    if contenu is not None:
        return "h:" + hashlib.sha256(contenu.encode("utf-8")).hexdigest()[:16]
    return doc.get("empreinte", "") or ""
