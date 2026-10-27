# Demo video script (target 2:30)

Judging gives **Demo 25%**: "a working, impressive demo, whether the product holds up live, and the quality of the demo video". Record at 1920×1080. Narrate in English. Show Bangla on screen and flip to English with the switch so judges can read along.

## Setup before recording
```bash
python -m jolrekha.pipeline --mode replay                       # refresh outputs (uses Muse Spark if the key is set)
python -m jolrekha.server --run replay_2024-05-27 --now "2024-05-26 12:00"
# Telegram demo (second window / phone screen-mirror):
python -m jolrekha.bot --demo replay_2024-05-27 --start "2024-05-26 15:00" --speed 15
```
- Subscribe a test phone to Mohammadpur beforehand (share a location near Beribadh).
- Delete `data/reports.json` before each take so runs are identical.
- Have 2 street-flood photos ready. Use your own, or ones you have rights to.

## Shots

| Time | On screen | Narration |
|---|---|---|
| 0:00–0:15 | Real flooded Dhaka lane (own photo/video), then the title "Jolrekha · জলরেখা" | "When cyclone rain hits Dhaka, the informal settlements flood first, and hear last. Many people there can't read an English warning." |
| 0:15–0:35 | Web demo, map at 26 May 12:00, all green. Press ▶. | "This is Cyclone Remal, May 2024, replayed hour by hour. Jolrekha scores all 203 wards every hour: rain forecast, times how vulnerable the settlement is, times what residents report." |
| 0:35–0:55 | Map turns yellow, then the first red at 17:00 (Mohammadpur Ward 46). Pause. | "At 5 PM, eleven hours before the heaviest rain, the first red alert goes out, to the dense, low wards along the Buriganga. Not the whole city: the people who need it first." |
| 0:55–1:15 | Phone: the Telegram alert arrives in Bangla. Flip the web switch to English to show the same text. | "Muse Spark writes each ward's alert in plain spoken Bangla, using only the facts we give it. Here's the English, so you can read what residents get." |
| 1:15–1:40 | Chat panel: type "মোহাম্মদপুরে আজ পানি উঠবে?" (or send a voice note in Telegram). Answer appears. | "People ask in their own words, by text or voice. Muse Spark calls our tools on the live score table, so it can't make up a risk level." |
| 1:40–2:05 | Click a ward, upload a street photo. Depth detected (Muse Spark; SAM 3.1 overlay if available). Map refreshes, ward turns red. | "Satellites can't see water between buildings. Residents can. A photo gets checked for water depth, and the ward's risk updates on the spot." |
| 2:05–2:20 | Split screen: classifier map + Sentinel-1 validation numbers. | "Under the hood: my informal-settlement classifier, 85% cross-validated, checked against an independent slum inventory, and a waterlogging layer tested against a real 2023 flood." |
| 2:20–2:30 | Title + repo URL | "Jolrekha. Warnings in the language of the people who need them first." |

## If something fails live
Every model call has a fallback (templates, rules, depth buttons), so the demo still runs. Say so on camera if needed. It shows the system holds up.
