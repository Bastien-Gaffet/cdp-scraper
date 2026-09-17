#!/usr/bin/env python3
"""cdp_agenda — agenda de classe cahier-de-prepa.fr -> export .ics (DS).

Récupère les événements de l'agenda (page HTML, analysée par expressions
régulières comme cdp_scraper.analyser_page — pas de dépendance ajoutée),
filtre les devoirs surveillés et génère/relit un fichier .ics (RFC 5545,
généré à la main). Module importé par cdp_scraper.py (écriture) ET par
cdp_viewer.py (lecture pour affichage) : `requests` n'est donc jamais importé
au niveau module ici, seulement en local dans recuperer_agenda (seule
fonction qui en a besoin) — le viewer doit rester sans dépendance externe.
"""
from datetime import date


def mois_annee_scolaire(aujourdhui: date) -> list:
    """10 couples (année, mois) de septembre à juin, sur l'année scolaire
    contenant `aujourdhui` (bascule au 1er juillet)."""
    annee_debut = aujourdhui.year if aujourdhui.month >= 7 else aujourdhui.year - 1
    return [(annee_debut, m) for m in range(9, 13)] + \
           [(annee_debut + 1, m) for m in range(1, 7)]
