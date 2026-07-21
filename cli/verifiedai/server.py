"""verifiedai serve — self-hosted HTTP API (stdlib only, zero dependencies).

Designed for on-prem deployment inside a lab's infrastructure: proof corpora
never leave the machine. Endpoints:

    GET  /v1/health
    POST /v1/audit   {"project_root": "...", "files": ["A.lean"] | "all": true,
                      "ignore": ["sorry"]?}
    POST /v1/repair  {"project_root": "...", "use_llm": false}

Every response is JSON. Audits of different projects run concurrently
(per-auditor unique probe files); requests are handled in threads.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .lean import LeanProject


def _audit(payload: dict) -> dict:
    from .audit import Auditor, report_dict
    from .__main__ import _discover

    project = LeanProject(payload["project_root"])
    files = _discover(project.root) if payload.get("all") else payload.get("files", [])
    ignore = set(payload.get("ignore", []))
    t0 = time.monotonic()
    reports, skipped = [], []
    for f in files:
        try:
            thms = Auditor(project, f).run()
        except RuntimeError as e:
            skipped.append({"file": f, "reason": str(e).splitlines()[0]})
            continue
        rep = report_dict(f, thms)
        if ignore:
            for t in rep["theorems"]:
                t["findings"] = [x for x in t["findings"] if x["kind"] not in ignore]
            rep["flagged"] = sum(1 for t in rep["theorems"] if t["findings"])
        reports.append(rep)
    n_thms = sum(len(r["theorems"]) for r in reports)
    return {
        "reports": reports,
        "skipped": skipped,
        "stats": {
            "files": len(reports),
            "theorems": n_thms,
            "flagged": sum(r["flagged"] for r in reports),
            "seconds": round(time.monotonic() - t0, 2),
        },
    }


def _repair(payload: dict) -> dict:
    from .repair import Repairer

    project = LeanProject(payload["project_root"])
    results = Repairer(project, use_llm=payload.get("use_llm", False)).run()
    return {
        "ok": all(r.fixed for r in results),
        "repairs": [
            {
                "file": r.file,
                "declaration": r.decl_head,
                "fixed": r.fixed,
                "method": r.method,
                "error": r.error,
            }
            for r in results
        ],
    }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/health":
            self._send(200, {"ok": True, "version": __version__})
        else:
            self._send(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid JSON body"})
            return
        try:
            if self.path == "/v1/audit":
                self._send(200, _audit(payload))
            elif self.path == "/v1/repair":
                self._send(200, _repair(payload))
            else:
                self._send(404, {"error": "unknown endpoint"})
        except (KeyError, FileNotFoundError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # surface, don't crash the server
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):  # quiet default access log
        print(f"[verifiedai] {self.address_string()} {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8419) -> None:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"verifiedai server v{__version__} listening on http://{host}:{port}")
    print("endpoints: GET /v1/health · POST /v1/audit · POST /v1/repair")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
