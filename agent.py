"""Clinic voice bot: reminder calls + inbound booking / rescheduling (FAKE data only).

Test in the terminal (you play the customer with your Mac mic):
  SCENARIO=R01 python agent.py console     # any id from test_scenarios.csv
  python agent.py console                  # inbound call with no caller ID

SAFETY: a real phone call is only ever placed to TEST_CALL_NUMBER from .env,
never to a number from the database.
"""

import dataclasses
import json
import logging
import os
from datetime import date, timedelta

from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, function_tool, inference
from livekit.agents.beta import EndCallTool
from livekit.plugins import anthropic, silero

import db

load_dotenv(".env")
log = logging.getLogger("clinic-bot")

# Brain: Claude if ANTHROPIC_API_KEY is set, else a model through LiveKit Inference (no extra key needed).
USE_CLAUDE = bool(os.getenv("ANTHROPIC_API_KEY"))
LLM_MODEL = os.getenv("LLM_MODEL") or ("claude-opus-5-5" if USE_CLAUDE else "google/gemini-3-flash")


def make_llm():
    if USE_CLAUDE and LLM_MODEL.startswith("claude"):
        return anthropic.LLM(model=LLM_MODEL, caching="ephemeral")
    return inference.LLM(model=LLM_MODEL)
TTS_MODEL = os.getenv("TTS_MODEL", "cartesia/sonic-3")
TTS_VOICE = os.getenv("TTS_VOICE", "")
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "hi")
# Speech-to-text language. "multi" guessed the language word by word and mis-heard Indian-accent Hinglish
# (11-24 test: 5 of 9 turns garbled), so default to Hindi mode. Set STT_LANGUAGE=multi in .env to go back.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "hi")
BASE_KEYTERMS = ["Happy Paws", "Saket", "reschedule", "confirm", "appointment", "cancel", "consultation",
                 "vaccination", "grooming", "video consult", "home visit", "WhatsApp"]


def stt_keyterms(customer_id: int | None) -> list[str]:
    """Words the speech model should expect: brand, clinic areas, doctors, and this caller's name + pets."""
    terms = list(BASE_KEYTERMS)
    try:
        for k in db.clinics():
            terms.append(k["name"].replace("Happy Paws", "").strip() or k["name"])
            terms += [d["name"] for d in db.doctors(k["id"])]
        if customer_id:
            with db.connect() as con:
                row = con.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
                if row:
                    terms.append(row[0])
                terms += [r[0] for r in con.execute("SELECT name FROM pets WHERE customer_id = ?", (customer_id,))]
    except Exception as e:  # a missing word list must never break the call
        log.warning("keyterms not built: %s", e)
    seen, out, total = set(), [], 0
    for t in terms:
        t = (t or "").strip()
        if t and t.lower() not in seen and total + len(t) <= 1100:   # Deepgram: max 100 terms / 1200 chars
            seen.add(t.lower()); out.append(t); total += len(t)
    return out[:100]


def date_facts() -> dict:
    t = db.now().date()
    return {"today": t.strftime("%A %d %B %Y"),
            "last_day": (t + timedelta(days=db.MAX_DAYS_AHEAD)).strftime("%d %B %Y")}


def calendar_hint() -> str:
    today = db.now().date()
    out = []
    for i in range(14):
        d = today + timedelta(days=i)
        tag = " (today)" if i == 0 else " (tomorrow)" if i == 1 else ""
        out.append(f"{d.strftime('%A')} {d.isoformat()}{tag}")
    return "\n".join(out)


def clinic_list() -> str:
    lines = []
    for k in db.clinics():
        extras = [x for x, f in [("emergency", "has_emergency"), ("surgery", "has_surgery"), ("grooming", "has_grooming"), ("exotics vet", "has_exotic_vet")] if k[f]]
        closed = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k["closed_weekday"]]
        lines.append(f"- id {k['id']}: {k['name']}, {k['city']}. {k['open_time']}-{k['close_time']}, closed {closed}. "
                     f"Has: {', '.join(extras) or 'basic services'}. Home visits up to {k['home_visit_km']} km. Address: {k['address']}. Phone {k['phone']}")
    return "\n".join(lines)


