"""Read/write helpers for clinic.db (built by generate_data.py, all fake data).

Booking rules:
  - 30-minute slots inside clinic hours; nothing on the clinic's closed weekday.
  - A doctor sees one pet per slot, and only on their working weekdays, not on leave days.
  - Grooming needs no doctor; one grooming per slot per clinic.
  - Surgery only 10:00-12:00 and only at clinics with surgery. Grooming only where offered.
  - Birds and rabbits only with an 'Exotics' doctor (if the clinic has one).
  - Bookings open up to 60 days ahead; same-day needs 30 minutes notice.
"""

import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).parent / "clinic.db"
TZ = ZoneInfo("Asia/Kolkata")
BRAND = "Happy Paws Pet Clinics"
MAX_DAYS_AHEAD = 60
SURGERY_SLOTS = {"10:00", "10:30", "11:00", "11:30"}
EXOTIC = {"bird", "rabbit"}
ACTIVE = ("scheduled", "confirmed")


def now() -> datetime:
    return datetime.now(TZ)


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _all(sql, args=()) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def _one(sql, args=()) -> dict | None:
    rows = _all(sql, args)
    return rows[0] if rows else None


def _write(sql, args=()) -> int:
    con = connect()
    cur = con.execute(sql, args)
    con.commit()
    con.close()
    return cur.lastrowid


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits[-10:]


# ---------------------------------------------------------------- clinics / services

def clinics(city: str | None = None) -> list[dict]:
    if city:
        return _all("SELECT * FROM clinics WHERE lower(city) = lower(?) OR lower(area) LIKE lower(?)", (city, f"%{city}%"))
    return _all("SELECT * FROM clinics")


def clinic(clinic_id: int) -> dict | None:
    return _one("SELECT * FROM clinics WHERE id = ?", (clinic_id,))


def services() -> list[dict]:
    return _all("SELECT * FROM services")


def service(code: str) -> dict | None:
    return _one("SELECT * FROM services WHERE code = ?", (code,))


def doctors(clinic_id: int) -> list[dict]:
    return _all("SELECT * FROM doctors WHERE clinic_id = ?", (clinic_id,))


def doctor_on_leave(doctor_id: int, day: str) -> bool:
    return _one("SELECT 1 x FROM doctor_leaves WHERE doctor_id = ? AND leave_date = ?", (doctor_id, day)) is not None


# ---------------------------------------------------------------- customers / pets

def find_customer(phone: str) -> dict | None:
    p = normalize_phone(phone)
    c = _one(
        "SELECT c.*, k.name AS home_clinic FROM customers c LEFT JOIN clinics k ON k.id = c.home_clinic_id "
        "WHERE c.phone = ? OR c.alt_phone = ?",
        (p, p),
    )
    if not c:
        return None
    c["pets"] = _all(
        "SELECT id, name, species, breed, sex, dob, temperament, allergies, is_deceased FROM pets WHERE customer_id = ?",
        (c["id"],),
    )
    return c


def create_customer(name: str, phone: str, city: str | None = None) -> int:
    home = clinics(city)[0]["id"] if city and clinics(city) else None
    return _write(
        "INSERT INTO customers(name, phone, city, home_clinic_id, preferred_language, is_member, do_not_call, no_show_count, created_at) "
        "VALUES (?, ?, ?, ?, 'hinglish', 0, 0, 0, ?)",
        (name.strip(), normalize_phone(phone), city, home, now().isoformat(timespec="seconds")),
    )


def add_pet(customer_id: int, name: str, species: str, breed: str | None = None) -> int:
    return _write(
        "INSERT INTO pets(customer_id, name, species, breed, temperament, is_deceased) VALUES (?, ?, ?, ?, 'friendly', 0)",
        (customer_id, name.strip(), species.strip().lower(), breed),
    )


def pet(pet_id: int) -> dict | None:
    return _one("SELECT * FROM pets WHERE id = ?", (pet_id,))


def mark_pet_deceased(pet_id: int) -> None:
    _write("UPDATE pets SET is_deceased = 1, deceased_on = ? WHERE id = ?", (now().date().isoformat(), pet_id))


def vaccines(pet_id: int) -> list[dict]:
    """Latest record per vaccine, with overdue / due soon status."""
    rows = _all(
        "SELECT vaccine, MAX(given_on) given_on, MAX(next_due) next_due FROM vaccinations WHERE pet_id = ? GROUP BY vaccine",
        (pet_id,),
    )
    today = now().date()
    for r in rows:
        due = date.fromisoformat(r["next_due"])
        r["status"] = "overdue" if due < today else "due within 30 days" if due <= today + timedelta(days=30) else "not due yet"
    return rows


# ---------------------------------------------------------------- appointments

