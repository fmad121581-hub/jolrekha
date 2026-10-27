# Jolrekha (জলরেখা) — ward-level flood and waterlogging alerts for Dhaka

Before the rain arrives and while water is rising, people in Dhaka's most vulnerable wards are alerted first — in plain Bangla.

**Theme:** Build for Your World · **Track:** Indie

Alerts and chatbot replies are in **Bangla**, because many residents of Dhaka's informal settlements cannot read English. The map and the chatbot have a **বাংলা / English** switch so anyone can see what the Bangla alerts say.

## Quick start

```bash
pip install -r requirements.txt
python scripts/import_classifier.py         # classifier GeoPackage → data/wards.geojson + data/informality.csv
python scripts/make_propensity.py           # DEM + MNDWI → data/propensity.csv (waterlogging propensity)
python -m jolrekha.pipeline --mode replay   # Cyclone Remal, 27 May 2024
python -m jolrekha.pipeline --mode forecast # now through the next 24 hours
python -m pytest -q tests

# Chatbot
python -m jolrekha.chatbot                                                  # live forecast, Bangla
python -m jolrekha.chatbot --run replay_2024-05-27 --now "2024-05-26 18:00" # Remal demo
python -m jolrekha.chatbot --lang en --ask "Will Jatrabari flood?"          # English, for judges

# Web demo: map + chatbot + photo reports on one page → http://localhost:8000 (?lang=en)
python -m jolrekha.server --run replay_2024-05-27 --now "2024-05-26 12:00"

# Telegram bot (needs TELEGRAM_BOT_TOKEN in .env)
python -m jolrekha.bot                                                       # live, refreshed hourly
python -m jolrekha.bot --demo replay_2024-05-27 --start "2024-05-26 15:00" --speed 15   # replay, 1 h per 15 s
```

Outputs go to `outputs/<run>/`:
- `map.html`: live map with a time slider and a বাংলা/English switch (`?lang=en` opens it in English)
- `alerts.json`: Bangla and English alert per at-risk ward at the worst moment
- `scores.csv`: R, V, W and score for every hour × ward
- `rain.csv`, `run.json`: saved inputs, so a new field report re-scores the run in seconds

## Keys

These go in `.env` (git-ignored; see `.env.example`). Everything runs without them, on templates and rules.