def service_list() -> str:
    return "\n".join(f"- {s['code']}: {s['name']}, Rs {s['price']}. Pets: {s['species_allowed']}. {s['prep_note']}" for s in db.services())


RULES = """
You are Asha, the phone receptionist for {brand}, a chain of pet clinics.
This is a live phone call, so talk like a friendly Indian receptionist:
- Reply in the caller's language. Hinglish callers get natural Hinglish (Hindi in Devanagari, English words like appointment, vaccination in Latin script). If they want a language you can't speak well, politely continue in simple English or Hindi.
- One or two short sentences per reply. One question at a time. No lists, markdown, emojis or symbols.
- Say times like "saadhe gyaarah baje" or "11:30 AM". Say prices like "nau sau rupaye".

Hard rules:
- You CANNOT send or pass on anything: no WhatsApp, SMS, email, link, location or photo, and no message or note to the doctor. You have no way to record a symptom or a note for the doctor. So NEVER say "note kar leti hoon", "noted", "maine note kar liya", "doctor ko bata dungi", "bhej deti hoon" or "WhatsApp kar dungi". If the caller asks for any of this (even again and again), say it kindly in one line, for example: "Yeh main doctor tak nahi pahuncha sakti, aap visit par doctor ko khud bata dijiyega." For an address, read it out instead. Only exception: right after create_ticket succeeds you may say the team has noted it.
- Never invent slots, prices, doctors, discounts or policies. Use the tools and the lists below.
- If a tool result says it could not do something, tell the caller it did NOT go through and what you will do instead. Never say booked, confirmed, rescheduled or cancelled unless the tool result says so.
- Before offering ANY time, day or doctor (new booking or a change), call check_free_slots first and offer only times it returned.
- Before booking, rescheduling or cancelling, repeat pet name, clinic, date and time and get a clear yes.
- If a customer has several upcoming appointments, ask which one before changing anything.
- Rescheduling means reschedule_appointment on the EXISTING appointment id. Never book a new appointment for a reschedule.
- When changing several appointments, read out EVERY appointment with its new date and time, and get one clear yes, before changing any of them.
- NEVER give medical advice: no medicine names, no vaccine names or vaccine schedules, no diet or home remedies. Say the doctor will decide at the visit, and offer a consultation or video consultation.
- Never mention tool names or say "tool" to the caller.
- Always answer the caller's actual question first (even if the answer is "we don't offer that"), then help further.
- Dates: always say the date with the month name. If the date the caller asked for is not exactly the date you are about to book, stop and point out the difference. Bookings open only up to {last_day}; for a later date say bookings are not open yet and ask them to call closer to the date, or pick a nearer date.
- EMERGENCY (poisoning, accident, heavy bleeding, breathing trouble, seizures, a male cat that can't pass urine, collapse): skip booking. Tell them to go NOW to the nearest clinic that has emergency, and give its address.
- Billing problems, complaints, lab reports, prescription refills, membership questions, or a request for a human: say sorry if something went wrong, use create_ticket, and tell them the team will call back within 24 hours. Never promise an outcome (refund, discount, speed).
- After a booking succeeds, always tell the caller the prep note from the tool result, if there is one.
- Home visit: first compare the customer's distance_km with the clinic's home visit limit. If it is further, say home visits don't reach them and offer a video consult or clinic visit.
- Do not read out personal details (phone, address, other pets) to someone who has not been identified.
- If a pet has died, be kind, offer condolences, cancel its appointments, use mark_pet_deceased. Never try to sell anything.
- When the caller is done, say a short goodbye and use end_call.

Today is {today}. Dates (use these exact YYYY-MM-DD values in tools):
{calendar}

Clinics:
{clinics}

Services and prices:
{services}
"""

INBOUND = """
This is an INBOUND call: the customer called you.
{caller_line}
If the number is not found, ask for their registered number (they may use another phone), or register them as a new customer.
"""

