"""Web demo — map, chatbot and photo reports on one page, for judges and the demo video.

    python -m jolrekha.server                                          # live forecast
    python -m jolrekha.server --run replay_2024-05-27 --now "2024-05-26 18:00"
    → open http://localhost:8000  (add ?lang=en for English)

Standard library only. The map's time slider drives the chatbot's "now", and a
photo report re-scores the run so the map changes on the spot.
"""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config
from .chatbot import Chatbot
from .places import find_wards, ward_at, ward_names
from .service import Service
from .status import fmt_time, public, summarize

DEMO_HTML = config.ROOT / "web" / "demo.html"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEPTHS = {"ankle", "knee", "waist", "none"}


class DemoApp:
    """HTTP-free core so it can be tested directly."""

    def __init__(self, service: Service):
        self.svc = service
        self.chats: dict[str, Chatbot] = {}

    def _chatbot(self, session: str, lang: str) -> Chatbot:
        key = f"{session}:{lang}"
        bot = self.chats.get(key)
        if bot is None or bot.status is not self.svc.status:
            bot = self.chats[key] = Chatbot(self.svc.status, lang)
        return bot

    def state(self) -> dict:
        st = self.svc.status
        return {"run": st.run, "now": st.now.strftime("%Y-%m-%d %H:%M"),
                "now_bn": fmt_time(st.now, "bn"), "now_en": fmt_time(st.now, "en"),
                "frames": [t.strftime("%Y-%m-%d %H:%M") for t in st.times],
                "llm": self._chatbot("_probe", "bn").llm is not None}

    def set_time(self, body: dict) -> dict:
        self.svc.set_now(body["now"])
        return self.state()

    def ask(self, body: dict) -> dict:
        q = str(body.get("q", ""))[:500]
        lang = "en" if body.get("lang") == "en" else "bn"
        bot = self._chatbot(str(body.get("session", "anon"))[:64], lang)
        return {"answer": bot.ask(q), "mode": bot.llm.model if bot.llm else "rules"}

    def resolve_ward(self, body: dict) -> str | None:
        if body.get("ward_id"):
            return str(body["ward_id"])
        if body.get("lat") is not None and body.get("lon") is not None:
            return ward_at(float(body["lat"]), float(body["lon"]))
        ids = find_wards(str(body.get("place", "")))
        return ids[0] if len(ids) == 1 else None

    def report(self, body: dict) -> dict:
        lang = "en" if body.get("lang") == "en" else "bn"
        ward = self.resolve_ward(body)
        if ward is None:
            return {"ok": False, "error": "ward_unknown"}
        name = ward_names(ward)[lang]
        depth = body.get("depth")
        if depth:  # the reporter picked the depth themselves
            if depth not in DEPTHS:
                return {"ok": False, "error": "bad_depth"}
            if depth != "none":
                self.svc.record(ward, depth, verified=False, source="web")
            return {"ok": True, "status": "recorded" if depth != "none" else "no_water",
                    "ward": name, "depth": depth, "verified": False}
        image = base64.b64decode(body.get("image_b64", "").split(",")[-1] or b"")
        if not image or len(image) > MAX_IMAGE_BYTES:
            return {"ok": False, "error": "bad_image"}
        res = self.svc.photo_report(image, ward, source="web")
        return {"ok": True, "ward": name, "ward_id": ward, **{k: v for k, v in res.items() if k != "analysis"},
                "evidence": (res.get("analysis") or {}).get("evidence")}

    def status(self, query: dict) -> dict:
        lang = "en" if query.get("lang") == "en" else "bn"
        res = self.svc.status.place(query.get("place", ""))
        return {"summary": summarize(res, lang), "wards": public(res["wards"])}


def make_handler(app: DemoApp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/":
                return self._send(200, DEMO_HTML.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/map":
                return self._send(200, (config.OUTPUT_DIR / app.svc.run / "map.html").read_bytes(),
                                  "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self._json(app.state())
            if url.path == "/api/status":
                return self._json(app.status(q))
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_IMAGE_BYTES * 2:
                return self._json({"ok": False, "error": "too_large"}, 413)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json({"ok": False, "error": "bad_json"}, 400)
            routes = {"/api/ask": app.ask, "/api/report": app.report, "/api/time": app.set_time}
            fn = routes.get(urlparse(self.path).path)
            if fn is None:
                return self._send(404, b"not found", "text/plain")
            try:
                self._json(fn(body))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Jolrekha web demo")
    ap.add_argument("--run", default="forecast", help="outputs/ run: forecast or replay_YYYY-MM-DD")
    ap.add_argument("--now", help="replay start time, e.g. '2024-05-26 18:00'")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    app = DemoApp(Service(args.run, args.now))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Jolrekha demo · {args.run} · http://{args.host}:{args.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
