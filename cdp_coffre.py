#!/usr/bin/env python3
"""cdp_coffre — coffre chiffré local pour les mots de passe de classes.

Chiffrement AES-256-GCM, clé dérivée d'un mot de passe maître via Scrypt.
Le mot de passe maître n'est jamais écrit sur disque. `cryptography` n'est
importée qu'à l'intérieur des fonctions qui en ont réellement besoin (jamais
au niveau module) : un appelant qui ne fait que lire/écrire la structure
(`charger`, `enregistrer`, `contient`, `lister`, `retirer`) n'a besoin
d'aucune dépendance supplémentaire. Mêmes conventions que cdp_config
(charger tolérant, enregistrer atomique, VERSION de schéma).
"""
import json
import os
from pathlib import Path

VERSION = 1
DOSSIER = ".cdp-scraper"
NOM_FICHIER = "coffre.json"


class CoffreVersionFuture(Exception):
    """Le coffre a été écrit par une version plus récente de l'outil."""


class MotDePasseMaitreIncorrect(Exception):
    """Le mot de passe maître ne permet pas de déchiffrer le témoin/l'entrée."""


class ClasseAbsenteDuCoffre(Exception):
    """Aucun mot de passe enregistré pour cette classe."""


def _vide() -> dict:
    return {"version": VERSION, "entrees": {}}


def charger(chemin: Path) -> dict:
    """Lit le coffre. Absent ou illisible → coffre vide (jamais d'erreur fatale).
    Lève CoffreVersionFuture si la version dépasse VERSION."""
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
        raise CoffreVersionFuture(
            f"Coffre en version {donnees.get('version')} > {VERSION} ; "
            "mettez l'outil à jour.")
    donnees.setdefault("version", VERSION)
    donnees.setdefault("entrees", {})
    return donnees


def enregistrer(chemin: Path, coffre: dict) -> None:
    """Écrit le coffre de façon atomique (.part + renommage)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".part")
    tmp.write_text(json.dumps(coffre, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, chemin)


def chemin_coffre(override=None) -> Path:
    """Résolution en cascade du fichier de coffre (même logique que
    cdp_config.chemin_config) :
    1) `override` (flag --coffre) ;
    2) ./.cdp-scraper/coffre.json s'il existe ;
    3) ~/.cdp-scraper/coffre.json (HOME — défaut).
    """
    if override:
        return Path(override)
    local = Path.cwd() / DOSSIER / NOM_FICHIER
    if local.is_file():
        return local
    return Path.home() / DOSSIER / NOM_FICHIER


def est_initialise(coffre: dict) -> bool:
    return "kdf" in coffre and "temoin" in coffre
