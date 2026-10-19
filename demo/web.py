"""Minimal demo UI (stdlib only): paste logs, compare base vs tuned side by side.

    uv run python demo/web.py        # then open http://127.0.0.1:7860
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from triage import triage  # demo/ is on sys.path when run as `python demo/web.py`

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Incident triage demo</title>
<style>
 body{font:15px system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#111}
 textarea{width:100%;height:220px;font:13px ui-monospace,monospace}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
 pre{background:#f4f4f5;padding:12px;border-radius:8px;white-space:pre-wrap;min-height:120px}
 button{padding:8px 18px;font-size:15px;margin:8px 0}
</style></head><body>
<h2>Incident triage: base 0.8B vs tuned 0.8B</h2>
<textarea id="logs" placeholder="Paste server logs here"></textarea><br>
<button onclick="go()">Triage</button>
<div class="cols"><div><h3>Base</h3><pre id="base"></pre></div>
<div><h3>Tuned</h3><pre id="tuned"></pre></div></div>
<script>
async function go(){
  for (const t of ["base","tuned"]) document.getElementById(t).textContent="...";
  const r = await fetch("/triage",{method:"POST",body:document.getElementById("logs").value});
  const d = await r.json();
  for (const t of ["base","tuned"]) document.getElementById(t).textContent = d[t];
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send(200, "text/html", PAGE.encode())

    def do_POST(self):
        logs = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()

        def run(target):
            try:
                report, raw, latency = triage(logs, target)
                body = json.dumps(report, indent=2) if report else raw
                return f"{body}\n\n({latency:.2f}s)"
            except Exception as exc:
                return f"error: {exc}"

        with ThreadPoolExecutor(2) as pool:
            base, tuned = pool.map(run, ["base", "tuned"])
        self._send(200, "application/json", json.dumps({"base": base, "tuned": tuned}).encode())

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 7860), Handler)
    print("Demo on http://127.0.0.1:7860  (Ctrl-C to stop)")
    server.serve_forever()
