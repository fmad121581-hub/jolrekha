# Pitch deck outline (8 slides)

Mapped to the judging weights: Impact 30% · Use of Meta AI tooling 25% · Technical depth 20% · Demo 25%.

1. **Title.** "Jolrekha · জলরেখা: flood alerts for Dhaka's most vulnerable, in their own language." One full-bleed photo of a flooded lane.
2. **Problem (Impact).** Informal settlements flood first and hear last. District-wide warnings in formal language. A map of the 55 "high informal risk" wards, overlaid on low ground.
3. **What residents get (Impact).** Telegram screenshot: a Bangla alert, the same alert in English, a voice question and its answer. "No typing needed: share a location, ask by voice."
4. **How it works (Technical).** Diagram: Open-Meteo rain, plus the classifier and DEM/MNDWI layer, plus photo reports, feed the score, which feeds the alerts. Formula on the slide.
5. **Meta's models (Tooling).** Muse Spark as the voice (alerts, tool-calling chatbot, Bangla audio) and the eyes (photo depth). SAM 3.1 segments water and reference objects. Every path has a fallback.
6. **Evidence (Technical).** Remal replay: first red 11 h before the heaviest hour, median 6.5 h. Classifier: 85.3% CV, ρ = 0.65 vs EO4SD. Propensity: ρ = 0.45 vs Sentinel-1 (2023 flood); the gap inside the dense city is why we need photos.
7. **Demo (Demo).** A still from the video and a QR code to the bot. "Try it: share your location."
8. **Next.** Ward councillors and NGOs, SMS/IVR for feature phones, other cities. Ask: pilot partners in Dhaka.
