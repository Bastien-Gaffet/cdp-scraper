#!/usr/bin/env python3
"""cdp_config — config mémorisée des classes pour cdp_scraper.

Liste de classes (url / login / dossier), JAMAIS le mot de passe. Module sans
dépendance réseau : tout est testable hors-ligne. Mêmes conventions que
cdp_manifeste (charger tolérant, enregistrer atomique, VERSION de schéma).
"""
import json
import os
from pathlib import Path

VERSION = 1
DOSSIER = ".cdp-scraper"
NOM_FICHIER = "config.json"


class ConfigVersionFuture(Exception):
    """La config a été écrite par une version plus récente de l'outil."""


class ClasseInconnue(Exception):
    """Un nom de classe demandé n'existe pas dans la config."""


def _vide() -> dict:
    return {"version": VERSION, "classes": []}


def charger(chemin: Path) -> dict:
    """Lit la config. Absente ou illisible → config vide (jamais d'erreur fatale).
    Lève ConfigVersionFuture si la version dépasse VERSION."""
    chemin = Path(chemin)
    if not chemin.is_file():
        return _vide()
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return _vide()
    if not isinstance(donnees, dict):
        return _vide()
    if donnees.get("version", 0) > VERSION:
        raise ConfigVersionFuture(
            f"Config en version {donnees.get('version')} > {VERSION} ; "
            "mettez l'outil à jour.")
    donnees.setdefault("version", VERSION)
    donnees.setdefault("classes", [])
    return donnees


def enregistrer(chemin: Path, config: dict) -> None:
    """Écrit la config de façon atomique (.part + renommage)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".part")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, chemin)