REMINDER = """
This is an OUTBOUND REMINDER call you are making to {customer_name}. The customer is already identified (it is their registered number):
do NOT call lookup_customer or register_customer. Use the appointment ids below for confirm / reschedule / cancel.
Appointments to remind about:
{appt_lines}
Steps:
1. Greet {customer_name} by name, say you are calling from {brand}, and remind them (all appointments in one go).
2. Ask if they will come. Yes -> confirm_appointment for each. Want another time -> find free slots and reschedule. Want to cancel -> confirm and cancel.
3. If an appointment says DOCTOR ON LEAVE, apologise and offer another doctor at the same time, or another day.
{dues_line}
4. Surgery or lab test: tell them the preparation note. Home visit: confirm the full address and a landmark.
5. Wrong person on the line: apologise, share NO details, create_ticket category 'wrong_number', end call.
6. Busy: ask one quick yes/no; if they can't talk, create_ticket category 'callback' and end politely.
"""


class Receptionist(Agent):
    def __init__(self, instructions: str, customer_id: int | None = None, caller_phone: str | None = None, text_mode: bool = False):
        if text_mode:  # tests without a real call: a simple end_call that just records it
            async def _end(context: RunContext) -> str:
                return "Call ended. Say nothing more."
            tools = [function_tool(_end, name="end_call", description="End the call after saying a short goodbye.")]
        else:
            tools = [EndCallTool()]
        super().__init__(instructions=instructions, tools=tools)
        self.customer_id = customer_id
        self.caller_phone = caller_phone

    # ---------------- look-ups

    @function_tool
    async def lookup_customer(self, context: RunContext, phone: str) -> str:
        """Find a customer by phone (main or alternate number). Returns their pets and appointments.

        Args:
            phone: 10-digit phone number, digits only.
        """
        c = db.find_customer(phone)
        if self.customer_id and (not c or c["id"] != self.customer_id):
            return "The customer on this call is already identified. Do not look up anyone else; use the details you already have."
        if not c:
            return "Not found. Ask if they have another registered number, else register_customer."
        self.customer_id = c["id"]
        keep = ("id", "name", "home_clinic", "home_clinic_id", "city", "distance_km", "is_member", "no_show_count")
        return json.dumps({"customer": {k: c[k] for k in keep}, "pets": c["pets"], **db.customer_appointments(c["id"])}, default=str)

    @function_tool
    async def register_customer(self, context: RunContext, name: str, phone: str, city: str, pet_name: str, species: str) -> str:
        """Register a new customer with their first pet.

        Args:
            name: Customer name.
            phone: 10-digit phone number.
            city: City they live in.
            pet_name: Pet's name.
            species: dog, cat, rabbit or bird.
        """
        if self.customer_id:
            return "This customer is already registered and identified. Use add_pet for a new pet."
        if db.find_customer(phone):
            return "Already registered. Use lookup_customer."
        cid = db.create_customer(name, phone, city)
        self.customer_id = cid
        return json.dumps({"customer_id": cid, "pet_id": db.add_pet(cid, pet_name, species)})

    @function_tool
    async def add_pet(self, context: RunContext, pet_name: str, species: str, breed: str = "") -> str:
        """Add a pet for the identified customer.

        Args:
            pet_name: Pet's name.
            species: dog, cat, rabbit or bird.
            breed: Breed if known.
        """
        if not self.customer_id:
            return "Identify the customer first."
        return json.dumps({"pet_id": db.add_pet(self.customer_id, pet_name, species, breed or None)})

    @function_tool
    async def check_vaccines(self, context: RunContext, pet_id: int) -> str:
        """Vaccination history of a pet and what is overdue or due soon.

        Args:
            pet_id: Pet id.
        """
        if not self._owns_pet(pet_id):
            return "Pet not found for this customer."
        v = db.vaccines(pet_id)
        return json.dumps(v) if v else "No vaccination records with us."

    @function_tool
    async def check_free_slots(self, context: RunContext, clinic_id: int, day: str, service_code: str, pet_id: int = 0, doctor_name: str = "") -> str:
        """Free times on a date for a service at a clinic.

        Args:
            clinic_id: Clinic id from the clinic list.
            day: Date as YYYY-MM-DD.
            service_code: One of the service codes, e.g. consult, vaccination, surgery, grooming, home_visit, video.
            pet_id: Pet id if known (needed for birds and rabbits).
            doctor_name: Only if the caller asked for a specific doctor.
        """
        try:
            d = date.fromisoformat(day)
        except ValueError:
            return "That date does not exist. Ask again."
        species = (db.pet(pet_id) or {}).get("species", "dog") if pet_id else "dog"
        res = db.free_slots(clinic_id, d, service_code, species, doctor_name or None)
        if not res["slots"]:
            return f"No free slots: {res['reason']}. Offer another day or clinic."
        return json.dumps(res["slots"])

    # ---------------- changes

    @function_tool
    async def book_appointment(self, context: RunContext, pet_id: int, clinic_id: int, service_code: str, day: str, time: str,
                               doctor_name: str = "", home_address: str = "") -> str:
        """Book a new appointment. Only after the caller said yes to pet, clinic, date and time.

        Args:
            pet_id: Pet id.
            clinic_id: Clinic id.
            service_code: Service code.
            day: YYYY-MM-DD.
            time: HH:MM 24-hour, must be a free slot.
            doctor_name: Only if the caller asked for one.
            home_address: Full address with landmark, required for home_visit.
        """
        if not self._owns_pet(pet_id):
            return "That pet does not belong to this customer."
        if service_code == "home_visit":
            cust = db._one("SELECT distance_km FROM customers WHERE id = ?", (self.customer_id,))
            limit = db.clinic(clinic_id)["home_visit_km"]
            if cust and cust["distance_km"] and cust["distance_km"] > limit:
                return f"Customer lives {cust['distance_km']} km away; home visits only up to {limit} km. Offer video consult or clinic visit."
            if not home_address:
                return "Ask for the full address and a landmark first."
        appt_id, why = db.book(pet_id, clinic_id, service_code, date.fromisoformat(day), time, doctor_name or None, home_address or None)
        if not appt_id:
            return f"Could not book: {why}. Check free slots again."
        a = db.get_appointment(appt_id)
        log.info("booked %s", appt_id)
        return f"Booked, appointment id {appt_id}, with {a['doctor_name'] or 'groomer'}. Prep note: {a['prep_note'] or 'none'}"

    @function_tool
    async def reschedule_appointment(self, context: RunContext, appointment_id: int, day: str, time: str, doctor_name: str = "") -> str:
        """Move an appointment to a new date/time (same clinic and service). Only after a clear yes.

        Args:
            appointment_id: Appointment id.
            day: New date YYYY-MM-DD.
            time: New time HH:MM 24-hour.
            doctor_name: Only if the caller asked for one.
        """
        a = self._own_active(appointment_id)
        if isinstance(a, str):
            return a
        why = db.reschedule(appointment_id, date.fromisoformat(day), time, doctor_name or None)
        if why:
            return f"Could not reschedule: {why}."
        log.info("rescheduled %s", appointment_id)
        return f"Rescheduled to {day} {time}."

    @function_tool
    async def cancel_appointment(self, context: RunContext, appointment_id: int, reason: str) -> str:
        """Cancel an appointment after the caller clearly said yes.

        Args:
            appointment_id: Appointment id.
            reason: Short reason the caller gave (or 'not given').
        """
        a = self._own_active(appointment_id)
        if isinstance(a, str):
            return a
        db.cancel(appointment_id, reason)
        log.info("cancelled %s", appointment_id)
        return "Cancelled."

    @function_tool
    async def confirm_appointment(self, context: RunContext, appointment_id: int) -> str:
        """Mark that the customer confirmed they will come.

        Args:
            appointment_id: Appointment id.
        """
        a = self._own_active(appointment_id)
        if isinstance(a, str):
            return a
        db.confirm(appointment_id)
        return "Confirmed."

    @function_tool
    async def mark_pet_deceased(self, context: RunContext, pet_id: int) -> str:
        """Record that a pet has passed away. Also cancels its upcoming appointments.

        Args:
            pet_id: Pet id.
        """
        if not self._owns_pet(pet_id):
            return "Pet not found for this customer."
        db.mark_pet_deceased(pet_id)
        for a in db.customer_appointments(self.customer_id)["upcoming"]:
            if a["pet_name"] == db.pet(pet_id)["name"]:
                db.cancel(a["id"], "pet passed away")
        return "Recorded, and upcoming appointments for this pet were cancelled."

    @function_tool
    async def create_ticket(self, context: RunContext, category: str, summary: str) -> str:
        """Hand something to the human team (they call back within 24 hours).

        Args:
            category: billing, complaint, lab_report, prescription, membership, callback, wrong_number, human_requested, other.
            summary: One or two lines on what the caller needs.
        """
        tid = db.create_ticket(self.customer_id, self.caller_phone, category, summary)
        return f"Ticket {tid} created."

    # ---------------- a caller can only touch their own data

    def _owns_pet(self, pet_id: int) -> bool:
        p = db.pet(pet_id)
        return bool(p and self.customer_id and p["customer_id"] == self.customer_id)

    def _own_active(self, appt_id: int) -> dict | str:
        a = db.get_appointment(appt_id)
        if not a or a["customer_id"] != self.customer_id:
            return "No such appointment for this customer."
        if a["status"] not in db.ACTIVE:
            return f"This appointment is {a['status']}, it can't be changed. Offer a new booking."
        return a


