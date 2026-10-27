# Jolrekha (জলরেখা) — hackathon submission draft

> Draft for the Cerebral Valley submission form. Numbers marked ✅ are measured in this repo or the
> classifier repo; items marked ⏳ depend on access to Meta Model API (Muse Spark / SAM 3.1). If that
> access becomes possible before 4 Nov, re-test and update the Meta models table.

**Track:** Indie · **Theme:** Build for Your World

## One line
Flood and waterlogging alerts for Dhaka's most vulnerable wards, in plain Bangla, hours before the rain peaks.

## The problem
When monsoon or cyclone rain hits Dhaka, informal settlements flood first: low ground, no drains, homes at street level. Their residents also hear last. Official warnings are district-wide, often in English or formal Bangla, and don't say *which* neighbourhood should move its medicine, papers and children to higher ground *tonight*. Many residents can't read English at all.

## What Jolrekha does
Every hour it scores all 203 wards and unions of Dhaka district:

```
score = R × (0.4 + 0.6·V) × (1 + W)
```

- **R, rain**: Open-Meteo hourly forecast, 6 h back + 12 h ahead, scaled to BMD's "very heavy" threshold.
- **V, vulnerability**: √(informality × waterlogging propensity).
  - Informality comes from my own XGBoost classifier ✅.
  - Propensity comes from SRTM elevation, local depressions and Sentinel-2 MNDWI ✅.
- **W, field reports**: residents' photos of street water, decaying with a 3 h half-life.

The riskiest wards are warned first, before the rain arrives. No report is needed for an alert to go out.

**Meta's models:**

| | Model | What it does | Status |
|---|---|---|---|
| Brain | **Llama 3.1 8B**, running locally in Ollama on a laptop GPU | Routes every chatbot question. It calls `get_ward_status` / `get_top_risk_wards` on the live score table, so it never states a risk level itself, and it writes English replies | ✅ Running. Handles Bangla, Banglish and English questions; 1–4 s per turn on an RX 7600S |
| Voice | **Muse Spark** | Writes a separate alert per ward in plain spoken Bangla, with an English rendering, from structured facts only | Built and tested with fakes. ⏳ Needs Meta Model API credits, which require a credit card I don't have |
| Eyes | **Muse Spark** (vision) / **SAM 3.1** | Judges water depth from reference objects in residents' photos | Built and tested with fakes. ⏳ Same access issue; Llama 3.2 Vision doesn't load in current Ollama |

**A design choice I want to be clear about.** I tested Llama 3.1 8B's Bangla and it isn't good enough for a safety message. It produced garbled advice. So residents' Bangla alerts and answers come from vetted templates, and the model only decides *what* is being asked. One config line (`JOLREKHA_LLM_REPLY_LANGS`) lets a stronger model such as Muse Spark write Bangla directly once it's available.

Voice notes are transcribed by Whisper (via Groq's free tier). Every path falls back gracefully (templates, rules, or asking the reporter to tap a depth), so the alert chain never depends on one model call succeeding.

**Access note for judges.** I'm in Bangladesh, where Meta Model API credits (credit card) and NVIDIA's hosted Muse Glimmer (phone verification, Bangladesh not listed) were not reachable. Running Meta's open-weights Llama on my own laptop was the way to keep a Meta model in the loop. That's also how a low-cost deployment in Dhaka would likely run.

## How people use it
- **Telegram bot.** Residents share a location (no typing needed) or `/subscribe মোহাম্মদপুর`. They get pushed alerts only when their ward's level *rises* to orange/red, plus an all-clear afterwards. Never the same level twice, so the alerts don't become noise. They can ask by text or voice, and send photos.
- **Web demo.** A live map with a time slider, a chatbot and photo reporting on one page. A বাংলা / English switch lets judges read exactly what residents receive.

## Evidence it works
- **Cyclone Remal replay (27 May 2024, ~176 mm in 24 h)** ✅, run on Open-Meteo's archive. It uses observed rain as a perfect forecast, so real-time lead times will be shorter.
  - The first red alert came at 17:00 on 26 May, for Mohammadpur Ward 46 (Beribadh). The heaviest hour was 04:00 on 27 May, so that alert came **11 hours ahead**.
  - 94 wards eventually turned red, with a median lead of **6.5 h** before the heaviest hour.
  - The first wards alerted were the dense, low settlements along the Buriganga: Mohammadpur, Hazaribagh, Lalbagh, Kadamtali, Adabor.
- **Informality classifier** ✅ ([repo](https://github.com/fmad121581-hub/informal-settlement-classifier)):
  - 85.3% ± 7.7% 5-fold CV accuracy (majority baseline 64.1%), and 83.1% with spatial-block CV. This uses a decoupled model built to remove label leakage.
  - Spearman r = 0.652 against the independent EO4SD-Urban 2017 slum inventory.
- **Propensity vs a real flood** ✅: Spearman ρ = 0.45 against Sentinel-1 water change for the 21 Sep 2023 Dhaka flood (n = 178 units, from my [NISAR/SAR repo](https://github.com/fmad121581-hub/nisar-dhaka-flood-mapping)).
  - Inside the dense city it drops to ρ = 0.18. C-band SAR can't see water between buildings.
  - That blind spot is exactly why Jolrekha asks residents for photos.
- **Field reports move the map** ✅: one knee-deep report in Mohammadpur Ward 46 lifted its score from 0.64 to 0.92 within the same hour, then decayed as expected.
- **36 automated tests**, covering the scoring engine, place lookup (Bangla/English/Banglish, typos), the chatbot tool loop, the bot, alert push, the vision parser and the web API.

## Why it matters
The Dhaka metropolitan region has about 12.5 million people, and my classifier puts 55 of its 203 wards at high informal-settlement risk. They have the least time and the fewest resources to prepare. A few hours' notice, in their own language, is the difference between losing medicine, papers and stock, and saving them. The same pipeline works for any city with rain forecasts and a vulnerability map.

## What's next
- Validate with BWDB / DNCC waterlogging records.
- Map old DCC ward numbers to today's DNCC/DSCC numbers.
- Add verified Bangla names for rural unions.
- Use SMS and IVR for people without smartphones.
- Partner with ward councillors and NGOs who already run volunteer networks.

## Disclosure
The informality classifier and SAR work were built before the hackathon. A first prototype of Jolrekha (scoring engine, replay, map) was started on 25 Oct 2026, the day before kickoff. The Meta-model integrations, the bot and the web demo are completed and validated with real models during the hackathon window. (⏳ Before submitting: put the repo under git and describe here exactly what existed at kickoff.)
