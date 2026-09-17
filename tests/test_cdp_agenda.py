import unittest
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_agenda


class TestMoisAnneeScolaire(unittest.TestCase):
    def test_rentree_annee_courante(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2026, 9, 15))
        self.assertEqual(mois, [
            (2026, 9), (2026, 10), (2026, 11), (2026, 12),
            (2027, 1), (2027, 2), (2027, 3), (2027, 4), (2027, 5), (2027, 6),
        ])

    def test_milieu_annee_scolaire(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2027, 3, 1))
        self.assertEqual(mois[0], (2026, 9))
        self.assertEqual(mois[-1], (2027, 6))

    def test_bascule_au_30_juin(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2026, 6, 30))
        self.assertEqual(mois[0], (2025, 9))
        self.assertEqual(mois[-1], (2026, 6))


class TestParserDateAgenda(unittest.TestCase):
    def test_jour_seul_sans_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le vendredi 12 septembre 2026")
        self.assertEqual(debut, datetime(2026, 9, 12, 0, 0))
        self.assertIsNone(fin)
        self.assertTrue(journee)

    def test_jour_seul_avec_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le vendredi 12 septembre 2026 à 8h")
        self.assertEqual(debut, datetime(2026, 9, 12, 8, 0))
        self.assertEqual(fin, datetime(2026, 9, 12, 8, 0))
        self.assertFalse(journee)

    def test_jour_seul_avec_plage_horaire(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le dimanche 1er mars 2027 de 8h à 12h30")
        self.assertEqual(debut, datetime(2027, 3, 1, 8, 0))
        self.assertEqual(fin, datetime(2027, 3, 1, 12, 30))
        self.assertFalse(journee)

    def test_plusieurs_jours_sans_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Du vendredi 12 septembre 2026 au dimanche 14 septembre 2026")
        self.assertEqual(debut, datetime(2026, 9, 12, 0, 0))
        self.assertEqual(fin, datetime(2026, 9, 14, 0, 0))
        self.assertTrue(journee)

    def test_plusieurs_jours_avec_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Du vendredi 12 septembre 2026 à 8h au samedi 13 septembre 2026 à 12h")
        self.assertEqual(debut, datetime(2026, 9, 12, 8, 0))
        self.assertEqual(fin, datetime(2026, 9, 13, 12, 0))
        self.assertFalse(journee)

    def test_texte_non_reconnu_leve_valueerror(self):
        with self.assertRaises(ValueError):
            cdp_agenda.parser_date_agenda("pas une date")


def _bloc(id_, date_texte, type_, matiere="", texte="Texte.", titre_grille=None):
    """Construit un extrait de page agenda.php (grille + bloc détaillé) pour
    un événement, comme le fait le vrai logiciel cahier-de-prepa."""
    if titre_grille is None:
        titre_grille = f"{matiere} - {type_}" if matiere else type_
    h4 = f"{type_} en {matiere}" if matiere else type_
    return (
        f'<td data-id="{id_}"><p class="evnmt4">{titre_grille}</p></td>'
        f'<article data-id="{id_}">'
        f'<h3 class="titreagenda">{date_texte}</h3>'
        f'<h4>{h4}</h4><p>{texte}</p></article>'
    )


class TestAnalyserPageAgenda(unittest.TestCase):
    def test_evenement_avec_matiere(self):
        page = _bloc("1", "Le vendredi 12 septembre 2026 à 8h",
                     "Devoir surveillé", "Mathématiques", texte="Chapitres 1 à 3.")
        evenements = cdp_agenda.analyser_page_agenda(page)
        self.assertEqual(len(evenements), 1)
        ev = evenements[0]
        self.assertEqual(ev["id"], "1")
        self.assertEqual(ev["type"], "Devoir surveillé")
        self.assertEqual(ev["matiere"], "Mathématiques")
        self.assertEqual(ev["debut"], datetime(2026, 9, 12, 8, 0))
        self.assertEqual(ev["fin"], datetime(2026, 9, 12, 8, 0))
        self.assertFalse(ev["journee_entiere"])
        self.assertEqual(ev["texte"], "Chapitres 1 à 3.")

    def test_evenement_sans_matiere(self):
        page = _bloc("2", "Le lundi 15 septembre 2026", "Cours")
        evenements = cdp_agenda.analyser_page_agenda(page)
        self.assertEqual(evenements[0]["matiere"], "")
        self.assertEqual(evenements[0]["type"], "Cours")

    def test_prefixe_heure_dans_la_grille_est_retire(self):
        # Quand hd != 0h00, la grille préfixe le titre par "8h : ...".
        page = _bloc("3", "Le mardi 15 septembre 2026 à 8h", "Devoir surveillé",
                     "Physique", titre_grille="8h : Physique - Devoir surveillé")
        evenements = cdp_agenda.analyser_page_agenda(page)
        self.assertEqual(evenements[0]["type"], "Devoir surveillé")
        self.assertEqual(evenements[0]["matiere"], "Physique")

    def test_evenement_sur_plusieurs_jours(self):
        page = _bloc("4",
                     "Du vendredi 12 septembre 2026 à 8h au samedi 13 septembre 2026 à 12h",
                     "Devoir surveillé", "Mathématiques")
        ev = cdp_agenda.analyser_page_agenda(page)[0]
        self.assertEqual(ev["debut"], datetime(2026, 9, 12, 8, 0))
        self.assertEqual(ev["fin"], datetime(2026, 9, 13, 12, 0))

    def test_page_sans_agenda_renvoie_liste_vide(self):
        self.assertEqual(cdp_agenda.analyser_page_agenda("<div id='calendrier'></div>"), [])

    def test_bloc_mode_edition_est_ignore_sans_crash(self):
        # Compte avec droits d'édition : <p class="titreagenda edition"
        # data-donnees='...'> au lieu de <h3>/<h4> — non géré, ignoré proprement.
        page = (
            '<article data-id="9" data-protection="0" data-edition="0">'
            '<p class="titreagenda edition" data-donnees=\'{"tid":4,"mid":2,'
            '"debut":"12/09/2026 8h00","fin":"12/09/2026 8h00","jours":false}\'>'
            'Le vendredi 12 septembre 2026 à 8h<br>Devoir surveillé en Mathématiques</p>'
            '</article>'
        )
        self.assertEqual(cdp_agenda.analyser_page_agenda(page), [])

    def test_date_non_reconnue_est_ignoree_sans_crash(self):
        page = (
            '<td data-id="5"><p class="evnmt4">Cours</p></td>'
            '<article data-id="5"><h3 class="titreagenda">une date bizarre</h3>'
            '<h4>Cours</h4><p>Texte.</p></article>'
        )
        self.assertEqual(cdp_agenda.analyser_page_agenda(page), [])


import requests


class _FakeRespAgenda:
    def __init__(self, text):
        self.text = text


class _FakeSessionAgenda:
    """Session hors-ligne : renvoie une page figée par URL ; enregistre les
    appels ; peut simuler un échec réseau sur certaines URLs."""

    def __init__(self, pages, echecs=()):
        self.pages = pages
        self.echecs = set(echecs)
        self.appels = []

    def get(self, url, timeout=None):
        self.appels.append(url)
        if url in self.echecs:
            raise requests.RequestException("boom")
        return _FakeRespAgenda(self.pages.get(url, ""))


class TestRecupererAgenda(unittest.TestCase):
    BASE = "https://x/mpsi"

    def _url(self, annee, mois):
        return f"{self.BASE}/agenda?mois={annee % 100:02d}{mois:02d}"

    def test_fusionne_les_mois_sans_doublon_et_interroge_10_mois(self):
        aujourdhui = date(2026, 9, 15)
        pages = {
            self._url(2026, 9): _bloc("1", "Le vendredi 4 septembre 2026", "Devoir surveillé"),
            self._url(2026, 10): _bloc("1", "Le vendredi 4 septembre 2026", "Devoir surveillé"),
        }
        session = _FakeSessionAgenda(pages)
        evenements = cdp_agenda.recuperer_agenda(session, self.BASE, aujourdhui=aujourdhui)
        self.assertEqual(len(evenements), 1)
        self.assertEqual(len(session.appels), 10)

    def test_echec_reseau_sur_un_mois_n_arrete_pas_les_autres(self):
        aujourdhui = date(2026, 9, 15)
        pages = {self._url(2026, 10): _bloc("2", "Le lundi 5 octobre 2026", "Devoir surveillé")}
        session = _FakeSessionAgenda(pages, echecs=[self._url(2026, 9)])
        evenements = cdp_agenda.recuperer_agenda(session, self.BASE, aujourdhui=aujourdhui)
        self.assertEqual(len(evenements), 1)
        self.assertEqual(evenements[0]["id"], "2")


class TestFiltrerDS(unittest.TestCase):
    def _ev(self, type_):
        return {"id": "1", "type": type_, "matiere": "", "debut": datetime(2026, 9, 1),
                "fin": None, "journee_entiere": True, "texte": ""}

    def test_garde_devoir_surveille(self):
        self.assertEqual(len(cdp_agenda.filtrer_ds([self._ev("Devoir surveillé")])), 1)

    def test_insensible_casse_et_accents(self):
        evenements = [self._ev("DEVOIR SURVEILLE"), self._ev("devoir survéillé")]
        self.assertEqual(len(cdp_agenda.filtrer_ds(evenements)), 2)

    def test_ecarte_les_autres_types(self):
        evenements = [self._ev("Devoir maison"), self._ev("Cours"), self._ev("Vacances")]
        self.assertEqual(cdp_agenda.filtrer_ds(evenements), [])


if __name__ == "__main__":
    unittest.main()
