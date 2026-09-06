#!/usr/bin/env python3
"""cdp_maj — vérification et mise à jour du projet depuis GitHub.

Vérifie une fois par jour au plus si une version plus récente est publiée
(releases GitHub), et peut mettre à jour les fichiers du projet sur place
(git pull si dépôt Git, sinon remplacement atomique des fichiers depuis le
dépôt). Stdlib pur (urllib, json, subprocess) : aucune dépendance ajoutée,
y compris pour cdp_viewer.py qui doit rester sans dépendance externe.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

DOSSIER = ".cdp-scraper"
NOM_FICHIER = "maj.json"
DELAI_CACHE = timedelta(hours=24)

EXTENSIONS_MAJ = (".py",)
FICHIERS_MAJ = {"requirements.txt", "requirements-dev.txt", "README.md",
                "CHANGELOG.md", "LICENSE"}


def chemin_maj(override=None) -> Path:
    """Résolution en cascade du fichier de cache (même logique que
    cdp_config.chemin_config) :
    1) `override` ;
    2) ./.cdp-scraper/maj.json s'il existe ;
    3) ~/.cdp-scraper/maj.json (HOME — défaut).
    """
    if override:
        return Path(override)
    local = Path.cwd() / DOSSIER / NOM_FICHIER
    if local.is_file():
        return local
    return Path.home() / DOSSIER / NOM_FICHIER


def charger(chemin: Path) -> dict:
    """Lit le cache. Absent ou illisible → dict vide (jamais d'erreur fatale,
    pas de notion de version de schéma : un cache invalide se régénère au
    prochain essai)."""
    chemin = Path(chemin)
    if not chemin.is_file():
        return {}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return donnees if isinstance(donnees, dict) else {}


def enregistrer(chemin: Path, donnees: dict) -> None:
    """Écrit le cache de façon atomique (.part + renommage)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".part")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, chemin)


def _version_tuple(s: str) -> tuple:
    """Parse "1.5.0" ou "v1.5.0" en (1, 5, 0). Renvoie () si le format est
    inattendu (la comparaison est alors toujours False, jamais d'exception)."""
    s = s.strip()
    if s[:1] in ("v", "V"):
        s = s[1:]
    try:
        return tuple(int(m) for m in s.split("."))
    except ValueError:
        return ()


def derniere_version_github(depot: str, timeout: float = 2.0):
    """GET /repos/<depot>/releases/latest. Renvoie le tag sans préfixe `v`,
    ou None pour toute erreur (réseau, timeout, JSON invalide, code HTTP,
    clé absente) — ne lève jamais."""
    url = f"https://api.github.com/repos/{depot}/releases/latest"
    requete = urllib.request.Request(url, headers={"User-Agent": "cdp-scraper"})
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
        return str(donnees["tag_name"]).lstrip("vV")
    except (OSError, ValueError, KeyError):
        return None


def verifier_maj(version_locale: str, chemin_cache: Path, depot: str):
    """Renvoie la version distante si elle est plus récente que
    `version_locale`, sinon None. Au plus un appel réseau par 24 h (mis en
    cache) ; le cache est mis à jour même en cas d'échec, pour ne pas
    retenter l'appel à chaque run tant qu'on est hors-ligne."""
    cache = charger(chemin_cache)
    maintenant = datetime.now()
    derniere_verif = cache.get("derniere_verif")
    assez_recent = False
    if derniere_verif:
        try:
            assez_recent = maintenant - datetime.fromisoformat(derniere_verif) < DELAI_CACHE
        except ValueError:
            assez_recent = False

    if assez_recent:
        connue = cache.get("derniere_version_connue")
    else:
        connue = derniere_version_github(depot)
        cache["derniere_verif"] = maintenant.isoformat(timespec="seconds")
        if connue:
            cache["derniere_version_connue"] = connue
        else:
            connue = cache.get("derniere_version_connue")
        enregistrer(chemin_cache, cache)

    if connue and _version_tuple(connue) > _version_tuple(version_locale):
        return connue
    return None
