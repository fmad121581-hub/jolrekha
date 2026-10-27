"""Field photos → water depth.

Muse Spark (multimodal, image_url content parts per the Meta Model API docs)
looks at a street photo and judges whether there is standing water and how deep
it is, using reference objects (feet, legs, rickshaw wheels, car tyres, kerbs).

SAM 3.1 is planned as a second opinion: segment "water" and the reference objects
and measure how much of each is submerged. Its Meta Model API interface is not
public yet, so segment_water() is a stub until the hackathon docs are available.

Without a key analyze_photo() returns None and the bot asks the user to pick the
depth with buttons instead.
"""
import base64

from . import config
from .llm import get_llm

MIN_CONFIDENCE = 0.6  # below this the bot asks the user to confirm the depth

PROMPT = """You are checking a photo sent to a flood-alert service in Dhaka, Bangladesh.
Decide whether the photo shows standing flood or rain water on a street, lane or inside a home,
and estimate its depth from reference objects (feet, legs, rickshaw or bicycle wheels,
car tyres, kerbs, doorsteps).

Depth classes:
- "none": no standing water (or the photo is not a street/home scene)
- "ankle": up to ankle height (~10–15 cm)
- "knee": around knee height (~40–50 cm)
- "waist": waist height or deeper (~80 cm+)

Be conservative: if you cannot see a reference object, lower your confidence.
Reply with JSON only:
{"water_visible": true|false, "depth": "none|ankle|knee|waist", "confidence": 0.0-1.0,
 "evidence": "one short English sentence on what you used to judge"}"""


def _image_type(image: bytes) -> str:
    # imghdr is gone in Python 3.13; Telegram photos are JPEG, documents may be PNG/WebP
    if image.startswith(b"\x89PNG"):
        return "png"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "webp"
    return "jpeg"


def _data_url(image: bytes) -> str:
    return f"data:image/{_image_type(image)};base64,{base64.b64encode(image).decode()}"


def analyze_photo(image: bytes) -> dict | None:
    """{"water_visible", "depth", "confidence", "evidence", "source"} or None if no model / failure."""
    llm = get_llm()
    if llm is None:
        return None
    model = getattr(llm, "vision_model", None)  # e.g. a local llama3.2-vision when the text model can't see
    try:
        data = llm.json([{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": _data_url(image)}},
        ]}], **({"model": model} if model else {}))
    except Exception as e:
        print(f"⚠ vision model failed: {e}")
        return None

    depth = data.get("depth")
    if depth not in config.DEPTH_LEVELS:
        return None
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    if not data.get("water_visible"):
        depth = "none"
    return {"water_visible": depth != "none", "depth": depth, "confidence": conf,
            "evidence": str(data.get("evidence", ""))[:200],
            "source": model or getattr(llm, "model", "llm")}


def segment_water(image: bytes) -> dict | None:
    """SAM 3.1 water segmentation — TODO once the Meta Model API SAM 3.1 interface is documented."""
    return None
