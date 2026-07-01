"""Show ALL saved data from the backend database (PostgreSQL).

Run:  python show_saved.py
"""
import json
import os
import sys

import store

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(__file__)
LANGS = {"en": "English", "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "gu": "Gujarati"}

try:
    with open(os.path.join(HERE, "catalog.json"), encoding="utf-8") as f:
        NAMES = {c["id"]: c["name"] for c in json.load(f)["categories"]}
except Exception:
    NAMES = {}


def size_of(meas):
    w, h = meas.get("width"), meas.get("height")
    if w and h:
        s = f"{w}×{h} in"
        if meas.get("panels"):
            s += f", {meas['panels']} pnl"
        return s
    return "-"


def status_of(work, sel):
    """Human-readable stage status for a placement."""
    work = work or {}
    c = work.get("complaint")
    if c:
        stage = {"measure": "Measurer", "prep": "Tailor", "install": "Installer"}.get(c.get("stage"), c.get("stage"))
        return f"COMPLAINT -> {stage}: {c.get('note', '')}"
    if work.get("status") == "installed":
        return "INSTALLED"
    wallpaper = sel and sel.get("category_id") == "wallpaper"
    if work.get("ready") or wallpaper:
        return "ready to install"
    if sel:
        return "measured (prep pending)"
    return "not measured"


def main():
    rows = store.list_projects()
    users = {u["id"]: u["name"] for u in store.list_users()}

    def who(assign, stage):
        return users.get((assign or {}).get(stage), "—")

    print(f"\n{'='*64}\n  ALL SAVED DATA  —  {len(rows)} project(s) in PostgreSQL ({store.PG['dbname']})\n{'='*64}")
    for meta in rows:
        pr = store.get_project(meta["id"])
        d = pr["data"]
        lang = LANGS.get(d.get("lang"), d.get("lang") or "-")
        rooms = d.get("rooms", [])
        print(f"\n■ {pr['name']}   ·  language: {lang}")
        if not rooms:
            print("    (no rooms)")
        for rm in rooms:
            print(f"    {rm.get('icon','')} {rm.get('name')}")
            for p in rm.get("placements", []):
                sel = p.get("selection")
                assign = p.get("assign", {})
                status = status_of(p.get("work"), sel)
                if not sel:
                    print(f"        • {p.get('label')}  —  (not configured)   [{status}]")
                    continue
                prod = NAMES.get(sel.get("category_id"), sel.get("category_id"))
                size = size_of(sel.get("measurements", {}))
                print(f"        • {p.get('label')}  —  {prod}   [{size}]   ·  {status}")
                print(f"            team:  measure={who(assign, 'measure')} · prep={who(assign, 'prep')} · install={who(assign, 'install')}")
                choices = sel.get("choices", {})
                if choices:
                    parts = []
                    for k, v in choices.items():
                        if isinstance(v, list):
                            v = ", ".join(v) if v else "—"
                        parts.append(f"{k}={v}")
                    print(f"            {' · '.join(parts)}")
    print(f"\n{'='*64}\n")


if __name__ == "__main__":
    main()