def caller_context(phone: str | None) -> tuple[str, int | None]:
    """Look the caller up BEFORE the conversation, so the bot already knows who is calling."""
    if not phone:
        return "No caller ID. Ask for their registered phone number, then lookup_customer.", None
    c = db.find_customer(phone)
    if not c:
        return (f"Caller ID {phone} is NOT registered. Ask if they have another registered number "
                "(then lookup_customer), or register them as a new customer."), None
    appts = db.customer_appointments(c["id"])
    keep = ("id", "name", "home_clinic", "home_clinic_id", "city", "distance_km", "is_member", "no_show_count")
    info = json.dumps({"customer": {k: c[k] for k in keep}, "pets": c["pets"], **appts,
                       "pending_payments": db.pending_dues(c["id"])}, default=str)
    return (f"Caller ID {phone} matches this customer (already looked up, no need to call lookup_customer):\n{info}\n"
            "Use their home clinic unless they ask for another one. In your first reply, greet them by name AND answer their question in the same reply."), c["id"]


def dues_line(customer_id: int) -> str:
    dues = db.pending_dues(customer_id)
    if not dues:
        return "3b. No pending payments."
    items = "; ".join(f"Rs {d['due']} for {d['pet_name']}'s {d['service']} on {d['appt_date']}" for d in dues)
    return (f"3b. Pending payment: {items}. After they confirm, mention it once, gently: it can be paid at the visit. "
            "Do not pressure, and do not book anything new for it.")


