#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
import argparse
import json
import mimetypes
import os
import socketserver
import subprocess
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path

PAGE_HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cdp-viewer</title>
<style>
:root {
  --bg:#f7f7f8; --panel:#fff; --txt:#1d1d1f; --muted:#6b6b70;
  --border:#e3e3e6; --accent:#2563eb; --hover:#eef2ff;
}
[data-theme="dark"] {
  --bg:#16171a; --panel:#1f2024; --txt:#e7e7ea; --muted:#9a9aa2;
  --border:#2c2d33; --accent:#6ea0ff; --hover:#262b3b;
}
* { box-sizing:border-box; }
body { margin:0; font:14px/1.5 system-ui,sans-serif; color:var(--txt);
  background:var(--bg); height:100vh; display:flex; flex-direction:column; }
header { display:flex; gap:12px; align-items:center; padding:10px 14px;
  background:var(--panel); border-bottom:1px solid var(--border); }
header h1 { font-size:16px; margin:0; white-space:nowrap; }
header .grow { flex:1; }
select, input, button { font:inherit; color:var(--txt); background:var(--bg);
  border:1px solid var(--border); border-radius:8px; padding:6px 10px; }
button { cursor:pointer; }
a { color:inherit; text-decoration:none; }
main { flex:1; display:flex; min-height:0; }

#rubriques { width:240px; overflow:auto; padding:10px; background:var(--panel);
  border-right:1px solid var(--border); flex-shrink:0; }