APPT_SQL = """
SELECT a.*, p.name AS pet_name, p.species, p.customer_id, p.is_deceased,
       c.name AS customer_name, c.phone, c.do_not_call, c.preferred_language, c.no_show_count,
       k.name AS clinic_name, k.address AS clinic_address, d.name AS doctor_name, s.name AS service_name, s.prep_note
FROM appointments a
JOIN pets p ON p.id = a.pet_id
JOIN customers c ON c.id = p.customer_id
JOIN clinics k ON k.id = a.clinic_id
LEFT JOIN doctors d ON d.id = a.doctor_id
JOIN services s ON s.code = a.service_code
"""


def get_appointment(appt_id: int) -> dict | None:
    a = _one(APPT_SQL + " WHERE a.id = ?", (appt_id,))
    if a and a["doctor_id"]:
        a["doctor_on_leave"] = doctor_on_leave(a["doctor_id"], a["appt_date"])
    return a


def customer_appointments(customer_id: int) -> dict:
    today = now().date()
    upcoming = _all(
        APPT_SQL + " WHERE p.customer_id = ? AND a.status IN ('scheduled','confirmed') AND a.appt_date >= ? ORDER BY a.appt_date, a.appt_time",
        (customer_id, today.isoformat()),
    )
    recent = _all(
        APPT_SQL + " WHERE p.customer_id = ? AND a.appt_date < ? AND a.appt_date >= ? ORDER BY a.appt_date DESC",
        (customer_id, today.isoformat(), (today - timedelta(days=30)).isoformat()),
    )
    keep = ("id", "pet_name", "appt_date", "appt_time", "status", "service_name", "clinic_name", "doctor_name", "visit_type")
    return {
        "upcoming": [{k: a[k] for k in keep} for a in upcoming],
        "last_30_days": [{k: a[k] for k in keep} for a in recent],
    }


def _name_match(asked: str, full: str) -> bool:
    a = asked.lower().replace("dr.", "").replace("dr ", "").strip()
    return bool(a) and a in full.lower()


def free_slots(clinic_id: int, day: date, service_code: str, species: str = "dog", doctor_name: str | None = None) -> dict:
    """Returns {"slots": {"HH:MM": [doctor names]}, "reason": why empty}."""
    k = clinic(clinic_id)
    s = service(service_code)
    if not k or not s:
        return {"slots": {}, "reason": "unknown clinic or service"}
    if species not in s["species_allowed"].split(","):
        return {"slots": {}, "reason": f"{s['name']} is not available for {species}"}
    if service_code == "surgery" and not k["has_surgery"]:
        return {"slots": {}, "reason": f"{k['name']} does not do surgery"}
    if service_code == "grooming" and not k["has_grooming"]:
        return {"slots": {}, "reason": f"{k['name']} does not do grooming"}
    today = now().date()
    if day < today:
        return {"slots": {}, "reason": "date is in the past"}
    if day > today + timedelta(days=MAX_DAYS_AHEAD):
        return {"slots": {}, "reason": f"bookings open only {MAX_DAYS_AHEAD} days ahead"}
    if day.weekday() == k["closed_weekday"]:
        return {"slots": {}, "reason": f"{k['name']} is closed on {day.strftime('%A')}"}

    times = []
    t = datetime.combine(day, time.fromisoformat(k["open_time"]), tzinfo=TZ)
    end = datetime.combine(day, time.fromisoformat(k["close_time"]), tzinfo=TZ)
    while t < end:
        if t > now() + timedelta(minutes=30):
            times.append(t.strftime("%H:%M"))
        t += timedelta(minutes=30)
    if service_code == "surgery":
        times = [x for x in times if x in SURGERY_SLOTS]

    booked = _all(
        "SELECT appt_time, doctor_id, service_code FROM appointments WHERE clinic_id = ? AND appt_date = ? AND status IN ('scheduled','confirmed')",
        (clinic_id, day.isoformat()),
    )
    if service_code == "grooming":
        busy = {b["appt_time"] for b in booked if b["service_code"] == "grooming"}
        return {"slots": {x: ["groomer"] for x in times if x not in busy}, "reason": "fully booked" if times else "no time left today"}

    docs = doctors(clinic_id)
    if species in EXOTIC:
        docs = [d for d in docs if d["speciality"] == "Exotics"]
        if not docs:
            return {"slots": {}, "reason": f"{k['name']} has no exotics doctor"}
    if doctor_name:
        docs = [d for d in docs if _name_match(doctor_name, d["name"])]
        if not docs:
            return {"slots": {}, "reason": f"no doctor called {doctor_name} at this clinic"}
    docs = [d for d in docs if str(day.weekday()) in d["work_weekdays"].split(",") and not doctor_on_leave(d["id"], day.isoformat())]
    if not docs:
        return {"slots": {}, "reason": "the doctor is not working / on leave that day" if doctor_name else "no doctor available that day"}

    busy = {(b["appt_time"], b["doctor_id"]) for b in booked}
    slots = {}
    for x in times:
        names = [d["name"] for d in docs if (x, d["id"]) not in busy]
        if names:
            slots[x] = names
    return {"slots": slots, "reason": "" if slots else "fully booked"}


