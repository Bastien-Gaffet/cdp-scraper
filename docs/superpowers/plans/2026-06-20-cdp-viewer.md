# cdp_viewer.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-dependency local web viewer (`cdp_viewer.py`) to browse the course tree downloaded by `cdp_scraper.py`.

**Architecture:** A single Python script using only the standard library. An `http.server` handler bound to `127.0.0.1` exposes three JSON/file routes plus an embedded single-page HTML app (vanilla JS + CSS variables). Pure functions (`resoudre_dans_racine`, `lister_classes`, `construire_arbre`) hold the logic and are unit-tested; the HTTP layer is integration-tested against a server on an ephemeral port.

**Tech Stack:** Python ≥ 3.8 stdlib (`http.server`, `socketserver`, `webbrowser`, `urllib`, `mimetypes`, `pathlib`, `argparse`, `json`, `html`), `unittest` for tests. No new dependency in `requirements.txt`.

---

## File Structure

- Create: `cdp_viewer.py` — the viewer (helpers + HTTP handler + embedded page + CLI).
- Create: `test_cdp_viewer.py` — `unittest` tests (pure helpers + server integration).
- Modify: `README.md` — add a "Parcourir ses cours (visualiseur local)" section.

Conventions to follow from `cdp_scraper.py`: French names/comments, `pathlib.Path`, module-level constants in UPPER_CASE, a `main()` guarded by `if __name__ == "__main__"`.

Data contract used everywhere:
- A **tree node** is a dict. Folder: `{"nom": str, "type": "dossier", "chemin": str, "enfants": [node, ...]}`. File: `{"nom": str, "type": "fichier", "chemin": str, "taille": int, "ext": str}`.
- `chemin` is always **relative to the root folder, POSIX-style, and includes the class folder** (e.g. `"PCSI/Maths/cours.pdf"`). This is the exact string passed to `/file/<chemin>`.

---

### Task 1: Path-traversal-safe resolver

**Files:**
- Create: `cdp_viewer.py`
- Test: `test_cdp_viewer.py`

- [ ] **Step 1: Write the failing test**

Create `test_cdp_viewer.py`:

```python
import unittest
from pathlib import Path
import tempfile

import cdp_viewer


class TestResoudreDansRacine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI").mkdir()
        (self.racine / "PCSI" / "cours.pdf").write_bytes(b"%PDF-1.4 test")

    def tearDown(self):
        self.tmp.cleanup()

    def test_chemin_interne_resolu(self):
        cible = cdp_viewer.resoudre_dans_racine(self.racine, "PCSI/cours.pdf")
        self.assertEqual(cible, (self.racine / "PCSI" / "cours.pdf").resolve())

    def test_racine_elle_meme_autorisee(self):
        self.assertEqual(cdp_viewer.resoudre_dans_racine(self.racine, ""), self.racine.resolve())

    def test_traversal_rejete(self):
        self.assertIsNone(cdp_viewer.resoudre_dans_racine(self.racine, "../secret.txt"))
        self.assertIsNone(cdp_viewer.resoudre_dans_racine(self.racine, "PCSI/../../secret.txt"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cdp_viewer.TestResoudreDansRacine -v`
Expected: FAIL — `AttributeError: module 'cdp_viewer' has no attribute 'resoudre_dans_racine'`

- [ ] **Step 3: Write minimal implementation**

Create `cdp_viewer.py`:

```python
#!/usr/bin/env python3
"""cdp_viewer — visualiseur web local des cours téléchargés par cdp_scraper.

Sert l'arborescence cours_cdp/<classe>/... dans le navigateur. Bibliothèque
standard uniquement, serveur lié à 127.0.0.1.
"""
from pathlib import Path


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cdp_viewer.TestResoudreDansRacine -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cdp_viewer.py test_cdp_viewer.py
git commit -m "feat(viewer): resolveur de chemin anti path-traversal"
```

---

### Task 2: List classes

**Files:**
- Modify: `cdp_viewer.py`
- Test: `test_cdp_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_viewer.py` (before the `if __name__` block):

```python
class TestListerClasses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI").mkdir()
        (self.racine / "MPSI").mkdir()
        (self.racine / "note.txt").write_text("ignore-moi")

    def tearDown(self):
        self.tmp.cleanup()

    def test_liste_les_sous_dossiers_tries(self):
        self.assertEqual(cdp_viewer.lister_classes(self.racine), ["MPSI", "PCSI"])

    def test_racine_absente_renvoie_vide(self):
        self.assertEqual(cdp_viewer.lister_classes(self.racine / "nexistepas"), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cdp_viewer.TestListerClasses -v`
Expected: FAIL — `AttributeError: module 'cdp_viewer' has no attribute 'lister_classes'`

- [ ] **Step 3: Write minimal implementation**

Add to `cdp_viewer.py`:

