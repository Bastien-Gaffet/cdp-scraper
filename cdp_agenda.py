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
import html as _html_mod
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


RE_ARTICLE = re.compile(r'<article\s+data-id="(\d+)"[^>]*>(.*?)</article>', re.DOTALL)
RE_H3 = re.compile(r'<h3 class="titreagenda">(.*?)</h3>', re.DOTALL)
RE_H4 = re.compile(r'<h4>(.*?)</h4>', re.DOTALL)
RE_P = re.compile(r'<p>(.*?)</p>', re.DOTALL)
RE_GRID = re.compile(r'<td data-id="(\d+)"><p class="evnmt\d+[^"]*">(.*?)</p></td>', re.DOTALL)
RE_HEURE_PREFIXE = re.compile(r'^\d{1,2}h\d{0,2}\s*:\s*')


def _texte(s: str) -> str:
    return _html_mod.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _type_matiere(titre_grille, titre_h4):
    """Sépare type et matière. La grille utilise " - " (fiable) ; à défaut,
    repli sur le " en " du bloc détaillé (ambigu si la matière contient
    elle-même ce mot, mais suffisant en dernier recours)."""
    if titre_grille:
        texte = RE_HEURE_PREFIXE.sub('', titre_grille).strip()
        if ' - ' in texte:
            matiere, type_ = texte.split(' - ', 1)
            return type_.strip(), matiere.strip()
        return texte, ''
    if ' en ' in titre_h4:
        type_, matiere = titre_h4.rsplit(' en ', 1)
        return type_.strip(), matiere.strip()
    return titre_h4, ''


def analyser_page_agenda(html_page: str) -> list:
    """Analyse une page mensuelle de l'agenda (compte en lecture seule —
    cas normal pour un élève). Un bloc en mode édition (droits d'édition sur
    l'agenda) n'a pas de <h3>/<h4> et est silencieusement ignoré, de même
    qu'un texte de date non reconnu : jamais d'exception."""
    titres_grille = {i: _texte(t) for i, t in RE_GRID.findall(html_page)}
    evenements = []
    for id_, corps in RE_ARTICLE.findall(html_page):
        h3 = RE_H3.search(corps)
        h4 = RE_H4.search(corps)
        if not h3 or not h4:
            continue
        try:
            debut, fin, journee_entiere = parser_date_agenda(_texte(h3.group(1)))
        except ValueError:
            continue
        type_, matiere = _type_matiere(titres_grille.get(id_), _texte(h4.group(1)))
        p = RE_P.search(corps)
        evenements.append({
            "id": id_, "type": type_, "matiere": matiere,
            "debut": debut, "fin": fin, "journee_entiere": journee_entiere,
            "texte": _texte(p.group(1)) if p else "",
        })
    return evenements


from time import sleep


def recuperer_agenda(session, base: str, aujourdhui=None, delai: float = 0.0) -> list:
    """Parcourt agenda?mois=YYMM pour chaque mois de l'année scolaire
    contenant `aujourdhui` (aujourd'hui par défaut), fusionne les événements
    par identifiant (un même événement vu sur deux mois voisins n'apparaît
    qu'une fois). Un mois en échec réseau est simplement ignoré — jamais
    d'exception qui remonte.

    `requests` est importé ici (et non au niveau module) : cdp_viewer.py
    importe aussi cdp_agenda pour lire les .ics déjà générés, et doit rester
    sans dépendance externe ; seule cette fonction (jamais appelée par le
    viewer) a besoin de requests."""
    import requests
    aujourdhui = aujourdhui or date.today()
    fusion = {}
    for annee, mois in mois_annee_scolaire(aujourdhui):
        url = f"{base}/agenda?mois={annee % 100:02d}{mois:02d}"
        try:
            page = session.get(url, timeout=20).text
        except requests.RequestException:
            continue
        for ev in analyser_page_agenda(page):
            fusion[ev["id"]] = ev
        if delai:
            sleep(delai)
    return list(fusion.values())


import unicodedata


def _normaliser(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return s.lower()


def filtrer_ds(evenements: list) -> list:
    """Garde les événements dont le type normalisé (minuscules, sans accents)
    contient 'surveille' — couvre le nom par défaut "Devoir surveillé" sans
    exiger une correspondance exacte."""
    return [e for e in evenements if 'surveille' in _normaliser(e['type'])]
