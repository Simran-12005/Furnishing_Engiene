"""Standalone HTTP server for the Furnishing Selection Engine.

Pure Python standard library — no pip installs. Serves the single-page frontend
and a small JSON API that exposes the catalog, the rules+formula engine
(/api/resolve), and project persistence.

Run:  python server.py     then open  http://localhost:8300
"""
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import catalog
import engine
import store

PORT = 8300
HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    # ---- helpers -----------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200):
        self._send(code, json.dumps(data).encode("utf-8"), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def log_message(self, *args):  # quieter console
        return

    # ---- routing -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self._json({"status": "ok"})
        if path == "/api/categories":
            return self._json({"categories": catalog.categories_brief()})
        if path == "/api/rooms":
            return self._json({"rooms": catalog.rooms()})
        if path == "/api/users":
            return self._json({"users": store.list_users()})
        m = re.fullmatch(r"/api/categories/([\w-]+)", path)
        if m:
            cat = catalog.get_category(m.group(1))
            return self._json(cat) if cat else self._json({"error": "not found"}, 404)
        if path == "/api/projects":
            return self._json({"projects": store.list_projects()})
        m = re.fullmatch(r"/api/projects/([\w-]+)", path)
        if m:
            proj = store.get_project(m.group(1))
            return self._json(proj) if proj else self._json({"error": "not found"}, 404)
        if path.startswith("/images/") and path.endswith(".svg"):
            fpath = os.path.join(HERE, "images", os.path.basename(path))
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    return self._send(200, f.read(), "image/svg+xml")
            return self._json({"error": "not found"}, 404)
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._read_json()

        if path == "/api/resolve":
            cat = catalog.get_category(body.get("category_id"))
            if not cat:
                return self._json({"error": "unknown category"}, 400)
            return self._json(engine.resolve(cat, body.get("answers", {})))

        if path == "/api/projects":
            name = (body.get("name") or "Untitled project").strip()
            pid = store.save_project(name, body.get("data", {}), body.get("id"))
            return self._json({"id": pid, "name": name})

        if path == "/api/login":
            user = store.login((body.get("name") or "").strip(), (body.get("pin") or "").strip())
            return self._json({"user": user}) if user else self._json({"error": "wrong name or PIN"}, 401)

        if path == "/api/users":
            name = (body.get("name") or "").strip()
            role = (body.get("role") or "").strip()
            if not name or role not in ("supervisor", "measurer", "tailor", "installer"):
                return self._json({"error": "name and valid role required"}, 400)
            uid = store.add_user(name, role, (body.get("pin") or "0000").strip())
            return self._json({"id": uid})

        # PATCH one item: POST /api/projects/<pid>/items/<item_id>  body = dotted updates
        m = re.fullmatch(r"/api/projects/([\w-]+)/items/([\w-]+)", path)
        if m:
            ok = store.patch_item(m.group(1), m.group(2), body or {})
            return self._json({"ok": ok}) if ok else self._json({"error": "not found"}, 404)

        return self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/projects":
            store.delete_all_projects()
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/projects/([\w-]+)", path)
        if m:
            store.delete_project(m.group(1))
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/users/([\w-]+)", path)
        if m:
            store.delete_user(m.group(1))
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    store.init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = _lan_ip()
    print("=" * 60)
    print(" Furnishing Estimator is running.")
    print(f"   On this PC :  http://localhost:{PORT}")
    print(f"   On a PHONE :  http://{ip}:{PORT}    <-- open this on your phone")
    print("   (phone must be on the same Wi-Fi; keep this window open)")
    print(" Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
