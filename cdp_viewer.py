#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
import argparse
import json
import mimetypes
import socketserver
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
main { flex:1; display:flex; min-height:0; }

#rubriques { width:240px; overflow:auto; padding:10px; background:var(--panel);
  border-right:1px solid var(--border); flex-shrink:0; }
.rubrique { padding:8px 10px; border-radius:8px; cursor:pointer; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; margin-bottom:2px; }
.rubrique:hover { background:var(--hover); }
.rubrique.actif { background:var(--accent); color:#fff; }

#explorateur { flex:1; overflow:auto; padding:16px; }
.fil { display:flex; flex-wrap:wrap; gap:4px; align-items:center; margin-bottom:16px;
  color:var(--muted); }
.fil a { color:var(--accent); cursor:pointer; text-decoration:none; }
.fil a:hover { text-decoration:underline; }
.fil .sep { color:var(--muted); }
.grille { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; }
.carte { display:flex; align-items:center; gap:10px; padding:12px; border-radius:10px;
  border:1px solid var(--border); background:var(--panel); cursor:pointer; min-width:0; }
.carte:hover { background:var(--hover); border-color:var(--accent); }
.carte .ico { font-size:22px; flex-shrink:0; }
.carte .info { min-width:0; }
.carte .nom { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.carte .meta { color:var(--muted); font-size:12px; }
.vide { color:var(--muted); padding:24px 0; }

#document { position:fixed; inset:0; z-index:50; background:var(--bg);
  display:flex; flex-direction:column; }
#document .barre { display:flex; gap:14px; align-items:center; padding:10px 14px;
  background:var(--panel); border-bottom:1px solid var(--border); }
#document .barre .titre { font-weight:600; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; flex:1; }
#document .corps { flex:1; overflow:auto; display:flex; flex-direction:column; }
#document iframe, #document img { width:100%; flex:1; border:0; }
#document img { object-fit:contain; }
#document pre { margin:0; padding:16px; white-space:pre-wrap; word-break:break-word; }
#document .corps .vide { margin:auto; text-align:center; }
a.dl { color:var(--accent); text-decoration:none; }
.cache { display:none !important; }
</style>
</head>
<body>
<header>
  <h1>&#128218; cdp-viewer</h1>
  <select id="classe" title="Classe"></select>
  <input id="recherche" class="grow" placeholder="&#128269; Rechercher un document&hellip;">
  <button id="theme" title="Mode sombre">&#127769;</button>
</header>
<main>
  <nav id="rubriques"></nav>
  <section id="explorateur"></section>
</main>
<div id="document" class="cache">
  <div class="barre">
    <button id="retour">&#8592; Retour</button>
    <span class="titre" id="doc-titre"></span>
    <a class="dl" id="doc-dl" download>&#11015; Télécharger</a>
  </div>
  <div class="corps" id="doc-corps"></div>
</div>
<script>
const IMAGES = ["png","jpg","jpeg","gif","webp","svg","bmp"];
const TEXTES = ["txt","md","markdown","csv","tsv","py","tex","json","log","html","htm","c","cpp","java"];
const elRubriques = document.getElementById("rubriques");
const elExplorateur = document.getElementById("explorateur");
const elClasse = document.getElementById("classe");
const elRecherche = document.getElementById("recherche");
const elDocument = document.getElementById("document");

let arbreClasse = null;   // nœud racine de la classe courante
let chemin = [];          // pile de dossiers depuis la racine de la classe

function octets(n) {
  if (n < 1024) return n + " o";
  if (n < 1048576) return (n/1024).toFixed(1) + " Ko";
  return (n/1048576).toFixed(1) + " Mo";
}
function urlFichier(c) {
  return "/file/" + c.split("/").map(encodeURIComponent).join("/");
}
function dossierCourant() {
  return chemin.length ? chemin[chemin.length - 1] : arbreClasse;
}
function tri(enfants) {
  return (enfants || []).slice().sort(
    (a, b) => (a.type !== "dossier") - (b.type !== "dossier")
              || a.nom.localeCompare(b.nom, "fr", {sensitivity:"base"}));
}

// ── Carte d'un élément (dossier ou fichier) ─────────────────────────────────
function carte(noeud) {
  const c = document.createElement("div");
  c.className = "carte";
  const dossier = noeud.type === "dossier";
  const ico = document.createElement("span");
  ico.className = "ico";
  ico.textContent = dossier ? "📁" : "📄";
  const info = document.createElement("div");
  info.className = "info";
  const nom = document.createElement("div");
  nom.className = "nom"; nom.textContent = noeud.nom; nom.title = noeud.nom;
  info.appendChild(nom);
  if (!dossier) {
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = (noeud.ext ? noeud.ext.toUpperCase() + " · " : "") + octets(noeud.taille);
    info.appendChild(meta);
  }
  c.appendChild(ico); c.appendChild(info);
  c.onclick = dossier ? () => { chemin.push(noeud); rendreExplorateur(); }
                      : () => ouvrirDocument(noeud);
  return c;
}

// ── Fil d'Ariane ────────────────────────────────────────────────────────────
function rendreFil() {
  const fil = document.createElement("div");
  fil.className = "fil";
  const accueil = document.createElement("a");
  accueil.textContent = "🏠 " + (arbreClasse ? arbreClasse.nom : "Accueil");
  accueil.onclick = () => { chemin = []; rendreExplorateur(); rendreRubriques(); };
  fil.appendChild(accueil);
  chemin.forEach((d, i) => {
    const sep = document.createElement("span"); sep.className = "sep"; sep.textContent = "/";
    fil.appendChild(sep);
    const a = document.createElement("a"); a.textContent = d.nom;
    a.onclick = () => { chemin = chemin.slice(0, i + 1); rendreExplorateur(); };
    fil.appendChild(a);
  });
  return fil;
}

