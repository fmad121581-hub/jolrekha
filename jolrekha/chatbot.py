"""Jolrekha chatbot — "মোহাম্মদপুরে আজ পানি উঠবে?" (Will water rise in Mohammadpur today?)

    python -m jolrekha.chatbot                                   # live forecast, Bangla
    python -m jolrekha.chatbot --run replay_2024-05-27 --now "2024-05-26 18:00"
    python -m jolrekha.chatbot --lang en --ask "Will Jatrabari flood?"

With Muse Spark the model calls tools and answers from the score table only.
Without a key it answers with rules (status.summarize). Replies are Bangla by
default; --lang en is for demos to international judges.
"""
import argparse
import json
import os
import sys

from .llm import get_llm, reply_langs
from .status import Status, fmt_time, public, summarize, summarize_top

SYSTEM = """You are "Jolrekha" (জলরেখা), a flood and waterlogging alert assistant for Dhaka district.
People ask in Bangla, Banglish or English. {language_rule}

Rules:
- Always call get_ward_status to describe an area. Never state a risk level, time or rainfall
  amount that did not come from a tool result, and never guess.
- For "where is it worst?" questions call get_top_risk_wards.
- If found = 0, say you didn't recognise the area and ask for a nearby thana or ward number.
- Levels: red = high risk of water entering homes, orange = low roads may flood,
  yellow = minor, green = no significant risk.
- For red or orange give one practical tip; for red also mention calling 999 in an emergency.
- When an area has many wards, name only the 1–2 riskiest, not the whole list.
- Ward numbers are the old Dhaka City Corporation numbers; if someone gives a new
  DNCC/DSCC number, ask for the area name.
- Times in tool results are Dhaka local time; "now" is given in each result.
- For questions unrelated to flooding, rain or safety, politely say you only help with those."""

LANGUAGE_RULES = {
    "bn": "Always reply in simple, spoken Bangla (no English words), 3–4 short sentences, "
          "with Bangla digits and Bangla area names (name_bn).",
    "en": "Always reply in plain English, 3–4 short sentences, using English area names (name_en).",
}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_ward_status",
        "description": "Current and next-24-hour flood risk for an area, thana, union or ward.",
        "parameters": {"type": "object", "properties": {
            "place": {"type": "string",
                      "description": "Area name or ward as the user wrote it, e.g. 'মোহাম্মদপুর', 'ward 44'"}},
            "required": ["place"]},
    }},
    {"type": "function", "function": {
        "name": "get_top_risk_wards",
        "description": "The riskiest wards over the next 24 hours.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "How many (1–10)"}}},
    }},
]
MAX_TOOL_ROUNDS = 4


def _assistant_entry(msg) -> dict:
    """Keep only the needed fields — some servers reject extra SDK fields (annotations etc.)."""
    entry = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        entry["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
            for c in msg.tool_calls
        ]
    return entry


class Chatbot:
    def __init__(self, status: Status, lang: str = "bn"):
        self.status = status
        self.lang = lang
        self.llm = get_llm()
        self.history = [{"role": "system", "content": SYSTEM.format(language_rule=LANGUAGE_RULES[lang])}]
        self._question = ""

    def _place(self, place: str) -> dict:
        """Look up the model's place argument; if that finds nothing, use the user's own words.

        Small models often garble Bangla place names when copying them into arguments.
        """
        r = self.status.place(place)
        if r["found"] == 0 and self._question:
            r = self.status.place(self._question)
        return r

    def _top_n(self, args: dict) -> int:
        try:
            return max(1, min(10, int(args.get("limit", 5))))
        except (TypeError, ValueError):
            return 5

    def _run_tool(self, name: str, args: dict) -> dict:
        now = self.status.now.strftime("%Y-%m-%d %H:%M")
        if name == "get_ward_status":
            r = self._place(str(args.get("place", "")))
            return {"query": r["query"], "now": now, "found": r["found"], "wards": public(r["wards"])}
        if name == "get_top_risk_wards":
            return {"now": now, "wards": public(self.status.top(self._top_n(args)))}
        return {"error": f"unknown tool {name}"}

    def _routed_ask(self, question: str) -> str:
        """The model only picks the tool; the reply comes from templates in self.lang."""
        msg = self.llm.chat([self.history[0], {"role": "user", "content": question}], tools=TOOLS)
        call = (msg.tool_calls or [None])[0]
        if call and call.function.name == "get_top_risk_wards":
            args = json.loads(call.function.arguments or "{}")
            return summarize_top(self.status.top(self._top_n(args)), self.status.now, self.lang)
        if call and call.function.name == "get_ward_status":
            args = json.loads(call.function.arguments or "{}")
            return summarize(self._place(str(args.get("place", ""))), self.lang)
        return summarize(self.status.place(question), self.lang)

    def ask(self, question: str) -> str:
        self._question = question
        if self.llm is None:
            return summarize(self.status.place(question), self.lang)
        if self.lang not in reply_langs():
            try:
                return self._routed_ask(question)
            except Exception as e:
                print(f"⚠ model failed: {e}", file=sys.stderr)
                return summarize(self.status.place(question), self.lang)

        self.history.append({"role": "user", "content": question})
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                msg = self.llm.chat(self.history, tools=TOOLS)
                self.history.append(_assistant_entry(msg))
                if not msg.tool_calls:
                    return msg.content or ""
                for call in msg.tool_calls:
                    result = self._run_tool(call.function.name, json.loads(call.function.arguments or "{}"))
                    self.history.append({"role": "tool", "tool_call_id": call.id,
                                         "content": json.dumps(result, ensure_ascii=False)})
        except Exception as e:  # model unavailable → rule-based answer, the conversation goes on
            print(f"⚠ model failed: {e}", file=sys.stderr)
        return summarize(self.status.place(question), self.lang)


def main():
    ap = argparse.ArgumentParser(description="Jolrekha chatbot")
    ap.add_argument("--run", default="forecast", help="which run under outputs/ (forecast or replay_YYYY-MM-DD)")
    ap.add_argument("--now", help="what 'now' means in a replay, e.g. '2024-05-26 18:00'")
    ap.add_argument("--lang", choices=["bn", "en"], default="bn", help="reply language (default Bangla)")
    ap.add_argument("--ask", help="ask one question and exit")
    args = ap.parse_args()

    status = Status(args.run, args.now)
    bot = Chatbot(status, args.lang)
    mode = bot.llm.model if bot.llm else "rule-based (no MODEL_API_KEY)"
    if status.stale:
        print("⚠ Forecast is stale — run `python -m jolrekha.pipeline --mode forecast` first", file=sys.stderr)
    if args.ask:
        print(bot.ask(args.ask))
        return
    print(f"Jolrekha chatbot · {mode} · {args.lang} · now = {fmt_time(status.now, 'en')}\nAsk a question (q to quit)")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if q.lower() in {"q", "quit", "exit"}:
            break
        if q:
            print(bot.ask(q))


if __name__ == "__main__":
    main()
