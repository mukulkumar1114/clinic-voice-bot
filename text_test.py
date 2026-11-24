"""Talk to the bot by TEXT (no mic, no voice) to test its brain and tools.

  python text_test.py I04                         # uses the scenario's 'caller_says' line
  python text_test.py I04 "haan 1 baje theek hai"  # add more turns after it
"""

import asyncio
import json
import sys
from datetime import timedelta

from livekit.agents import AgentSession

import agent as bot
import db


def build_agent(sc: dict):
    rules = bot.RULES.format(brand=db.BRAND, calendar=bot.calendar_hint(), clinics=bot.clinic_list(), services=bot.service_list(), **bot.date_facts())
    if sc["kind"] == "reminder":
        cid = db.get_appointment(sc["appointment_id"])["customer_id"]
        appts = [db.get_appointment(a["id"]) for a in db.customer_appointments(cid)["upcoming"]
                 if a["appt_date"] <= (db.now().date() + timedelta(days=1)).isoformat()]
        task = bot.REMINDER.format(customer_name=appts[0]["customer_name"], brand=db.BRAND,
                                   appt_lines="\n".join(bot.appt_line(a) for a in appts),
                                   dues_line=bot.dues_line(cid))
        return bot.Receptionist(rules + task, customer_id=cid, caller_phone=appts[0]["phone"], text_mode=True), "Start the reminder call now (step 1)."
    line, cid = bot.caller_context(sc["caller_phone"])
    return bot.Receptionist(rules + bot.INBOUND.format(caller_line=line), customer_id=cid, caller_phone=sc["caller_phone"], text_mode=True), None


def show(result):
    for ev in result.events:
        item = getattr(ev, "item", None)
        kind = type(item).__name__
        if kind == "FunctionCall":
            print(f"   [tool] {item.name}({item.arguments})")
        elif kind == "FunctionCallOutput":
            print(f"   [result] {item.output[:200]}")
        elif kind == "ChatMessage" and item.role == "assistant":
            print(f"BOT: {item.text_content}")


async def main():
    sc = db.scenario(sys.argv[1])
    print(f"=== {sc['id']} {sc['category']} | expected: {sc['expected_bot_action']}  (model: {bot.LLM_MODEL})\n")
    agent, opening = build_agent(sc)
    turns = ([] if sc["kind"] == "reminder" else [sc["caller_says"]]) + sys.argv[2:]
    async with bot.make_llm() as llm, AgentSession(llm=llm) as session:
        await session.start(agent)
        if opening:
            show(await session.run(user_input="(call connected)"))
        for t in turns:
            print(f"\nCALLER: {t}")
            show(await session.run(user_input=t))


if __name__ == "__main__":
    asyncio.run(main())
