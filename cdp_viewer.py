#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
from pathlib import Path


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