| Key | What for | Where from |
|---|---|---|
| `MODEL_API_KEY` | The model: alerts, chatbot, photo depth | `ollama` for the local Llama setup below; for Muse Spark, [dev.meta.ai](https://dev.meta.ai) (credits require a credit card) |
| `GROQ_API_KEY` | Voice-note transcription (Whisper large-v3, Bangla) | [console.groq.com/keys](https://console.groq.com/keys), free, no card |
| `TELEGRAM_BOT_TOKEN` | Running the Telegram bot | Telegram → @BotFather → `/newbot` |

### Current setup: Meta Llama on the laptop (no account, no card)

Meta Model API credits require a credit card, and NVIDIA's Muse Glimmer endpoint requires phone verification that excludes Bangladesh. So the project currently runs **Llama 3.1 8B locally in [Ollama](https://ollama.com)** (`ollama pull llama3.1:8b`). On the RX 7600S it runs 100% on the GPU and takes about 1–4 s per chatbot turn.

- **What Llama does:** it routes every chatbot question. It decides whether the user is asking about an area, asking where the risk is highest, or asking something off-topic, by calling `get_ward_status` / `get_top_risk_wards`. It also writes English replies.
- **Garbled place names:** if the place name Llama copies into the tool call matches nothing, the lookup falls back to the user's own words. Llama often garbles Bangla place names this way.
- **What stays on templates:** Bangla replies and all alerts come from the vetted templates (`JOLREKHA_LLM_REPLY_LANGS=en`). Llama 3.1 8B's Bangla was tested and is not good enough for safety messages.
- **Photos:** depth comes from the reporter's button choice. `llama3.2-vision:11b` (architecture `mllama`) does not load in Ollama 0.40.

Switching to Muse Spark later takes three `.env` lines (see the comments in `.env`).

## Telegram bot

- **Subscribe:** share a location (no typing) or send `/subscribe মোহাম্মদপুর`.
  - Alerts are pushed only when the ward's level *rises* to orange/red, plus an all-clear after.
- **Ask:** type or send a voice note. Voice is transcribed by Muse Spark, and the chatbot answers.
- **Report:** send a street photo. Muse Spark judges the depth; when unsure, the reporter taps ankle/knee/waist.
  - The report re-scores the ward immediately.
- **Commands:** `/start`, `/subscribe <area>`, `/status`, `/lang` (বাংলা ↔ English), `/stop`.

## Web demo

[jolrekha/server.py](jolrekha/server.py) puts three things on one page (standard library only):
- the map
- the chatbot
- photo reports

The map's time slider sets the chatbot's "now". Clicking a ward picks it for a report. A report re-scores the run and reloads the map. Built for judges and the demo video. See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Engine

```
score = min(1, R × (0.4 + 0.6·V) × (1 + W))
```

| Part | Meaning | Source |
|---|---|---|
| **R** | Rain: total from 6 h before to 12 h after (89 mm = 1, BMD "very heavy"), or the heaviest single hour (30 mm = 1), whichever is larger | Open-Meteo forecast / archive |
| **V** | Ward vulnerability: √(informality probability × waterlogging propensity) | Classifier + DEM/MNDWI (checked against Sentinel-1) |
| **W** | Field reports: ankle 0.33, knee 0.66, waist 1. Decays with a 3 h half-life; half weight until SAM verifies the photo | User photos → SAM 3.1 |

With no reports W = 0 and the score still isn't zero, so alerts go out **before** the rain. Alert levels: red ≥ 0.60, orange ≥ 0.40, yellow ≥ 0.20. All numbers live in [jolrekha/config.py](jolrekha/config.py).

## Muse Spark (Meta Model API)

Set `MODEL_API_KEY` in `.env` (see **Keys**). Without a key everything runs on templates and rule-based answers. The `source` field in `alerts.json` says who wrote the messages. To use another OpenAI-compatible endpoint, change `JOLREKHA_LLM_BASE_URL` and `JOLREKHA_LLM_MODEL`.

- **Alerts** ([alerts.py](jolrekha/alerts.py)): ward facts go to the model as JSON, 20 per request. It writes a Bangla message and an English rendering for each. Any ward with a missing or invalid message falls back to the template.
- **Chatbot** ([chatbot.py](jolrekha/chatbot.py)): the model calls `get_ward_status(place)` and `get_top_risk_wards(limit)` and answers only from the score table.
- **Photo depth** ([vision.py](jolrekha/vision.py)): the image goes to the model as an `image_url` part. It judges depth from reference objects (feet, rickshaw wheels, kerbs). When confidence is below 0.6, the reporter is asked instead.
  - SAM 3.1 segmentation is a stub until its Meta Model API interface is documented.
- **Voice** ([voice.py](jolrekha/voice.py)): Telegram OGG voice notes go to the model as an `input_audio` part for transcription.
  - ⚠ This audio format is unverified; check it against the official docs once credits are live.
- **Place lookup** ([places.py](jolrekha/places.py)): understands Bangla, English and Banglish spellings, typos ("যাত্রাবারি"), old DCC ward numbers, some neighbourhood names (Old Dhaka, Banani, Farmgate…) and shared locations (point-in-ward).

## Validation

- **Classifier:** see the [informal-settlement-classifier repo](https://github.com/fmad121581-hub/informal-settlement-classifier). Decoupled model: 85.3% ± 7.7% 5-fold CV; ρ = 0.652 vs EO4SD-Urban 2017.
- **Propensity vs Sentinel-1** ([scripts/validate_propensity_sar.py](scripts/validate_propensity_sar.py)), 21 Sep 2023 Dhaka flood, SAR scenes from the NISAR repo:
  - Spearman ρ = 0.45 for all units (n = 178), and 0.18 for city wards only (n = 104).
  - C-band SAR misses water between buildings, which is why field photos matter. The NISAR repo's own pixel-level check of this scene was weak (kappa ≈ 0.01), so this is partial evidence, not ground truth.
- **Remal replay lead time** (observed rain as a perfect forecast):
  - The first red alert came at 17:00 on 26 May, 11 h before the heaviest hour (04:00, 27 May).
  - 94 wards turned red, with a median lead of 6.5 h.

## Layout

```
jolrekha/        core: wards, rainfall, reports, score, alerts, llm, places, status, chatbot,
                 vision, voice, notify, service, bot, server, mapviz, pipeline
scripts/         data import, propensity, SAR validation, synthetic sample data
web/             map template, web demo page
data/            inputs (formats in data/README.md), validation outputs
docs/            submission draft, demo video script, pitch deck outline
outputs/         pipeline results (not in git)
tests/           36 tests: engine, places, chatbot, alerts, bot, push, vision, web API, Telegram HTTP
```

## Data notes

- The 203 units are **GADM Level-4** for Dhaka district: 115 city wards plus unions in Savar, Dhamrai, Dohar, Nawabganj and Keraniganj.
- Ward numbers are the **old Dhaka City Corporation (DCC)** numbers, not today's DNCC/DSCC numbers.
- Union names are still in Latin script in the Bangla UI (e.g. "Aganagar, কেরানীগঞ্জ") until verified Bangla spellings are added.

## Progress

- [x] Days 1–2: wards + rain API + scoring engine + replay mode + prototype map
- [x] Real classifier output and ward boundaries (GADM L4, 203 units)
- [x] `data/propensity.csv` from DEM + MNDWI: low 0.35, hollow (lower than surroundings) 0.45, wet 0.20
- [x] Days 3–4: Muse Spark alerts and tool-based chatbot (also run without a key)
- [x] বাংলা / English switch on the map and chatbot
- [x] Telegram bot: subscribe (location or name), push alerts on rising level, text/voice questions, photo reports
- [x] Photo depth via Muse Spark vision, with the reporter's own choice as fallback; reports re-score the run live
- [x] Web demo (map + chatbot + photo report, synced time and language)
- [x] Propensity checked against Sentinel-1 for the Sep 2023 Dhaka flood
- [x] Submission draft, demo script, pitch deck outline (docs/)
- [ ] With the Meta Model API key: check Bangla alert quality, chatbot tool calls, photo depth on real photos, voice format
- [ ] SAM 3.1 water segmentation once its API interface is documented
- [ ] Create the Telegram bot (@BotFather) and run the demo end to end on a phone
- [ ] Bangla union names; old DCC → current DNCC/DSCC ward number table (for the chatbot)
- [ ] Put the repo on GitHub; record the demo video; submit by 4 Nov, 9 PM ET

## Demo events

Heaviest rain days in Dhaka 2019–2025 per the Open-Meteo archive:
`2024-05-27` (Cyclone Remal, ~175 mm), `2021-12-06` (~145 mm), `2022-10-24` (Cyclone Sitrang, ~131 mm).

## বাংলায় সংক্ষেপে

জলরেখা ঢাকার প্রতিটা ওয়ার্ডের জন্য বৃষ্টির পূর্বাভাস, বসতির ঝুঁকি আর মাঠের রিপোর্ট মিলিয়ে একটা স্কোর বের করে। যে ওয়ার্ডের স্কোর বেশি, সেখানকার মানুষ আগে সহজ বাংলায় সতর্কবার্তা পায়। চ্যাটবটে বাংলায় প্রশ্ন করা যায়, যেমন "মোহাম্মদপুরে আজ পানি উঠবে?"।