// ── Vue explorateur (contenu du dossier courant) ────────────────────────────
function rendreExplorateur() {
  elExplorateur.innerHTML = "";
  if (!arbreClasse) return;
  elExplorateur.appendChild(rendreFil());
  const enfants = tri(dossierCourant().enfants);
  if (!enfants.length) {
    const v = document.createElement("div"); v.className = "vide";
    v.textContent = "Dossier vide.";
    elExplorateur.appendChild(v);
    return;
  }
  const grille = document.createElement("div"); grille.className = "grille";
  enfants.forEach(e => grille.appendChild(carte(e)));
  elExplorateur.appendChild(grille);
  rendreRubriques();
}

// ── Recherche (tous les fichiers de la classe par nom) ──────────────────────
function collecter(noeud, acc) {
  (noeud.enfants || []).forEach(e => {
    if (e.type === "dossier") collecter(e, acc); else acc.push(e);
  });
  return acc;
}
function rechercher(q) {
  elExplorateur.innerHTML = "";
  const fil = document.createElement("div"); fil.className = "fil";
  fil.textContent = "Résultats pour « " + q + " »";
  elExplorateur.appendChild(fil);
  const trouves = collecter(arbreClasse, []).filter(f => f.nom.toLowerCase().includes(q));
  if (!trouves.length) {
    const v = document.createElement("div"); v.className = "vide";
    v.textContent = "Aucun document ne correspond.";
    elExplorateur.appendChild(v);
    return;
  }
  const grille = document.createElement("div"); grille.className = "grille";
  trouves.sort((a, b) => a.nom.localeCompare(b.nom, "fr", {sensitivity:"base"}))
         .forEach(f => grille.appendChild(carte(f)));
  elExplorateur.appendChild(grille);
}

// ── Rubriques (1er niveau seulement) ────────────────────────────────────────
function rendreRubriques() {
  elRubriques.innerHTML = "";
  if (!arbreClasse) return;
  const accueil = document.createElement("div");
  accueil.className = "rubrique" + (chemin.length === 0 ? " actif" : "");
  accueil.textContent = "🏠 Accueil";
  accueil.onclick = () => { chemin = []; rendreExplorateur(); };
  elRubriques.appendChild(accueil);
  tri(arbreClasse.enfants).filter(e => e.type === "dossier").forEach(d => {
    const r = document.createElement("div");
    r.className = "rubrique" + (chemin[0] === d ? " actif" : "");
    r.textContent = "📁 " + d.nom; r.title = d.nom;
    r.onclick = () => { chemin = [d]; rendreExplorateur(); };
    elRubriques.appendChild(r);
  });
}

// ── Ouverture d'un document en plein écran ──────────────────────────────────
function ouvrirDocument(noeud) {
  const url = urlFichier(noeud.chemin);
  const ext = (noeud.ext || "").toLowerCase();
  document.getElementById("doc-titre").textContent = noeud.nom;
  const dl = document.getElementById("doc-dl");
  dl.href = url; dl.setAttribute("download", noeud.nom);
  const corps = document.getElementById("doc-corps");
  corps.innerHTML = "";
  if (ext === "pdf") {
    const f = document.createElement("iframe"); f.src = url; corps.appendChild(f);
  } else if (IMAGES.includes(ext)) {
    const i = document.createElement("img"); i.src = url; i.alt = noeud.nom; corps.appendChild(i);
  } else if (TEXTES.includes(ext)) {
    fetch(url).then(r => r.text()).then(t => {
      const pre = document.createElement("pre"); pre.textContent = t; corps.appendChild(pre);
    });
  } else {
    const v = document.createElement("div"); v.className = "vide";
    v.innerHTML = "Aperçu indisponible pour ce type.<br>Utilisez « Télécharger ».";
    corps.appendChild(v);
  }
  elDocument.classList.remove("cache");
}
function fermerDocument() {
  elDocument.classList.add("cache");
  document.getElementById("doc-corps").innerHTML = "";
}

// ── Chargement / init ───────────────────────────────────────────────────────
async function chargerClasse(classe) {
  elExplorateur.innerHTML = "Chargement…";
  const r = await fetch("/api/tree?classe=" + encodeURIComponent(classe));
  if (!r.ok) { elExplorateur.textContent = "Erreur de chargement."; return; }
  arbreClasse = await r.json();
  chemin = [];
  elRecherche.value = "";
  rendreRubriques();
  rendreExplorateur();
}

async function init() {
  const r = await fetch("/api/classes");
  const classes = await r.json();
  if (!classes.length) {
    elExplorateur.innerHTML =
      "<div class='vide'>Aucun cours trouvé.<br>Lancez d'abord <code>cdp_scraper.py</code>.</div>";
    return;
  }
  classes.forEach(c => {
    const o = document.createElement("option"); o.value = c; o.textContent = c; elClasse.appendChild(o);
  });
  elClasse.onchange = () => chargerClasse(elClasse.value);
  chargerClasse(classes[0]);
}

elRecherche.oninput = () => {
  const q = elRecherche.value.trim().toLowerCase();
  if (q === "") rendreExplorateur(); else rechercher(q);
};
document.getElementById("retour").onclick = fermerDocument;
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !elDocument.classList.contains("cache")) fermerDocument();
});
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
            ctype = mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
            self._envoyer_octets(200, cible.read_bytes(), ctype)
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
