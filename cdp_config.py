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


def contient(config: dict, nom: str) -> bool:
    return any(c.get("nom") == nom for c in config.get("classes", []))


def ajouter_ou_maj(config: dict, classe: dict) -> dict:
    """Insère `classe` ou remplace l'entrée de même `nom`. Renvoie la config."""
    classes = config.setdefault("classes", [])
    for i, c in enumerate(classes):
        if c.get("nom") == classe.get("nom"):
            classes[i] = {**c, **classe}
            return config
    classes.append(classe)
    return config


def lister(config: dict) -> list:
    return list(config.get("classes", []))


def retirer(config: dict, nom: str) -> dict:
    config["classes"] = [c for c in config.get("classes", []) if c.get("nom") != nom]
    return config


def chemin_config(override=None) -> Path:
    """Résolution en cascade du fichier de config :
    1) `override` (flag --config) ;
    2) ./.cdp-scraper/config.json s'il existe (usage script, dossier courant) ;
    3) ~/.cdp-scraper/config.json (HOME — défaut lecture/écriture, prêt pour l'exe).
    """
    if override:
        return Path(override)
    local = Path.cwd() / DOSSIER / NOM_FICHIER
    if local.is_file():
        return local
    return Path.home() / DOSSIER / NOM_FICHIER


def selectionner(config: dict, noms: list) -> list:
    """Renvoie les entrées correspondant à `noms`, dans cet ordre. Lève
    ClasseInconnue (en listant les noms disponibles) si l'une manque."""
    par_nom = {c.get("nom"): c for c in config.get("classes", [])}
    choisies = []
    for nom in noms:
        if nom not in par_nom:
            dispo = ", ".join(sorted(n for n in par_nom if n)) or "(aucune)"
            raise ClasseInconnue(
                f"Classe inconnue : {nom!r}. Disponibles : {dispo}")
        choisies.append(par_nom[nom])
    return choisies