```python
def lister_classes(racine: Path) -> list[str]:
    """Noms des sous-dossiers de `racine` (= les classes scrapées), triés."""
    if not racine.is_dir():
        return []
    return sorted(p.name for p in racine.iterdir() if p.is_dir())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cdp_viewer.TestListerClasses -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add cdp_viewer.py test_cdp_viewer.py
git commit -m "feat(viewer): listing des classes (sous-dossiers de la racine)"
```

---

### Task 3: Build the folder tree

**Files:**
- Modify: `cdp_viewer.py`
- Test: `test_cdp_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_viewer.py`:

```python
class TestConstruireArbre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        maths = self.racine / "PCSI" / "Maths"
        maths.mkdir(parents=True)
        (maths / "cours.pdf").write_bytes(b"%PDF data")
        (self.racine / "PCSI" / "info.txt").write_text("hello")

    def tearDown(self):
        self.tmp.cleanup()

    def test_structure_de_l_arbre(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        self.assertEqual(arbre["type"], "dossier")
        self.assertEqual(arbre["chemin"], "PCSI")
        noms = sorted(e["nom"] for e in arbre["enfants"])
        self.assertEqual(noms, ["Maths", "info.txt"])

    def test_dossiers_avant_fichiers(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        self.assertEqual(arbre["enfants"][0]["type"], "dossier")

    def test_noeud_fichier(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        dossier = next(e for e in arbre["enfants"] if e["nom"] == "Maths")
        fichier = dossier["enfants"][0]
        self.assertEqual(fichier["type"], "fichier")
        self.assertEqual(fichier["nom"], "cours.pdf")
        self.assertEqual(fichier["chemin"], "PCSI/Maths/cours.pdf")
        self.assertEqual(fichier["ext"], "pdf")
        self.assertEqual(fichier["taille"], len(b"%PDF data"))

    def test_classe_inconnue_renvoie_none(self):
        self.assertIsNone(cdp_viewer.construire_arbre(self.racine, "TERM"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cdp_viewer.TestConstruireArbre -v`
Expected: FAIL — `AttributeError: module 'cdp_viewer' has no attribute 'construire_arbre'`

- [ ] **Step 3: Write minimal implementation**

Add to `cdp_viewer.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cdp_viewer.TestConstruireArbre -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cdp_viewer.py test_cdp_viewer.py
git commit -m "feat(viewer): construction de l'arbre des cours (dossiers avant fichiers)"
```

---

### Task 4: HTTP handler and routes

**Files:**
- Modify: `cdp_viewer.py`
- Test: `test_cdp_viewer.py`

This task adds the request handler with `/api/classes`, `/api/tree`, `/file/<chemin>` and a server factory. The `/` route is added in Task 5; here it may return 200 with an empty body placeholder that Task 5 replaces.

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_viewer.py`. Add these imports at the very top of the file (next to the existing ones):

```python
import json
import threading
import urllib.request
import urllib.error
```

Then append the test class:

```python
class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.racine = Path(cls.tmp.name)
        maths = cls.racine / "PCSI" / "Maths"
        maths.mkdir(parents=True)
        (maths / "cours.pdf").write_bytes(b"%PDF-1.4 contenu")
        (cls.racine / "secret.txt").write_text("hors classe")

        cls.serveur = cdp_viewer.creer_serveur(cls.racine, port=0)
        cls.port = cls.serveur.server_address[1]
        cls.thread = threading.Thread(target=cls.serveur.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()
        cls.tmp.cleanup()

    def _get(self, chemin):
        url = f"http://127.0.0.1:{self.port}{chemin}"
        return urllib.request.urlopen(url, timeout=5)

    def test_api_classes(self):
        with self._get("/api/classes") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(json.load(r), ["PCSI"])

    def test_api_tree(self):
        with self._get("/api/tree?classe=PCSI") as r:
            arbre = json.load(r)
        self.assertEqual(arbre["chemin"], "PCSI")
        self.assertEqual(arbre["enfants"][0]["nom"], "Maths")

    def test_api_tree_classe_inconnue_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/tree?classe=TERM")
        self.assertEqual(ctx.exception.code, 404)

    def test_file_sert_le_contenu(self):
        with self._get("/file/PCSI/Maths/cours.pdf") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read(), b"%PDF-1.4 contenu")
            self.assertEqual(r.headers["Content-Type"], "application/pdf")

    def test_file_inexistant_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/PCSI/Maths/absent.pdf")
        self.assertEqual(ctx.exception.code, 404)

    def test_file_traversal_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cdp_viewer.TestServeur -v`
Expected: FAIL — `AttributeError: module 'cdp_viewer' has no attribute 'creer_serveur'`

- [ ] **Step 3: Write minimal implementation**

Add the imports at the top of `cdp_viewer.py` (below the existing `from pathlib import Path`):

```python
import json
import mimetypes
import socketserver
import urllib.parse
from http.server import BaseHTTPRequestHandler

