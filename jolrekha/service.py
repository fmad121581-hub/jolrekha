"""Shared state for the Telegram bot and the web demo.

Holds which run is live (forecast or a replay), what "now" is, and how a field
report flows in: photo → Muse Spark depth estimate (or the user's own choice)
→ reports.json → re-score the run → fresh status and map.
"""
import threading
from datetime import datetime

import pandas as pd

from . import config, pipeline
from .reports import add_report
from .status import Status
from .vision import MIN_CONFIDENCE, analyze_photo

PHOTOS_DIR = config.DATA_DIR / "photos"


class Service:
    def __init__(self, run: str = "forecast", now: str | None = None, rescore=pipeline.rescore):
        self.run = run
        self._now = now
        self._rescore = rescore
        self.lock = threading.RLock()
        self.status = Status(run, now)

    # ---------- clock ----------
    def reload(self):
        with self.lock:
            self.status = Status(self.run, self._now)

    def set_now(self, now: str | None):
        self._now = now
        self.reload()

    def advance(self, hours: int = 1) -> bool:
        """Move the replay clock forward; False once the last frame is reached."""
        nxt = self.status.now + pd.Timedelta(hours=hours)
        if nxt > self.status.times[-1]:
            return False
        self.set_now(nxt.isoformat())
        return True

    def refresh_live(self):
        """Live mode: fetch a new forecast and re-score (hourly)."""
        pipeline.run("forecast", use_llm=False)
        self.reload()

    # ---------- reports ----------
    def save_photo(self, image: bytes, ward_id: str) -> str:
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTOS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{ward_id.replace('.', '-')}.jpg"
        path.write_bytes(image)
        return str(path)

    def photo_report(self, image: bytes, ward_id: str, source: str) -> dict:
        """Analyse a photo. Returns {"status": "recorded" | "no_water" | "needs_depth", ...}."""
        self.save_photo(image, ward_id)
        a = analyze_photo(image)
        if a is None or a["confidence"] < MIN_CONFIDENCE:
            return {"status": "needs_depth", "analysis": a}
        if a["depth"] == "none":
            return {"status": "no_water", "analysis": a}
        self.record(ward_id, a["depth"], verified=True, source=f"{source}+{a['source']}")
        return {"status": "recorded", "depth": a["depth"], "verified": True, "analysis": a}

    def record(self, ward_id: str, depth: str, verified: bool, source: str) -> dict:
        """Store a report at the current (possibly replayed) time, then re-score so it shows up."""
        with self.lock:
            rec = add_report(ward_id, depth, time=self.status.now.to_pydatetime(),
                             verified=verified, source=source)
            self._rescore(self.run)
            self.reload()
        return rec
