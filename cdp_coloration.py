#!/usr/bin/env python3
"""cdp_coloration — coloration syntaxique générique multi-langages.

Un moteur regex unique, paramétré par une table de specs (un jeu de mots-clés et
de délimiteurs par langage), produit du HTML échappé + <span class="kw|str|com|
num"> réutilisant les classes CSS de la page de code du viewer.

Python n'est PAS géré ici : le viewer garde son coloriseur `tokenize`, plus
précis. Bibliothèque standard uniquement.
"""
import html
import re

VERSION = 1


class SpecLangage:
    """Décrit comment colorier un langage (mots-clés + styles de délimiteurs)."""

    def __init__(self, mots_cles, commentaire_ligne=(), commentaire_bloc=None,
                 guillemets=('"',), insensible_casse=False):
        self.insensible_casse = insensible_casse
        self.mots_cles = frozenset(
            (m.lower() if insensible_casse else m) for m in mots_cles)
        self.commentaire_ligne = tuple(commentaire_ligne)
        self.commentaire_bloc = commentaire_bloc      # (ouvre, ferme) ou None
        self.guillemets = tuple(guillemets)


def _mots(chaine):
    return chaine.split()


_KW_C = _mots(
    "auto break case char const continue default do double else enum extern "
    "float for goto if inline int long register restrict return short signed "
    "sizeof static struct switch typedef union unsigned void volatile while")
_KW_CPP = _KW_C + _mots(
    "bool catch class constexpr delete dynamic_cast explicit false friend "
    "mutable namespace new nullptr operator private protected public "
    "reinterpret_cast static_cast template this throw true try typename using "
    "virtual")
_KW_JAVA = _mots(
    "abstract assert boolean break byte case catch char class const continue "
    "default do double else enum extends final finally float for goto if "
    "implements import instanceof int interface long native new package "
    "private protected public return short static strictfp super switch "
    "synchronized this throw throws transient try void volatile while true "
    "false null var")
_KW_SQL = _mots(
    "select from where insert into values update delete create table drop alter "
    "add column primary key foreign references join inner left right outer full "
    "on group by order asc desc having distinct as and or not null is in like "
    "between union all limit offset set index view default constraint check "
    "unique cascade exists case when then else end count sum avg min max")
_KW_R = _mots(
    "if else for while repeat function return break next in TRUE FALSE NULL NA "
    "Inf NaN library require")
_KW_ML = _mots(
    "let rec in and fun function match with type of module struct sig end if "
    "then else begin do done while for to downto try raise exception open "
    "include val mutable ref true false as when")
_KW_JSON = _mots("true false null")

LANGAGES = {
    "c": SpecLangage(_KW_C, commentaire_ligne=("//",),
                     commentaire_bloc=("/*", "*/"), guillemets=('"', "'")),
    "cpp": SpecLangage(_KW_CPP, commentaire_ligne=("//",),
                       commentaire_bloc=("/*", "*/"), guillemets=('"', "'")),
    "java": SpecLangage(_KW_JAVA, commentaire_ligne=("//",),
                        commentaire_bloc=("/*", "*/"), guillemets=('"', "'")),
    "sql": SpecLangage(_KW_SQL, commentaire_ligne=("--",),
                       commentaire_bloc=("/*", "*/"), guillemets=("'", '"'),
                       insensible_casse=True),
    "r": SpecLangage(_KW_R, commentaire_ligne=("#",),
                     guillemets=('"', "'")),
    "ml": SpecLangage(_KW_ML, commentaire_bloc=("(*", "*)"),
                      guillemets=('"',)),
    "json": SpecLangage(_KW_JSON, guillemets=('"',)),
}

_CACHE_RX = {}


def _regex_pour(spec):
    """Construit la regex alternée (groupes nommés) pour `spec`.

    Ordre = priorité : commentaire bloc, commentaire ligne, chaîne, nombre,
    identifiant. Tout le reste (espaces, ponctuation) tombe dans les intervalles
    entre correspondances et est émis tel quel (échappé).

    Limitations assumées pour v1.4 (le texte source reste toujours préservé) :
    - commentaires OCaml imbriqués `(* (* *) *)` non gérés (un simple .*? non
      glouton s'arrête au premier `*)`) ;
    - littéraux hexadécimaux (0x...) et chaînes multilignes non colorés."""
    parties = []
    if spec.commentaire_bloc:
        o, f = spec.commentaire_bloc
        parties.append(r"(?P<com_bloc>%s.*?%s)" % (re.escape(o), re.escape(f)))
    if spec.commentaire_ligne:
        alt = "|".join(re.escape(c) for c in spec.commentaire_ligne)
        parties.append(r"(?P<com_ligne>(?:%s)[^\n]*)" % alt)
    if spec.guillemets:
        sous = []
        for q in spec.guillemets:
            eq = re.escape(q)
            sous.append(r"%s(?:\\.|[^%s\\\n])*%s" % (eq, eq, eq))
        parties.append(r"(?P<chaine>%s)" % "|".join(sous))
    parties.append(r"(?P<nombre>\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)")
    parties.append(r"(?P<mot>[A-Za-z_]\w*)")
    return re.compile("|".join(parties), re.DOTALL)


def colorier(source, langage):
    """Rend `source` en HTML coloré pour `langage`, ou None si langage inconnu.

    Garantit que le rendu, balises retirées, reproduit exactement
    `html.escape(source, quote=False)` (chaque tranche est émise après
    échappement HTML)."""
    spec = LANGAGES.get(langage)
    if spec is None:
        return None
    rx = _CACHE_RX.get(langage)
    if rx is None:
        rx = _CACHE_RX[langage] = _regex_pour(spec)
    out = []
    pos = 0
    for m in rx.finditer(source):
        if m.start() > pos:
            out.append(html.escape(source[pos:m.start()], quote=False))
        txt = m.group()
        esc = html.escape(txt, quote=False)
        nom = m.lastgroup
        if nom in ("com_bloc", "com_ligne"):
            out.append('<span class="com">%s</span>' % esc)
        elif nom == "chaine":
            out.append('<span class="str">%s</span>' % esc)
        elif nom == "nombre":
            out.append('<span class="num">%s</span>' % esc)
        elif nom == "mot":
            cle = txt.lower() if spec.insensible_casse else txt
            out.append('<span class="kw">%s</span>' % esc
                       if cle in spec.mots_cles else esc)
        else:
            # filet de sécurité : ne devrait pas arriver
            out.append(esc)
        pos = m.end()
    if pos < len(source):
        out.append(html.escape(source[pos:], quote=False))
    return "".join(out)
