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


_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,})(.*)$")
_FENCE_FIN = re.compile(r"^ {0,3}`{3,}\s*$")
_TITRE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^ {0,3}([-*_])(\s*\1){2,}\s*$")
_CITATION = re.compile(r"^ {0,3}>")
_SEP_TABLE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _est_debut_bloc(ligne):
    return bool(_FENCE.match(ligne) or _TITRE.match(ligne)
                or _CITATION.match(ligne) or _ITEM.match(ligne)
                or _HR.match(ligne))


def _bloc_code(code, lang, colorier_python):
    cle = lang.strip().lower()
    colore = None
    if cle in ("py", "python") and colorier_python is not None:
        colore = colorier_python(code)
    elif cle in cdp_coloration.LANGAGES:
        colore = cdp_coloration.colorier(code, cle)
    corps = colore if colore is not None else html.escape(code)
    return "<pre><code>%s</code></pre>" % corps


def _rendre_liste(items, i, prefixe_url):
    """Rend la sous-liste dont l'indentation == celle de items[i].
    `items` : liste de (indent, ordonnee, contenu). Renvoie (html, i)."""
    indent = items[i][0]
    tag = "ol" if items[i][1] else "ul"
    out = ["<%s>" % tag]
    while i < len(items) and items[i][0] == indent:
        contenu = rendre_inline(items[i][2], prefixe_url)
        i += 1
        if i < len(items) and items[i][0] > indent:
            sous, i = _rendre_liste(items, i, prefixe_url)
            out.append("<li>%s%s</li>" % (contenu, sous))
        else:
            out.append("<li>%s</li>" % contenu)
    out.append("</%s>" % tag)
    return "".join(out), i


def _table(lignes, i, n, prefixe_url):
    def cellules(l):
        l = l.strip()
        if l.startswith("|"):
            l = l[1:]
        if l.endswith("|"):
            l = l[:-1]
        return [c.strip() for c in l.split("|")]

    out = ["<table><thead><tr>"]
    for c in cellules(lignes[i]):
        out.append("<th>%s</th>" % rendre_inline(c, prefixe_url))
    out.append("</tr></thead><tbody>")
    i += 2  # saute l'en-tête et la ligne de séparation
    while i < n and lignes[i].strip() and "|" in lignes[i]:
        out.append("<tr>")
        for c in cellules(lignes[i]):
            out.append("<td>%s</td>" % rendre_inline(c, prefixe_url))
        out.append("</tr>")
        i += 1
    out.append("</tbody></table>")
    return "".join(out), i


def convertir(source, prefixe_url="", colorier_python=None):
    """Convertit `source` (Markdown) en HTML sûr.

    `prefixe_url` : URL du dossier du .md (pour résoudre images/liens relatifs).
    `colorier_python` : callback optionnel (code -> HTML) pour les blocs ```python
    — injecté par le viewer pour réutiliser son coloriseur tokenize."""
    lignes = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lignes)
    out = []
    i = 0
    while i < n:
        ligne = lignes[i]

        m = _FENCE.match(ligne)
        if m:
            lang = m.group(2)
            i += 1
            corps = []
            while i < n and not _FENCE_FIN.match(lignes[i]):
                corps.append(lignes[i])
                i += 1
            i += 1  # saute la clôture (ou la fin du fichier)
            out.append(_bloc_code("\n".join(corps), lang, colorier_python))
            continue

        if ligne.strip() == "":
            i += 1
            continue

        m = _TITRE.match(ligne)
        if m:
            niv = len(m.group(1))
            out.append("<h%d>%s</h%d>"
                       % (niv, rendre_inline(m.group(2), prefixe_url), niv))
            i += 1
            continue

        if _HR.match(ligne):
            out.append("<hr>")
            i += 1
            continue

        if _CITATION.match(ligne):
            bloc = []
            while i < n and _CITATION.match(lignes[i]):
                bloc.append(re.sub(r"^ {0,3}>\s?", "", lignes[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>"
                       % convertir("\n".join(bloc), prefixe_url, colorier_python))
            continue

        if ("|" in ligne and i + 1 < n and _SEP_TABLE.match(lignes[i + 1])):
            html_table, i = _table(lignes, i, n, prefixe_url)
            out.append(html_table)
            continue

        if _ITEM.match(ligne):
            items = []
            while i < n and _ITEM.match(lignes[i]):
                mi = _ITEM.match(lignes[i])
                ordonnee = mi.group(2)[0] not in "-*+"
                items.append((len(mi.group(1)), ordonnee, mi.group(3)))
                i += 1
            html_liste, _ = _rendre_liste(items, 0, prefixe_url)
            out.append(html_liste)
            continue

        para = []
        while (i < n and lignes[i].strip() != ""
               and not _est_debut_bloc(lignes[i])):
            para.append(lignes[i].strip())
            i += 1
        out.append("<p>%s</p>" % rendre_inline(" ".join(para), prefixe_url))

    return "\n".join(out)
