#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
import json
import mimetypes
import socketserver
import urllib.parse
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
#arbre { width:320px; overflow:auto; padding:10px; background:var(--panel);
  border-right:1px solid var(--border); }
#apercu { flex:1; overflow:auto; padding:0; display:flex; flex-direction:column; }
#apercu .vide { margin:auto; color:var(--muted); }
#apercu iframe, #apercu img { width:100%; flex:1; border:0; }
#apercu img { object-fit:contain; }
#apercu pre { margin:0; padding:16px; white-space:pre-wrap; word-break:break-word; }
.barre { padding:8px 14px; border-bottom:1px solid var(--border);
  background:var(--panel); display:flex; gap:12px; align-items:center; }
.dossier > .ligne::before { content:"\25B8 "; color:var(--muted); }
.dossier.ouvert > .ligne::before { content:"\25BE "; color:var(--muted); }
.ligne { padding:3px 6px; border-radius:6px; cursor:pointer; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.ligne:hover { background:var(--hover); }
.ligne.actif { background:var(--accent); color:#fff; }
.enfants { margin-left:14px; }
.cache { display:none; }
a.dl { color:var(--accent); }
</style>
</head>
<body>
<header>
  <h1>&#128218; cdp-viewer</h1>
  <select id="classe" title="Classe"></select>
  <input id="recherche" class="grow" placeholder="&#128269; Rechercher un fichier&hellip;">
  <button id="theme" title="Mode sombre">&#127769;</button>
</header>
<main>
  <nav id="arbre"></nav>
  <section id="apercu"><div class="vide">Sélectionnez un fichier à gauche.</div></section>
</main>
<script>
const IMAGES = ["png","jpg","jpeg","gif","webp","svg","bmp"];
const TEXTES = ["txt","md","markdown","csv","tsv","py","tex","json","log","html","htm","c","cpp","java"];
const elArbre = document.getElementById("arbre");
const elApercu = document.getElementById("apercu");
const elClasse = document.getElementById("classe");
const elRecherche = document.getElementById("recherche");

function octets(n) {
  if (n < 1024) return n + " o";
  if (n < 1048576) return (n/1024).toFixed(1) + " Ko";
  return (n/1048576).toFixed(1) + " Mo";
}
function urlFichier(chemin) {
  return "/file/" + chemin.split("/").map(encodeURIComponent).join("/");
}

function rendreNoeud(noeud) {
  if (noeud.type === "fichier") {
    const d = document.createElement("div");
    d.className = "fichier";
    const l = document.createElement("div");
    l.className = "ligne";
    l.textContent = "📄 " + noeud.nom;
    l.dataset.nom = noeud.nom.toLowerCase();
    l.onclick = () => { selectionner(l); apercu(noeud); };
    d.appendChild(l);
    return d;
  }
  const d = document.createElement("div");
  d.className = "dossier ouvert";
  const l = document.createElement("div");
  l.className = "ligne";
  l.textContent = "📁 " + noeud.nom;
  l.dataset.nom = noeud.nom.toLowerCase();
  const enfants = document.createElement("div");
  enfants.className = "enfants";
  l.onclick = () => { d.classList.toggle("ouvert"); enfants.classList.toggle("cache"); };
  (noeud.enfants || []).forEach(e => enfants.appendChild(rendreNoeud(e)));
  d.appendChild(l);
  d.appendChild(enfants);
  return d;
}

function selectionner(ligne) {
  document.querySelectorAll(".ligne.actif").forEach(e => e.classList.remove("actif"));
  ligne.classList.add("actif");
}

function apercu(noeud) {
  const url = urlFichier(noeud.chemin);
  const ext = (noeud.ext || "").toLowerCase();
  elApercu.innerHTML = "";
  const barre = document.createElement("div");
  barre.className = "barre";
  barre.innerHTML = "<strong>" + noeud.nom + "</strong><span style='color:var(--muted)'>"
    + (ext ? ext.toUpperCase() + " &middot; " : "") + octets(noeud.taille) + "</span>";
  const dl = document.createElement("a");
  dl.className = "dl"; dl.href = url; dl.download = noeud.nom; dl.textContent = "⬇ Télécharger";
  barre.appendChild(dl);
  elApercu.appendChild(barre);

  if (ext === "pdf") {
    const f = document.createElement("iframe"); f.src = url; elApercu.appendChild(f);
  } else if (IMAGES.includes(ext)) {
    const i = document.createElement("img"); i.src = url; i.alt = noeud.nom; elApercu.appendChild(i);
  } else if (TEXTES.includes(ext)) {
    fetch(url).then(r => r.text()).then(t => {
      const pre = document.createElement("pre"); pre.textContent = t; elApercu.appendChild(pre);
    });
  } else {
    const p = document.createElement("div"); p.className = "vide";
    p.innerHTML = "Aperçu indisponible pour ce type.<br>Utilisez « Télécharger ».";
    elApercu.appendChild(p);
  }
}

function filtrer() {
  const q = elRecherche.value.trim().toLowerCase();
  document.querySelectorAll("#arbre .fichier").forEach(f => {
    const nom = f.querySelector(".ligne").dataset.nom;
    f.classList.toggle("cache", q !== "" && !nom.includes(q));
  });
  // Masque les dossiers dont aucun fichier n'est visible.
  document.querySelectorAll("#arbre .dossier").forEach(d => {
    const visible = d.querySelector(".fichier:not(.cache)");
    d.classList.toggle("cache", q !== "" && !visible);
  });
}

async function chargerClasse(classe) {
  elArbre.innerHTML = "Chargement&hellip;";
  const r = await fetch("/api/tree?classe=" + encodeURIComponent(classe));
  if (!r.ok) { elArbre.textContent = "Erreur de chargement."; return; }
  const arbre = await r.json();
  elArbre.innerHTML = "";
  (arbre.enfants || []).forEach(e => elArbre.appendChild(rendreNoeud(e)));
}

async function init() {
  const r = await fetch("/api/classes");
  const classes = await r.json();
  if (!classes.length) {
    elArbre.innerHTML = "";
    elApercu.innerHTML = "<div class='vide'>Aucun cours trouvé.<br>Lancez d'abord <code>cdp_scraper.py</code>.</div>";
    return;
  }
  classes.forEach(c => {
    const o = document.createElement("option"); o.value = c; o.textContent = c; elClasse.appendChild(o);
  });
  elClasse.onchange = () => chargerClasse(elClasse.value);
  chargerClasse(classes[0]);
}

elRecherche.oninput = filtrer;
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
