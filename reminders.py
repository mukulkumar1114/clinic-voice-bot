"""Find who needs a reminder call and (optionally) start the calls.

Rules: appointments tomorrow, or later today; skip already confirmed, already reminded,
do-not-call customers and deceased pets. One call per customer covers all their appointments.

  python reminders.py          # dry run: list who would be called
  python reminders.py --call   # start calls. SAFETY: every call goes to TEST_CALL_NUMBER only.
"""

import asyncio
import json
import os
import sys
from itertools import groupby

from dotenv import load_dotenv
from livekit import api

import db

load_dotenv(".env")


def grouped() -> list[list[dict]]:
    due = db.due_for_reminder()
    return [list(g) for _, g in groupby(due, key=lambda a: a["customer_id"])]


async def start_calls(groups) -> None:
    lk = api.LiveKitAPI()
    try:
        for g in groups:
            room = f"reminder-{g[0]['customer_id']}-{db.now().strftime('%Y%m%d%H%M')}"
            await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                agent_name="clinic-receptionist", room=room,
                metadata=json.dumps({"appointment_ids": [a["id"] for a in g], "dial": True})))
            print(f"  call started for {g[0]['customer_name']} -> TEST_CALL_NUMBER")
    finally:
        await lk.aclose()


def main() -> None:
    groups = grouped()
    print(f"{sum(len(g) for g in groups)} appointment(s) due, {len(groups)} call(s):")
    for g in groups[:40]:
        items = "; ".join(f"#{a['id']} {a['pet_name']} {a['service_code']} {a['appt_date']} {a['appt_time']}" for a in g)
        print(f"  {g[0]['customer_name']:25s} {items}")
    if len(groups) > 40:
        print(f"  ... and {len(groups) - 40} more")
    if "--call" not in sys.argv:
        print("\nDry run. Add --call to start calls (they all go to TEST_CALL_NUMBER).")
        return
    if not (os.getenv("SIP_OUTBOUND_TRUNK_ID") and os.getenv("TEST_CALL_NUMBER")):
        print("\nSet SIP_OUTBOUND_TRUNK_ID and TEST_CALL_NUMBER in .env first.")
        return
    asyncio.run(start_calls(groups[:1]))   # one call at a time while testing


if __name__ == "__main__":
    main()
