"""Consulta métricas bibliométricas y las guarda en metricas.json.

Si una fuente falla, se conservan los valores anteriores de esa fuente.
La clave de Scopus se lee de la variable de entorno SCOPUS_API_KEY.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date

OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricas.json")

OPENALEX_ID = "A5018031815"
SCOPUS_ID = "55667326400"
SCHOLAR_ID = "OKIleUEAAAAJ"
DIALNET_ID = "165226"

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def openalex():
    d = json.loads(get(f"https://api.openalex.org/authors/{OPENALEX_ID}?mailto=victorhs@ugr.es"))
    return {
        "documents": d.get("works_count"),
        "citations": d.get("cited_by_count"),
        "h_index": d.get("summary_stats", {}).get("h_index"),
    }


def scopus():
    key = os.environ.get("SCOPUS_API_KEY")
    if not key:
        raise RuntimeError("falta SCOPUS_API_KEY")
    d = json.loads(get(
        f"https://api.elsevier.com/content/author/author_id/{SCOPUS_ID}?view=METRICS",
        {"X-ELS-APIKey": key, "Accept": "application/json"},
    ))
    a = d["author-retrieval-response"][0]
    core = a.get("coredata", {})
    return {
        "documents": int(core["document-count"]),
        "citations": int(core["cited-by-count"]),
        "h_index": int(a["h-index"]),
    }


def scholar():
    html = get(f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en",
               {"Accept-Language": "en-US,en;q=0.9"})
    # Tabla lateral: [citas total, citas recientes, h total, h reciente, i10 total, i10 reciente]
    vals = re.findall(r'class="gsc_rsb_std">(\d+)</td>', html)
    if len(vals) < 3:
        raise RuntimeError("no se encontró la tabla de métricas (¿bloqueo de Google?)")
    return {"citations": int(vals[0]), "h_index": int(vals[2])}


def dialnet():
    html = get(f"https://dialnet.unirioja.es/servlet/autor?codigo={DIALNET_ID}",
               {"Accept-Language": "es-ES,es;q=0.9"})
    out = {}
    m = re.search(r"<b>(\d+)</b>[^<]*<span>Citas</span>", html, re.I)
    if m:
        out["citations"] = int(m.group(1))
    m = re.search(r"ndice H:[^<]*<b>(\d+)</b>", html, re.I)
    if m:
        out["h_index"] = int(m.group(1))
    # Suma de las secciones del autor salvo "Tesis dirigidas"
    m = re.search(r'<ul id="seccionesDeAutor">([\s\S]*?)</ul>', html, re.I)
    if m:
        secciones = re.sub(r"dirigidas[\s\S]*?</li>", "", m.group(1), flags=re.I)
        docs = sum(int(n) for n in re.findall(r"\((\d+)\)", secciones))
        if docs:
            out["documents"] = docs
    if not out:
        raise RuntimeError("no se encontraron métricas")
    return out


def main():
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    for name, fn in [("openalex", openalex), ("scopus", scopus),
                     ("scholar", scholar), ("dialnet", dialnet)]:
        try:
            values = {k: v for k, v in fn().items() if v}
            data[name] = {**values, "updated": date.today().isoformat()}
            print(f"OK    {name}: {values}")
        except Exception as e:
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                detail = " | " + e.read().decode("utf-8", errors="replace")[:300]
            print(f"ERROR {name}: {e}{detail} (se mantienen los valores anteriores)")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