def appt_line(a: dict) -> str:
    when = "TODAY" if a["appt_date"] == db.now().date().isoformat() else "tomorrow"
    line = (f"- appointment id {a['id']}, pet id {a['pet_id']}: {a['pet_name']} ({a['species']}), {a['service_name']}, {when} {a['appt_date']} at {a['appt_time']}, "
            f"{a['clinic_name']}, {a['doctor_name'] or 'groomer'}.")
    if a.get("doctor_on_leave"):
        line += " DOCTOR ON LEAVE that day."
    if a["prep_note"]:
        line += f" Prep: {a['prep_note']}"
    if a["home_address"]:
        line += f" Address on file: {a['home_address']}."
    return line


server = AgentServer()


@server.rtc_session(agent_name="clinic-receptionist")
async def entrypoint(ctx: agents.JobContext):
    meta = json.loads(ctx.job.metadata) if ctx.job.metadata else {}

    # Console testing: SCENARIO=R01 picks the customer/appointments from test_scenarios
    sc = db.scenario(os.getenv("SCENARIO", "")) if os.getenv("SCENARIO") else None
    if sc:
        print(f"\n=== Scenario {sc['id']} ({sc['kind']}): {sc['category']}\n    Setup: {sc['setup']}\n"
              f"    Try saying: {sc['caller_says']}\n    Bot should: {sc['expected_bot_action']}\n")
        if sc["kind"] == "reminder":
            cid = db.get_appointment(sc["appointment_id"])["customer_id"]
            ids = [a["id"] for a in db.customer_appointments(cid)["upcoming"]
                   if a["appt_date"] <= (db.now().date() + timedelta(days=1)).isoformat()]
            meta = {"appointment_ids": ids}
        else:
            meta = {"caller_phone": sc["caller_phone"]}

    rules = RULES.format(brand=db.BRAND, calendar=calendar_hint(), clinics=clinic_list(), services=service_list(), **date_facts())
    appt_ids = meta.get("appointment_ids") or []

    if appt_ids:
        appts = [db.get_appointment(i) for i in appt_ids]
        first = appts[0]
        task = REMINDER.format(customer_name=first["customer_name"], brand=db.BRAND, appt_lines="\n".join(appt_line(a) for a in appts),
                               dues_line=dues_line(first["customer_id"]))
        agent = Receptionist(rules + task, customer_id=first["customer_id"], caller_phone=first["phone"])
        opening = "Start the reminder call now (step 1)."
    else:
        caller = meta.get("caller_phone")
        caller_line, cid = caller_context(caller)
        agent = Receptionist(rules + INBOUND.format(caller_line=caller_line), customer_id=cid, caller_phone=caller)
        opening = "Greet: namaste, Happy Paws, and ask how you can help."

    tts_kwargs = {"language": TTS_LANGUAGE}
    if TTS_VOICE:
        tts_kwargs["voice"] = TTS_VOICE
    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3", language=STT_LANGUAGE,
                          extra_kwargs={"keyterm": stt_keyterms(agent.customer_id)}),
        llm=make_llm(),
        tts=inference.TTS(model=TTS_MODEL, **tts_kwargs),
        vad=silero.VAD.load(),
    )
    await session.start(room=ctx.room, agent=agent)

    # Call log: transcript + per-turn timings + model usage, saved after every turn
    # (so Ctrl+C in console mode still leaves a file). results/voice_<scenario>_<time>.json
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                            f"voice_{sc['id'] if sc else 'call'}_{db.now().strftime('%Y%m%d_%H%M%S')}.json")

    def save_call_log(*_):
        try:
            usage = [dataclasses.asdict(u) if dataclasses.is_dataclass(u) else getattr(u, "__dict__", str(u))
                     for u in session.usage.model_usage]
            data = {"scenario": sc["id"] if sc else None,
                    "history": session.history.to_dict(exclude_timestamp=False),
                    "usage": usage}
            with open(log_path, "w") as f:
                json.dump(data, f, indent=1, default=str, ensure_ascii=False)
        except Exception as e:  # logging must never break the call
            log.warning("call log not saved: %s", e)

    session.on("conversation_item_added", save_call_log)
    session.on("function_tools_executed", save_call_log)

    async def _save_on_shutdown():
        save_call_log()
    ctx.add_shutdown_callback(_save_on_shutdown)

    # Real phone reminder (phase 2). SAFETY: always dials TEST_CALL_NUMBER, never the customer's number.
    if appt_ids and meta.get("dial") and os.getenv("SIP_OUTBOUND_TRUNK_ID"):
        test_number = os.getenv("TEST_CALL_NUMBER", "")
        if not test_number:
            log.error("TEST_CALL_NUMBER not set; refusing to dial")
            ctx.shutdown()
            return
        try:
            await ctx.api.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                room_name=ctx.room.name, sip_trunk_id=os.environ["SIP_OUTBOUND_TRUNK_ID"],
                sip_call_to=test_number, participant_identity="test-callee", wait_until_answered=True))
        except api.TwirpError as e:
            log.error("call failed: %s", e.message)
            ctx.shutdown()
            return

    if appt_ids:
        db.mark_reminder_sent(appt_ids)
    await session.generate_reply(instructions=opening)


if __name__ == "__main__":
    agents.cli.run_app(server)
