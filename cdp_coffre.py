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


_TEMOIN_CLAIR = b"cdp-coffre-ok"
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_TAILLE_CLE = 32
_TAILLE_SEL = 16
_TAILLE_NONCE = 12


def _derive_cle(mdp_maitre: str, sel: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    kdf = Scrypt(salt=sel, length=_TAILLE_CLE, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(mdp_maitre.encode("utf-8"))


def _chiffrer(cle: bytes, associated_data: bytes, clair: bytes) -> dict:
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(_TAILLE_NONCE)
    chiffre = AESGCM(cle).encrypt(nonce, clair, associated_data)
    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "chiffre": base64.b64encode(chiffre).decode("ascii"),
    }


def _dechiffrer(cle: bytes, associated_data: bytes, bloc: dict) -> bytes:
    import base64
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = base64.b64decode(bloc["nonce"])
    chiffre = base64.b64decode(bloc["chiffre"])
    try:
        return AESGCM(cle).decrypt(nonce, chiffre, associated_data)
    except InvalidTag:
        raise MotDePasseMaitreIncorrect("Mot de passe maître incorrect.") from None


def creer(mdp_maitre: str) -> dict:
    """Nouveau coffre vide, avec un sel et un témoin fraîchement générés."""
    import base64
    coffre = _vide()
    sel = os.urandom(_TAILLE_SEL)
    coffre["kdf"] = {
        "algorithme": "scrypt",
        "sel": base64.b64encode(sel).decode("ascii"),
        "n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P,
    }
    cle = _derive_cle(mdp_maitre, sel)
    coffre["temoin"] = _chiffrer(cle, b"temoin", _TEMOIN_CLAIR)
    return coffre


def deverrouiller(coffre: dict, mdp_maitre: str) -> bytes:
    """Dérive la clé et vérifie le témoin. Lève MotDePasseMaitreIncorrect si
    le mot de passe maître est faux."""
    import base64
    sel = base64.b64decode(coffre["kdf"]["sel"])
    cle = _derive_cle(mdp_maitre, sel)
    _dechiffrer(cle, b"temoin", coffre["temoin"])
    return cle


def ajouter(coffre: dict, mdp_maitre: str, nom: str, mdp_classe: str) -> dict:
    """Enregistre (ou remplace) le mot de passe de `nom`. Initialise le
    coffre si c'est le tout premier usage (aucune vérification du mot de
    passe maître dans ce cas : rien à vérifier contre)."""
    if not est_initialise(coffre):
        coffre.update(creer(mdp_maitre))
    cle = deverrouiller(coffre, mdp_maitre)
    coffre["entrees"][nom] = _chiffrer(cle, nom.encode("utf-8"), mdp_classe.encode("utf-8"))
    return coffre


def recuperer(coffre: dict, mdp_maitre: str, nom: str) -> str:
    """Déchiffre le mot de passe de `nom`. Lève MotDePasseMaitreIncorrect ou
    ClasseAbsenteDuCoffre."""
    if nom not in coffre.get("entrees", {}):
        raise ClasseAbsenteDuCoffre(f"Aucun mot de passe enregistré pour « {nom} ».")
    cle = deverrouiller(coffre, mdp_maitre)
    clair = _dechiffrer(cle, nom.encode("utf-8"), coffre["entrees"][nom])
    return clair.decode("utf-8")
