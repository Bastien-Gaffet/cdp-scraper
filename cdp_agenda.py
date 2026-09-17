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
import re
from datetime import date, datetime, time


def mois_annee_scolaire(aujourdhui: date) -> list:
    """10 couples (année, mois) de septembre à juin, sur l'année scolaire
    contenant `aujourdhui` (bascule au 1er juillet)."""
    annee_debut = aujourdhui.year if aujourdhui.month >= 7 else aujourdhui.year - 1
    return [(annee_debut, m) for m in range(9, 13)] + \
           [(annee_debut + 1, m) for m in range(1, 7)]


_JOURS_SEM = "lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"
_NOMS_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]
_INDEX_MOIS = {nom: i + 1 for i, nom in enumerate(_NOMS_MOIS)}

# Un fragment de date au format produit par cahier-de-prepa (voir
# fonctions.php::format_date) : "vendredi 12 septembre 2026", optionnellement
# suivi de "à 8h30" ou (seulement pour un événement d'un seul jour) "de 8h à
# 12h30". Groupes : 1=jour 2=mois 3=année 4=heure simple 5=min simple
# 6=heure début plage 7=min début plage 8=heure fin plage 9=min fin plage.
_RE_DATE = re.compile(
    r"(?:" + _JOURS_SEM + r") (\d{1,2})(?:er)? (" + "|".join(_NOMS_MOIS) + r") (\d{4})"
    r"(?: à (\d{1,2})h(\d{2})?| de (\d{1,2})h(\d{2})? à (\d{1,2})h(\d{2})?)?"
)


def _valeurs_date(m):
    """(date, heure_debut|None, heure_fin|None) depuis un match de _RE_DATE."""
    d = date(int(m.group(3)), _INDEX_MOIS[m.group(2)], int(m.group(1)))
    if m.group(6):      # "de Hh à H2h" (plage, un seul jour)
        h1 = time(int(m.group(6)), int(m.group(7) or 0))
        h2 = time(int(m.group(8)), int(m.group(9) or 0))
        return d, h1, h2
    if m.group(4):      # "à Hh"
        h = time(int(m.group(4)), int(m.group(5) or 0))
        return d, h, h
    return d, None, None


def parser_date_agenda(texte: str):
    """Parse le texte de <h3 class="titreagenda"> (ou équivalent) : "Le ..."
    (un seul jour) ou "Du ... au ..." (plusieurs jours). Renvoie
    (debut: datetime, fin: datetime|None, journee_entiere: bool). Lève
    ValueError si aucune date n'est reconnue."""
    correspondances = list(_RE_DATE.finditer(texte))
    if not correspondances:
        raise ValueError(f"Date d'agenda non reconnue : {texte!r}")

    if len(correspondances) == 1:
        d, h1, h2 = _valeurs_date(correspondances[0])
        if h1 is None:
            return datetime.combine(d, time(0, 0)), None, True
        return datetime.combine(d, h1), datetime.combine(d, h2), False

    d1, h1a, _ = _valeurs_date(correspondances[0])
    d2, h2a, h2b = _valeurs_date(correspondances[1])
    if h1a is None and h2a is None:
        return datetime.combine(d1, time(0, 0)), datetime.combine(d2, time(0, 0)), True
    debut = datetime.combine(d1, h1a or time(0, 0))
    fin = datetime.combine(d2, h2b or h2a or time(0, 0))
    return debut, fin, False