def _pick_doctor(clinic_id, day: date, hhmm, service_code, species, doctor_name=None) -> tuple[bool, int | None, str]:
    res = free_slots(clinic_id, day, service_code, species)
    if hhmm not in res["slots"]:
        return False, None, res["reason"] or f"{hhmm} is not free"
    if service_code == "grooming":
        return True, None, ""
    names = res["slots"][hhmm]
    if doctor_name:
        names = [n for n in names if _name_match(doctor_name, n)]
        if not names:
            return False, None, f"{doctor_name} is not free at {hhmm}"
    chosen = names[0]
    d = _one("SELECT id FROM doctors WHERE clinic_id = ? AND name = ?", (clinic_id, chosen))
    return True, d["id"], ""


def book(pet_id, clinic_id, service_code, day: date, hhmm, doctor_name=None, home_address=None) -> tuple[int | None, str]:
    p = pet(pet_id)
    if not p or p["is_deceased"]:
        return None, "pet not found or marked deceased"
    ok, doc_id, why = _pick_doctor(clinic_id, day, hhmm, service_code, p["species"], doctor_name)
    if not ok:
        return None, why
    visit = {"home_visit": "home_visit", "video": "video"}.get(service_code, "in_clinic")
    appt_id = _write(
        "INSERT INTO appointments(pet_id, clinic_id, doctor_id, service_code, appt_date, appt_time, status, visit_type, home_address, booked_via, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, 'voice_bot', ?)",
        (pet_id, clinic_id, doc_id, service_code, day.isoformat(), hhmm, visit, home_address, now().isoformat(timespec="seconds")),
    )
    return appt_id, ""


def reschedule(appt_id, day: date, hhmm, doctor_name=None) -> str:
    a = get_appointment(appt_id)
    # free the old slot first so the same doctor/time can be re-picked
    _write("UPDATE appointments SET status = 'rescheduling' WHERE id = ?", (appt_id,))
    ok, doc_id, why = _pick_doctor(a["clinic_id"], day, hhmm, a["service_code"], a["species"], doctor_name)
    if not ok:
        _write("UPDATE appointments SET status = ? WHERE id = ?", (a["status"], appt_id))
        return why
    _write(
        "UPDATE appointments SET appt_date = ?, appt_time = ?, doctor_id = ?, status = 'scheduled', "
        "reschedule_count = reschedule_count + 1, reminder_sent_at = NULL, reminder_outcome = NULL WHERE id = ?",
        (day.isoformat(), hhmm, doc_id, appt_id),
    )
    return ""


def cancel(appt_id: int, reason: str, by: str = "customer") -> None:
    _write("UPDATE appointments SET status = 'cancelled', cancel_reason = ?, cancelled_by = ? WHERE id = ?", (reason, by, appt_id))


def confirm(appt_id: int) -> None:
    _write("UPDATE appointments SET status = 'confirmed', reminder_outcome = 'confirmed' WHERE id = ?", (appt_id,))


def create_ticket(customer_id: int | None, phone: str | None, category: str, summary: str) -> int:
    return _write(
        "INSERT INTO call_tickets(customer_id, phone, category, summary, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
        (customer_id, phone, category, summary, now().isoformat(timespec="seconds")),
    )


def pending_dues(customer_id: int) -> list[dict]:
    """Unpaid invoices for this customer (amount still due)."""
    return _all(
        """SELECT i.amount - i.paid_amount AS due, a.appt_date, s.name AS service, p.name AS pet_name
           FROM invoices i JOIN appointments a ON a.id = i.appointment_id
           JOIN pets p ON p.id = a.pet_id JOIN services s ON s.code = a.service_code
           WHERE p.customer_id = ? AND i.payment_status = 'pending' AND i.amount > i.paid_amount""",
        (customer_id,),
    )


# ---------------------------------------------------------------- reminders

def due_for_reminder() -> list[dict]:
    """Appointments tomorrow or later today that still need a reminder call.
    Skips: already confirmed, already reminded, do-not-call customers, deceased pets."""
    n = now()
    today, tomorrow = n.date(), n.date() + timedelta(days=1)
    return _all(
        APPT_SQL
        + """ WHERE a.status = 'scheduled' AND a.reminder_sent_at IS NULL AND c.do_not_call = 0 AND p.is_deceased = 0
              AND (a.appt_date = ? OR (a.appt_date = ? AND a.appt_time > ?))
              ORDER BY c.phone, a.appt_date, a.appt_time""",
        (tomorrow.isoformat(), today.isoformat(), (n + timedelta(hours=1)).strftime("%H:%M")),
    )


def mark_reminder_sent(appt_ids: list[int]) -> None:
    for i in appt_ids:
        _write("UPDATE appointments SET reminder_sent_at = ? WHERE id = ?", (now().isoformat(timespec="seconds"), i))


def scenario(sid: str) -> dict | None:
    return _one("SELECT * FROM test_scenarios WHERE id = ?", (sid,))
