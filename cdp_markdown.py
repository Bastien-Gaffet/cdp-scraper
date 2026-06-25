#!/usr/bin/env python3
"""cdp_markdown — convertisseur Markdown → HTML sûr (côté serveur, stdlib).

Couverture « essentiel + tables GFM » : titres, paragraphes, listes imbriquées,
blocs de code clôturés (avec coloration via cdp_coloration / callback Python),
citations, règles, tables, et inline (gras, italique, code, liens, images).

Sécurité : tout le texte est échappé, seule une liste blanche de balises est
émise, et les URL de liens/images sont assainies (schémas http/https et chemins
relatifs confinés sous /file/ ; le reste est neutralisé). Bibliothèque standard
uniquement.
"""
import html
import posixpath
import re
import urllib.parse

import cdp_coloration  # utilisé par convertir (blocs de code colorés), ajouté à la Task 3

VERSION = 1

_SCHEMES_OK = ("http://", "https://")

_CODE = re.compile(r"`([^`]+)`")
_IMG = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)\)")
_LIEN = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_GRAS = re.compile(r"(\*\*|__)(.+?)\1")
_ITAL = re.compile(r"(?<![\w*])(\*|_)(?!\s)(.+?)(?<!\s)\1(?![\w*])")


def _url_sure(url, prefixe_url):
    """URL sûre pour href/src, ou None à neutraliser.

    - http:// et https:// : conservées.
    - chemin relatif : résolu et confiné sous `prefixe_url` (dossier du .md) ;
      tout ce qui en sort renvoie None. C'est l'appelant qui garantit que
      `prefixe_url` pointe sous l'arborescence /file/.
    - tout le reste (javascript:, data:, //, mailto:, ancre #, absolu) : None.
    """
    u = url.strip()
    if not u:
        return None
    bas = u.lower()
    if bas.startswith(_SCHEMES_OK):
        return u
    if ("://" in bas or u.startswith("/")
            or bas.startswith(("javascript:", "data:", "vbscript:",
                               "mailto:", "//", "#"))):
        return None
    if not prefixe_url:
        return None
    segs = [urllib.parse.quote(s) for s in u.split("/")]
    joint = posixpath.normpath(prefixe_url + "/" + "/".join(segs))
    # Confiné : le chemin résolu doit rester sous prefixe_url (et donc sous /file/)
    if joint == prefixe_url or joint.startswith(prefixe_url + "/"):
        return joint
    return None


def rendre_inline(texte, prefixe_url=""):
    """Rend les éléments inline d'une portion de texte en HTML sûr.

    Méthode : on « gèle » d'abord le code/les liens/les images en jetons HTML
    sûrs (\\x00 n \\x00), on échappe tout le texte restant, on applique l'emphase,
    puis on réinjecte les jetons. L'emphase ne peut donc pas pénétrer le code ni
    casser une balise déjà générée."""
    texte = texte.replace("\x00", "")   # neutralise toute forge de jeton (\x00 n \x00)
    jetons = []

    def _placer(html_sur):
        jetons.append(html_sur)
        return "\x00%d\x00" % (len(jetons) - 1)

    def _img(m):
        alt, url = m.group(1), m.group(2)
        sure = _url_sure(url, prefixe_url)
        if sure is None:
            return alt                       # neutralisée : alt en texte
        return _placer('<img src="%s" alt="%s">'
                       % (html.escape(sure, quote=True),
                          html.escape(alt, quote=True)))

    def _lien(m):
        libelle, url = m.group(1), m.group(2)
        sure = _url_sure(url, prefixe_url)
        if sure is None:
            return libelle                   # neutralisé : libellé en texte
        externe = sure.lower().startswith(_SCHEMES_OK)
        attrs = ' target="_blank" rel="noopener noreferrer"' if externe else ""
        return _placer('<a href="%s"%s>%s</a>'
                       % (html.escape(sure, quote=True), attrs,
                          html.escape(libelle)))

    texte = _CODE.sub(
        lambda m: _placer("<code>%s</code>" % html.escape(m.group(1))), texte)
    texte = _IMG.sub(_img, texte)
    texte = _LIEN.sub(_lien, texte)
    texte = html.escape(texte)
    texte = _GRAS.sub(lambda m: "<strong>%s</strong>" % m.group(2), texte)
    texte = _ITAL.sub(lambda m: "<em>%s</em>" % m.group(2), texte)
    texte = re.sub(r"\x00(\d+)\x00", lambda m: jetons[int(m.group(1))], texte)
    return texte