.rubrique { display:block; padding:8px 10px; border-radius:8px; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; margin-bottom:2px; }
.rubrique:hover { background:var(--hover); }
.rubrique.actif { background:var(--accent); color:#fff; }
.rubrique.actif .ico { color:#fff; }

#explorateur { flex:1; overflow:auto; padding:16px 24px; }
.fil { display:flex; flex-wrap:wrap; gap:4px; align-items:center; margin-bottom:16px;
  color:var(--txt); }
.fil a { color:var(--txt); }
.fil a:hover { text-decoration:underline; }
.fil .sep { color:var(--muted); }
.fil .courant { color:var(--txt); }

.liste { display:flex; flex-direction:column; }
.ligne { display:flex; align-items:center; gap:10px; padding:8px;
  border-bottom:1px solid var(--border); }
.ligne:hover { background:var(--hover); }
.ico { display:inline-flex; align-items:center; flex-shrink:0; color:var(--muted); }
.ico svg { display:block; }
.ligne.dossier .ico { color:var(--accent); }
.ligne .nom { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ligne.dossier .nom { font-weight:600; }
.ligne .meta { color:var(--muted); font-size:12px; margin-left:auto; flex-shrink:0;
  padding-left:12px; }
.vide { color:var(--muted); padding:24px 0; }
#theme { display:inline-flex; align-items:center; }
.fil a, .fil .courant { display:inline-flex; align-items:center; gap:4px; }
</style>
</head>
<body>
<header>
  <h1>cdp-viewer</h1>
  <select id="classe" title="Classe"></select>
  <input id="recherche" class="grow" placeholder="Rechercher un document&hellip;">
  <button id="theme" title="Mode sombre"></button>
</header>
<main>
  <nav id="rubriques"></nav>
  <section id="explorateur"></section>
</main>
<script>
const elRubriques = document.getElementById("rubriques");
const elExplorateur = document.getElementById("explorateur");
const elClasse = document.getElementById("classe");
const elRecherche = document.getElementById("recherche");

let arbres = {};          // cache : nom de classe -> nœud racine
let classesDispo = [];

// Icônes SVG (suivent la couleur du texte, sans emoji).
const ICONES = {
  dossier: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7z"/></svg>',
  document: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v5h5"/><path d="M7 3h7l5 5v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/></svg>',
  accueil: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l9-8 9 8"/><path d="M5 10v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9"/></svg>',
  theme: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
};
// Extensions que le navigateur sait afficher (sinon : ouverture dans l'explorateur).
const VISIONNABLES = new Set([
  "pdf","png","jpg","jpeg","gif","webp","svg","bmp","ico",
  "txt","md","markdown","csv","tsv","py","tex","json","log","c","cpp","java","ml","sql","r",
  "html","htm","mp3","wav","ogg","mp4","webm","m4a","mov"
]);
function elIcone(nom) {
  const s = document.createElement("span");
  s.className = "ico"; s.innerHTML = ICONES[nom];
  return s;
}
function urlReveal(c) {
  return "/reveal/" + c.split("/").map(encodeURIComponent).join("/");
}

function octets(n) {
  if (n < 1024) return n + " o";
  if (n < 1048576) return (n/1024).toFixed(1) + " Ko";
  return (n/1048576).toFixed(1) + " Mo";
}
// Lien navigable : un dossier pointe vers un hash (#chemin), un document vers
// une vraie URL /file/... (navigation réelle => retour via le navigateur).
function urlFichier(c) {
  return "/file/" + c.split("/").map(encodeURIComponent).join("/");
}
function hashDe(chemin) {
  return "#" + chemin.split("/").map(encodeURIComponent).join("/");
}
function nbElements(noeud) {
  const n = (noeud.enfants || []).length;
  return n + (n > 1 ? " éléments" : " élément");
}
function tri(enfants) {
  return (enfants || []).slice().sort(
    (a, b) => (a.type !== "dossier") - (b.type !== "dossier")
              || a.nom.localeCompare(b.nom, "fr", {sensitivity:"base"}));
}
function trouver(noeud, chemin) {
  if (noeud.chemin === chemin) return noeud;
  for (const e of (noeud.enfants || []))
    if (e.type === "dossier") { const t = trouver(e, chemin); if (t) return t; }
  return null;
}

// ── Une ligne de la liste (dossier ou document) ─────────────────────────────
function ligne(noeud) {
  const dossier = noeud.type === "dossier";
  const a = document.createElement("a");
  a.className = "ligne " + (dossier ? "dossier" : "doc");
  if (dossier) {
    a.href = hashDe(noeud.chemin);                       // navigation dans l'arbre
  } else if (VISIONNABLES.has((noeud.ext || "").toLowerCase())) {
    a.href = urlFichier(noeud.chemin);                   // ouverture pleine page
  } else {
    a.href = urlReveal(noeud.chemin);                    // ouvrir (ou révéler dans l'explorateur)
    a.title = "Ouvrir avec l'application associée, sinon afficher dans l'explorateur";
    a.onclick = (e) => { e.preventDefault(); fetch(urlReveal(noeud.chemin)); };
  }
  const nom = document.createElement("span");
  nom.className = "nom"; nom.textContent = noeud.nom;
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = dossier ? "(" + nbElements(noeud) + ")"
    : "(" + (noeud.ext ? noeud.ext.toUpperCase() + " · " : "") + octets(noeud.taille) + ")";
  a.appendChild(elIcone(dossier ? "dossier" : "document"));
  a.appendChild(nom); a.appendChild(meta);
  return a;
}

// ── Fil d'Ariane (chaque segment = un hash) ─────────────────────────────────
function rendreFil(arbre, cible) {
  const fil = document.createElement("div");
  fil.className = "fil";
  const segs = cible.chemin.split("/");
  segs.forEach((seg, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "sep"; sep.textContent = "/"; fil.appendChild(sep);
    }
    const prefixe = segs.slice(0, i + 1).join("/");
    const dernier = i === segs.length - 1;
    const el = document.createElement(dernier ? "span" : "a");
    if (dernier) el.className = "courant"; else el.href = hashDe(prefixe);
    if (i === 0) el.appendChild(elIcone("accueil"));
    el.appendChild(document.createTextNode((i === 0 ? " " : "") + seg));
    fil.appendChild(el);
  });
  return fil;
}

// ── Vue liste du dossier courant ────────────────────────────────────────────
function rendreListe(arbre, cible) {
  elExplorateur.innerHTML = "";
  elExplorateur.appendChild(rendreFil(arbre, cible));
  const enfants = tri(cible.enfants);
  if (!enfants.length) {
    const v = document.createElement("div"); v.className = "vide";
    v.textContent = "Dossier vide.";
    elExplorateur.appendChild(v);
    return;
  }
  const liste = document.createElement("div"); liste.className = "liste";
  enfants.forEach(e => liste.appendChild(ligne(e)));
  elExplorateur.appendChild(liste);
}

// ── Rubriques (dossiers de 1er niveau) ──────────────────────────────────────
function rendreRubriques(arbre, cible) {
  elRubriques.innerHTML = "";
  const segs = cible.chemin.split("/");
  const actifTop = segs.length > 1 ? segs[1] : null;
  const accueil = document.createElement("a");
  accueil.className = "rubrique" + (actifTop === null ? " actif" : "");
  accueil.href = hashDe(arbre.chemin);
  accueil.appendChild(elIcone("accueil"));
  accueil.appendChild(document.createTextNode(" Accueil"));
  elRubriques.appendChild(accueil);
  tri(arbre.enfants).filter(e => e.type === "dossier").forEach(d => {
    const r = document.createElement("a");
    r.className = "rubrique" + (d.nom === actifTop ? " actif" : "");
    r.href = hashDe(d.chemin); r.title = d.nom;
    r.appendChild(elIcone("dossier"));
    r.appendChild(document.createTextNode(" " + d.nom));
    elRubriques.appendChild(r);
  });
}

// ── Recherche (tous les documents de la classe par nom) ─────────────────────
function collecter(noeud, acc) {
  (noeud.enfants || []).forEach(e => {
    if (e.type === "dossier") collecter(e, acc); else acc.push(e);
  });
  return acc;
}
function rechercher(arbre, q) {
  elExplorateur.innerHTML = "";
  const fil = document.createElement("div"); fil.className = "fil";
  fil.textContent = "Résultats pour « " + q + " »";
  elExplorateur.appendChild(fil);
  const trouves = collecter(arbre, []).filter(f => f.nom.toLowerCase().includes(q));
  if (!trouves.length) {
    const v = document.createElement("div"); v.className = "vide";
    v.textContent = "Aucun document ne correspond.";
    elExplorateur.appendChild(v);
    return;
  }
  const liste = document.createElement("div"); liste.className = "liste";
  trouves.sort((a, b) => a.nom.localeCompare(b.nom, "fr", {sensitivity:"base"}))
         .forEach(f => liste.appendChild(ligne(f)));
  elExplorateur.appendChild(liste);
}

// ── Routage : le hash de l'URL porte le dossier courant ─────────────────────
async function naviguer() {
  const hash = decodeURIComponent(location.hash.slice(1));
  const classe = hash.split("/")[0] || classesDispo[0];
  if (!classe) return;
  if (!arbres[classe]) {
    const r = await fetch("/api/tree?classe=" + encodeURIComponent(classe));
    if (r.ok) arbres[classe] = await r.json();
  }
  const arbre = arbres[classe];
  if (!arbre) {                       // classe inconnue (lien périmé)
    if (classesDispo.length) location.hash = encodeURIComponent(classesDispo[0]);
    return;
  }
  if (elClasse.value !== classe) elClasse.value = classe;
  elRecherche.value = "";
  const cible = trouver(arbre, hash) || arbre;
  rendreRubriques(arbre, cible);
  rendreListe(arbre, cible);
}

async function init() {
  const r = await fetch("/api/classes");
  classesDispo = await r.json();
  if (!classesDispo.length) {
    elExplorateur.innerHTML =
      "<div class='vide'>Aucun cours trouvé.<br>Lancez d'abord <code>cdp_scraper.py</code>.</div>";
    return;
  }
  classesDispo.forEach(c => {
    const o = document.createElement("option"); o.value = c; o.textContent = c; elClasse.appendChild(o);
  });
  elClasse.onchange = () => { location.hash = encodeURIComponent(elClasse.value); };
  if (location.hash) naviguer();
  else location.hash = encodeURIComponent(classesDispo[0]);
}

window.addEventListener("hashchange", naviguer);
elRecherche.oninput = () => {
  const q = elRecherche.value.trim().toLowerCase();
  const arbre = arbres[elClasse.value];
  if (!arbre) return;
  if (q === "") naviguer(); else rechercher(arbre, q);
};
document.getElementById("theme").innerHTML = ICONES.theme;
document.getElementById("theme").onclick = () => {
  const sombre = document.documentElement.getAttribute("data-theme") === "dark";
  document.documentElement.setAttribute("data-theme", sombre ? "light" : "dark");
  localStorage.setItem("cdp-theme", sombre ? "light" : "dark");
};
if (localStorage.getItem("cdp-theme") === "dark")
  document.documentElement.setAttribute("data-theme", "dark");

init();
</script>
</body>
</html>"""


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


def _noeud(racine: Path, chemin_abs: Path) -> dict:
    """Construit récursivement le nœud (dossier ou fichier) pour `chemin_abs`."""
    rel = chemin_abs.relative_to(racine).as_posix()
    if chemin_abs.is_dir():
        enfants = [_noeud(racine, p) for p in chemin_abs.iterdir()]
        # Dossiers d'abord, puis tri alphabétique insensible à la casse.
        enfants.sort(key=lambda n: (n["type"] != "dossier", n["nom"].lower()))
        return {"nom": chemin_abs.name, "type": "dossier", "chemin": rel, "enfants": enfants}
    ext = chemin_abs.suffix.lstrip(".").lower()
    return {
        "nom": chemin_abs.name,
        "type": "fichier",
        "chemin": rel,
        "taille": chemin_abs.stat().st_size,
        "ext": ext,
    }


def construire_arbre(racine: Path, classe: str) -> dict | None:
    """Arbre de la classe `classe` sous `racine`, ou None si elle n'existe pas.

    Les `chemin` des nœuds sont relatifs à `racine` (ils incluent le dossier de
    classe) et utilisables tels quels dans /file/<chemin>.
    """
    racine = racine.resolve()
    base = resoudre_dans_racine(racine, classe)
    if base is None or not base.is_dir():
        return None
    return _noeud(racine, base)


# Extensions servies en text/plain pour s'afficher dans le navigateur plutôt
# que de se télécharger (sinon le type MIME deviné déclencherait un download).
EXT_TEXTE = {"txt", "md", "markdown", "csv", "tsv", "py", "tex", "json", "log",
             "c", "cpp", "java", "ml", "sql", "r"}


def reveler_dans_explorateur(cible: Path):
    """Affiche `cible` dans l'explorateur de fichiers du système (sélectionné)."""
    chemin = str(cible)
    if sys.platform == "win32":
        # explorer.exe exige les guillemets AUTOUR DU CHEMIN SEUL. En mode liste,
        # subprocess quote tout l'argument « /select,<chemin> » (à cause des
        # espaces/accents), et explorer abandonne en ouvrant le dossier Documents.
        # On passe donc la ligne de commande en chaîne, avec le bon découpage.
        subprocess.run(f'explorer /select,"{chemin}"')
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", chemin])
    else:
        subprocess.run(["xdg-open", str(cible.parent)])


def ouvrir_ou_reveler(cible: Path):
    """Ouvre `cible` avec son application associée si elle est installée,
    sinon la révèle (sélectionnée) dans l'explorateur de fichiers.

    Cas d'usage : un .ggb s'ouvre dans GeoGebra s'il est installé ; sinon
    l'utilisateur retrouve le fichier dans l'explorateur pour décider quoi en
    faire (plutôt qu'un téléchargement silencieux par le navigateur).
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(cible))  # lance l'app associée (GeoGebra, Word…)
            return
        except OSError:
            pass  # aucune application associée → on révèle dans l'explorateur
    elif sys.platform == "darwin":
        # open échoue (code != 0) s'il n'y a pas d'app associée → on révèle.
        if subprocess.run(["open", str(cible)]).returncode == 0:
            return
    else:
        if subprocess.run(["xdg-open", str(cible)]).returncode == 0:
            return
    reveler_dans_explorateur(cible)


class GestionnaireCDP(BaseHTTPRequestHandler):
    """Sert la page, l'API JSON et les fichiers. `self.server.racine` = racine."""

    def _envoyer_octets(self, code: int, octets: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(octets)))
        self.end_headers()
        self.wfile.write(octets)

    def _envoyer_json(self, code: int, donnees):
        self._envoyer_octets(code, json.dumps(donnees).encode("utf-8"),
                             "application/json; charset=utf-8")

    def _erreur(self, code: int, message: str):
        self._envoyer_octets(code, message.encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self):
        parties = urllib.parse.urlparse(self.path)
        chemin = parties.path
        racine = self.server.racine

        if chemin == "/":
            self._envoyer_octets(200, PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if chemin == "/api/classes":
            self._envoyer_json(200, lister_classes(racine))
            return

        if chemin == "/api/tree":
            params = urllib.parse.parse_qs(parties.query)
            classe = (params.get("classe") or [""])[0]
            arbre = construire_arbre(racine, classe)
            if arbre is None:
                self._erreur(404, "Classe introuvable")
                return
            self._envoyer_json(200, arbre)
            return

        if chemin.startswith("/file/"):
            rel = urllib.parse.unquote(chemin[len("/file/"):])
            cible = resoudre_dans_racine(racine, rel)
            if cible is None:
                self._erreur(403, "Acces refuse")
                return
            if not cible.is_file():
                self._erreur(404, "Fichier introuvable")
                return
            ext = cible.suffix.lstrip(".").lower()
            if ext in EXT_TEXTE:
                ctype = "text/plain; charset=utf-8"
            else:
                ctype = mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
            self._envoyer_octets(200, cible.read_bytes(), ctype)
            return

        if chemin.startswith("/reveal/"):
            rel = urllib.parse.unquote(chemin[len("/reveal/"):])
            cible = resoudre_dans_racine(racine, rel)
            if cible is None:
                self._erreur(403, "Acces refuse")
                return
            if not cible.exists():
                self._erreur(404, "Fichier introuvable")
                return
            try:
                ouvrir_ou_reveler(cible)
            except Exception:
                pass
            self.send_response(204)
            self.end_headers()
            return

        self._erreur(404, "Introuvable")

    def log_message(self, *args):  # silence: pas de log par requête
        pass


class ServeurCDP(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, adresse, handler, racine: Path):
        self.racine = racine.resolve()
        super().__init__(adresse, handler)


def creer_serveur(racine: Path, port: int) -> ServeurCDP:
    """Crée (sans démarrer) le serveur lié à 127.0.0.1 sur `port` (0 = éphémère)."""
    return ServeurCDP(("127.0.0.1", port), GestionnaireCDP, Path(racine))


def main():
    p = argparse.ArgumentParser(
        description="Visualiseur web local des cours téléchargés par cdp_scraper.")
    p.add_argument("--dossier", default="cours_cdp", metavar="CHEMIN",
                   help="Dossier racine des cours (défaut : cours_cdp)")
    p.add_argument("--port", type=int, default=8000,
                   help="Port d'écoute (défaut : 8000)")
    p.add_argument("--no-browser", action="store_true",
                   help="Ne pas ouvrir le navigateur automatiquement")
    args = p.parse_args()

    racine = Path(args.dossier)
    if not racine.is_dir():
        print(f"Dossier introuvable : {racine.resolve()}")
        print("Lancez d'abord cdp_scraper.py, ou indiquez --dossier <chemin>.")

    serveur = creer_serveur(racine, args.port)
    url = f"http://127.0.0.1:{serveur.server_address[1]}"
    print(f"cdp-viewer en écoute sur {url}  (Ctrl+C pour arrêter)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        serveur.shutdown()
        serveur.server_close()


if __name__ == "__main__":
    main()