PAGE_HTML = "<!doctype html><title>cdp-viewer</title>"  # remplacé en Task 5
```

Add the handler and server factory at the bottom of `cdp_viewer.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cdp_viewer.TestServeur -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest test_cdp_viewer -v`
Expected: PASS (all tests from Tasks 1–4)

- [ ] **Step 6: Commit**

```bash
git add cdp_viewer.py test_cdp_viewer.py
git commit -m "feat(viewer): serveur HTTP local et routes api/classes, api/tree, file"
```

---

### Task 5: Embedded single-page frontend

**Files:**
- Modify: `cdp_viewer.py` (replace the `PAGE_HTML` constant)
- Test: `test_cdp_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_viewer.py` inside `TestServeur` (it reuses the running server):

```python
    def test_page_racine_contient_le_squelette(self):
        with self._get("/") as r:
            html = r.read().decode("utf-8")
        self.assertIn("cdp-viewer", html)
        self.assertIn("id=\"arbre\"", html)
        self.assertIn("id=\"apercu\"", html)
        self.assertIn("/api/classes", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cdp_viewer.TestServeur.test_page_racine_contient_le_squelette -v`
Expected: FAIL — placeholder HTML lacks `id="arbre"`

- [ ] **Step 3: Replace the `PAGE_HTML` constant**

In `cdp_viewer.py`, replace the placeholder line `PAGE_HTML = "..."` with the full page below. Use a raw triple-quoted string so JS `{}` are untouched (no `.format`).

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cdp_viewer -v`
Expected: PASS (all tests, including `test_page_racine_contient_le_squelette`)

- [ ] **Step 5: Commit**

```bash
git add cdp_viewer.py test_cdp_viewer.py
git commit -m "feat(viewer): page unique (arbre, apercu PDF/images/texte, recherche, mode sombre)"
```

---

### Task 6: CLI entry point

**Files:**
- Modify: `cdp_viewer.py`
- Test: manual smoke test (CLI wiring is thin; covered by integration tests above)

- [ ] **Step 1: Add the CLI**

Add imports at the top of `cdp_viewer.py` (with the others):

```python
import argparse
import webbrowser
```

Add at the bottom of `cdp_viewer.py`:

```python
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
```

- [ ] **Step 2: Smoke test the CLI manually**

Run: `python cdp_viewer.py --no-browser --port 8000`
Expected: prints `cdp-viewer en écoute sur http://127.0.0.1:8000`. Open that URL in a browser: the page loads (empty-state message if `cours_cdp/` is absent). Stop with Ctrl+C; expect `Arrêt.`

- [ ] **Step 3: Verify the full suite still passes**

Run: `python -m unittest test_cdp_viewer -v`
Expected: PASS (all tests)

- [ ] **Step 4: Commit**

```bash
git add cdp_viewer.py
git commit -m "feat(viewer): point d'entrée CLI (--dossier, --port, --no-browser)"
```

---

### Task 7: Document the viewer in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a viewer section**

In `README.md`, after the `## ▶️ Utilisation` section (before the `---` that precedes `## 📄 Licence`), insert:

```markdown
## 🖥️ Parcourir ses cours (visualiseur local)

Une fois vos documents téléchargés, `cdp_viewer.py` lance un petit site **local**
pour les parcourir confortablement (arborescence, aperçu PDF/images/texte,
recherche, mode sombre). Aucune dépendance supplémentaire, rien n'est exposé sur
le réseau (le serveur n'écoute que sur `127.0.0.1`).

```bash
python cdp_viewer.py                     # sert ./cours_cdp et ouvre le navigateur
python cdp_viewer.py --dossier ./cours   # autre dossier racine
python cdp_viewer.py --port 8080 --no-browser
```

Le navigateur s'ouvre sur `http://127.0.0.1:8000`. Choisissez la classe en haut,
naviguez dans l'arbre à gauche, l'aperçu s'affiche à droite.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: section visualiseur local dans le README"
```

---

## Self-Review Notes

- **Spec coverage:** zero-dependency stdlib (Tasks 1–6, no `requirements.txt` change); routes `/api/classes`, `/api/tree`, `/file`, `/` (Task 4–5); preview PDF/images/text + download fallback (Task 5); search (Task 5); dark mode + localStorage (Task 5); class selector (Task 5); 127.0.0.1 bind + path-traversal 403 (Tasks 1, 4); 404 for missing file/class (Task 4); empty-root friendly message (Tasks 5 init, 6 CLI); tests incl. traversal (Tasks 1, 4); README integration (Task 7). All covered.
- **Type consistency:** `resoudre_dans_racine`, `lister_classes`, `construire_arbre`, `creer_serveur`, `ServeurCDP.racine`, node keys (`nom/type/chemin/taille/ext/enfants`) used identically across tasks and tests.
- **No placeholders:** every code/test step is complete and runnable.
```
