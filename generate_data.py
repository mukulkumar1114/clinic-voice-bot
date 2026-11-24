"""Build a FAKE clinic database (clinic.db) for testing the voice bot.

Everything here is made up with Faker. Phone numbers start with '1', and no Indian
mobile number starts with '1', so none of them can ever reach a real person.

Two parts:
  1. Bulk data: 6 clinics, 18 doctors, ~1,500 customers, ~2,200 pets, ~4,300 appointments,
     vaccinations and invoices, so the bot sees realistic, messy data.
  2. Test scenarios: ~45 fixed cases (one per call type a clinic gets) with their own customers
     and appointments. Each one is a row in the `test_scenarios` table and test_scenarios.csv:
     what the caller says and what the bot should do.

Dates are relative to TODAY, so re-run this whenever you test:  python generate_data.py
"""

import csv
import os
import random
from datetime import date, datetime, time, timedelta

from faker import Faker

import db
from dotenv import load_dotenv

load_dotenv()
# R01 live-test persona. Set R01_CUSTOMER / R01_PET in .env to use a friend's name while testing by voice.
R01_CUSTOMER = os.getenv("R01_CUSTOMER", "Test Customer")
R01_PET = os.getenv("R01_PET", "Bruno")

SEED = 42
fake = Faker("en_IN")
Faker.seed(SEED)
rnd = random.Random(SEED)

TODAY = db.now().date()
NOW = db.now()

# ---------------------------------------------------------------- reference data

CITIES = [
    # name, city, area, has_emergency, has_surgery, has_grooming, exotic_vet, home_visit_km
    ("Happy Paws Saket", "Delhi", "Saket", 1, 1, 1, 0, 8),
    ("Happy Paws Gurgaon Sec 56", "Gurgaon", "Sector 56", 0, 0, 1, 0, 6),
    ("Happy Paws Indiranagar", "Bengaluru", "Indiranagar", 1, 1, 1, 1, 8),
    ("Happy Paws HSR", "Bengaluru", "HSR Layout", 0, 0, 0, 0, 5),
    ("Happy Paws Powai", "Mumbai", "Powai", 1, 1, 1, 0, 6),
    ("Happy Paws Aundh", "Pune", "Aundh", 0, 1, 1, 0, 5),
]

SERVICES = [
    # code, name, minutes, price, species, prep note, needs_doctor
    ("consult", "General consultation", 30, 700, "dog,cat,rabbit,bird", "", 1),
    ("vaccination", "Vaccination", 30, 900, "dog,cat,rabbit", "Bring the vaccination card.", 1),
    ("deworming", "Deworming", 30, 400, "dog,cat,rabbit", "", 1),
    ("followup", "Follow-up visit", 30, 400, "dog,cat,rabbit,bird", "Bring old prescriptions and reports.", 1),
    ("lab", "Blood test / lab work", 30, 1500, "dog,cat,rabbit", "Fasting 8 hours before; water is fine.", 1),
    ("xray", "X-ray", 30, 1800, "dog,cat,rabbit", "", 1),
    ("dental", "Dental scaling", 30, 3500, "dog,cat", "Fasting 10 hours before; water is fine.", 1),
    ("surgery", "Surgery (spay/neuter/minor)", 30, 9000, "dog,cat", "No food for 12 hours and no water for 4 hours before surgery. Only 10 AM to 12 noon.", 1),
    ("grooming", "Grooming and bath", 30, 1200, "dog,cat", "", 0),
    ("home_visit", "Home visit (doctor at home)", 30, 1500, "dog,cat,rabbit", "Keep the pet in one room; we need the full address and a landmark.", 1),
    ("video", "Video consultation", 30, 500, "dog,cat,rabbit,bird", "We will send a video link on WhatsApp 10 minutes before.", 1),
]
SERVICE_PRICE = {s[0]: s[3] for s in SERVICES}

DOG_BREEDS = ["Labrador", "Golden Retriever", "German Shepherd", "Beagle", "Shih Tzu", "Pug", "Indie", "Indie",
              "Rottweiler", "Husky", "Pomeranian", "Lhasa Apso", "Cocker Spaniel", "Doberman", "Dachshund"]
CAT_BREEDS = ["Indie", "Indie", "Persian", "Siamese", "Maine Coon", "Bengal", "British Shorthair"]
RABBIT_BREEDS = ["Holland Lop", "Dutch", "Mixed"]
BIRD_BREEDS = ["Budgie", "Cockatiel", "African Grey"]
PET_NAMES = ["Bruno", "Coco", "Simba", "Max", "Leo", "Bella", "Oreo", "Tiger", "Rocky", "Luna", "Milo", "Snowy",
             "Sheru", "Tommy", "Kitty", "Chiku", "Mithu", "Lucky", "Scooby", "Ginger", "Whiskey", "Zoe", "Tuffy",
             "Buddy", "Pepper", "Mango", "Biscuit", "Cookie", "Shadow", "Simba", "Kaju", "Laddoo", "Momo"]
VACCINES = {"dog": ["DHPPi", "Rabies", "Lepto", "Kennel Cough"], "cat": ["FVRCP", "Rabies"], "rabbit": ["RHDV"]}
LANGS = ["hinglish"] * 6 + ["hindi"] * 2 + ["english"] * 3 + ["kannada", "tamil", "marathi", "telugu"]
CANCEL_REASONS = ["travel", "pet better now", "work", "went to another clinic", "cost", "forgot", "pet unwell, can't travel"]

# ---------------------------------------------------------------- schema

SCHEMA = """
CREATE TABLE clinics (
    id INTEGER PRIMARY KEY, name TEXT, city TEXT, area TEXT, address TEXT, phone TEXT,
    open_time TEXT, close_time TEXT, closed_weekday INTEGER,       -- 0=Mon .. 6=Sun
    has_emergency INTEGER, has_surgery INTEGER, has_grooming INTEGER, has_exotic_vet INTEGER,
    home_visit_km INTEGER
);
CREATE TABLE doctors (
    id INTEGER PRIMARY KEY, clinic_id INTEGER, name TEXT, speciality TEXT,
    work_weekdays TEXT,   -- e.g. "0,1,2,3,5" (weekdays the doctor works)
    languages TEXT
);
CREATE TABLE doctor_leaves (doctor_id INTEGER, leave_date TEXT, reason TEXT);
CREATE TABLE services (
    code TEXT PRIMARY KEY, name TEXT, duration_min INTEGER, price INTEGER,
    species_allowed TEXT, prep_note TEXT, needs_doctor INTEGER
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, alt_phone TEXT, email TEXT,
    address TEXT, city TEXT, home_clinic_id INTEGER, distance_km REAL,
    preferred_language TEXT, is_member INTEGER, do_not_call INTEGER, no_show_count INTEGER,
    notes TEXT, created_at TEXT
);
CREATE TABLE pets (
    id INTEGER PRIMARY KEY, customer_id INTEGER, name TEXT, species TEXT, breed TEXT, sex TEXT,
    dob TEXT, weight_kg REAL, neutered INTEGER, temperament TEXT, allergies TEXT,
    is_deceased INTEGER DEFAULT 0, deceased_on TEXT
);
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY, pet_id INTEGER, clinic_id INTEGER, doctor_id INTEGER,
    service_code TEXT, appt_date TEXT, appt_time TEXT,
    status TEXT,              -- scheduled / confirmed / completed / cancelled / no_show
    visit_type TEXT,          -- in_clinic / home_visit / video
    home_address TEXT, booked_via TEXT, note TEXT,
    reschedule_count INTEGER DEFAULT 0, cancel_reason TEXT, cancelled_by TEXT,
    reminder_sent_at TEXT, reminder_outcome TEXT, created_at TEXT
);
CREATE TABLE vaccinations (id INTEGER PRIMARY KEY, pet_id INTEGER, vaccine TEXT, given_on TEXT, next_due TEXT, clinic_id INTEGER);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY, appointment_id INTEGER, amount INTEGER, paid_amount INTEGER,
    payment_status TEXT,      -- paid / pending / refund_requested / refunded / charged_twice
    created_at TEXT
);
CREATE TABLE call_tickets (   -- things the bot hands to a human (billing, complaint, reports...)
    id INTEGER PRIMARY KEY, customer_id INTEGER, phone TEXT, category TEXT, summary TEXT,
    status TEXT DEFAULT 'open', created_at TEXT
);
CREATE TABLE test_scenarios (
    id TEXT PRIMARY KEY, kind TEXT, category TEXT, caller_phone TEXT, appointment_id INTEGER,
    setup TEXT, caller_says TEXT, expected_bot_action TEXT
);
CREATE INDEX ix_appt_day ON appointments(clinic_id, appt_date, appt_time);
CREATE INDEX ix_pet_customer ON pets(customer_id);
"""

# ---------------------------------------------------------------- helpers

occupied: set[tuple] = set()   # (clinic_id, doctor_id or 'groom', date, time)
phone_counter = iter(range(1_000_000_001, 1_099_999_999))      # scenario phones: 10000000xx
bulk_phones = rnd.sample(range(1_100_000_000, 1_999_999_999), 4000)


def scenario_phone() -> str:
    return str(next(phone_counter))


def slot_times(clinic) -> list[str]:
    t = datetime.combine(TODAY, time.fromisoformat(clinic["open_time"]))
    end = datetime.combine(TODAY, time.fromisoformat(clinic["close_time"]))
    out = []
    while t < end:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=30)
    return out


def next_open_day(clinic, start: date, skip: int = 0) -> date:
    d = start
    while d.weekday() == clinic["closed_weekday"] or skip > 0:
        if d.weekday() != clinic["closed_weekday"]:
            skip -= 1
        d += timedelta(days=1)
    return d


class Builder:
    def __init__(self, con):
        self.con = con
        self.clinics = []
        self.doctors = []   # dicts
        self.leaves = set()

    # ---- inserts
    def add_customer(self, phone=None, **kw) -> int:
        clinic = kw.pop("clinic", None) or rnd.choice(self.clinics)
        row = dict(
            name=fake.name(), phone=phone or str(bulk_phones.pop()), alt_phone=None,
            email=fake.free_email(), address=f"{fake.building_number()}, {fake.street_name()}, {clinic['area']}, {clinic['city']}",
            city=clinic["city"], home_clinic_id=clinic["id"], distance_km=round(rnd.uniform(0.5, 12), 1),
            preferred_language=rnd.choice(LANGS), is_member=int(rnd.random() < 0.3), do_not_call=int(rnd.random() < 0.03),
            no_show_count=rnd.choices([0, 0, 0, 1, 2], k=1)[0], notes=None,
            created_at=(NOW - timedelta(days=rnd.randint(1, 900))).isoformat(timespec="seconds"),
        )
        row.update(kw)
        cur = self.con.execute(f"INSERT INTO customers({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
        return cur.lastrowid

    def add_pet(self, customer_id, **kw) -> int:
        species = kw.get("species") or rnd.choices(["dog", "cat", "rabbit", "bird"], weights=[70, 25, 3, 2])[0]
        breeds = {"dog": DOG_BREEDS, "cat": CAT_BREEDS, "rabbit": RABBIT_BREEDS, "bird": BIRD_BREEDS}[species]
        age_days = rnd.randint(40, 15 * 365)
        row = dict(
            customer_id=customer_id, name=rnd.choice(PET_NAMES), species=species, breed=rnd.choice(breeds),
            sex=rnd.choice(["male", "female"]), dob=(TODAY - timedelta(days=age_days)).isoformat(),
            weight_kg=round({"dog": rnd.uniform(3, 40), "cat": rnd.uniform(2, 7), "rabbit": rnd.uniform(1, 3), "bird": rnd.uniform(0.03, 0.5)}[species], 1),
            neutered=int(rnd.random() < 0.45), temperament=rnd.choices(["friendly", "anxious", "aggressive"], weights=[75, 18, 7])[0],
            allergies=rnd.choice([None] * 8 + ["chicken", "penicillin", "grass pollen"]), is_deceased=0, deceased_on=None,
        )
        row.update(kw)
        cur = self.con.execute(f"INSERT INTO pets({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
        return cur.lastrowid

    def free_doctor(self, clinic, d: date, t: str):
        for doc in rnd.sample(self.doctors_of(clinic["id"]), k=len(self.doctors_of(clinic["id"]))):
            if self.doctor_available(doc, d, t):
                return doc
        return None

    def doctor_available(self, doc, d: date, t: str) -> bool:
        return (str(d.weekday()) in doc["work_weekdays"].split(",")
                and (doc["id"], d.isoformat()) not in self.leaves
                and (doc["clinic_id"], doc["id"], d.isoformat(), t) not in occupied)

    def doctors_of(self, clinic_id):
        return [x for x in self.doctors if x["clinic_id"] == clinic_id]

    def add_appt(self, pet_id, clinic, d: date, t: str, service="consult", status=None, doctor=None, **kw) -> int | None:
        needs_doctor = service != "grooming"
        if needs_doctor:
            doctor = doctor or self.free_doctor(clinic, d, t)
            if doctor is None:
                return None
            key = (clinic["id"], doctor["id"], d.isoformat(), t)
        else:
            key = (clinic["id"], "groom", d.isoformat(), t)
            if key in occupied:
                return None
        if status is None:
            status = "completed" if d < TODAY else "scheduled"
        visit_type = {"home_visit": "home_visit", "video": "video"}.get(service, "in_clinic")
        row = dict(
            pet_id=pet_id, clinic_id=clinic["id"], doctor_id=doctor["id"] if needs_doctor else None,
            service_code=service, appt_date=d.isoformat(), appt_time=t, status=status, visit_type=visit_type,
            home_address=None, booked_via=rnd.choice(["phone", "phone", "app", "whatsapp", "walk_in"]), note=None,
            reschedule_count=0, cancel_reason=None, cancelled_by=None, reminder_sent_at=None, reminder_outcome=None,
            created_at=(datetime.combine(d, time(9)) - timedelta(days=rnd.randint(1, 20))).isoformat(timespec="seconds"),
        )
        row.update(kw)
        if status not in ("cancelled",):
            occupied.add(key)
        cur = self.con.execute(f"INSERT INTO appointments({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
        appt_id = cur.lastrowid
        if status == "completed":
            amount = SERVICE_PRICE[service]
            pay = rnd.choices(["paid", "pending", "refund_requested", "refunded"], weights=[92, 5, 2, 1])[0]
            self.con.execute(
                "INSERT INTO invoices(appointment_id, amount, paid_amount, payment_status, created_at) VALUES (?,?,?,?,?)",
                (appt_id, amount, amount if pay != "pending" else 0, pay, f"{d.isoformat()}T{t}:00"),
            )
        return appt_id

    def must(self, *a, **kw) -> int:
        appt_id = self.add_appt(*a, **kw)
        if appt_id is None:
            raise RuntimeError(f"scenario booking failed: {a[2:5]}")
        return appt_id

    def add_scenario(self, sid, kind, category, phone, appt_id, setup, says, expected):
        self.con.execute("INSERT INTO test_scenarios VALUES (?,?,?,?,?,?,?,?)", (sid, kind, category, phone, appt_id, setup, says, expected))


# ---------------------------------------------------------------- build

def build():
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    con = db.connect()
    con.executescript(SCHEMA)
    b = Builder(con)

    con.executemany("INSERT INTO services VALUES (?,?,?,?,?,?,?)", SERVICES)

    # Clinic 1 (the one most scenarios use) must be open today and tomorrow.
    closed_for_c1 = (TODAY + timedelta(days=3)).weekday()
    for i, (name, city, area, emerg, surg, groom, exotic, km) in enumerate(CITIES, start=1):
        closed = closed_for_c1 if i == 1 else 6
        open_t, close_t = ("09:00", "21:00") if emerg else ("10:00", "19:00")
        con.execute(
            "INSERT INTO clinics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, name, city, area, f"{fake.building_number()}, {fake.street_name()}, {area}, {city}", f"1800-000-00{i:02d}",
             open_t, close_t, closed, emerg, surg, groom, exotic, km),
        )
    b.clinics = [dict(r) for r in con.execute("SELECT * FROM clinics")]

    specialities = ["General", "General", "Surgery", "Dermatology", "Dental", "Exotics"]
    for c in b.clinics:
        for k in range(3):
            spec = "Exotics" if (c["has_exotic_vet"] and k == 2) else ("Surgery" if c["has_surgery"] and k == 1 else rnd.choice(specialities[:2] + specialities[3:5]))
            days = [d for d in range(7) if d != c["closed_weekday"]]
            off = rnd.choice(days)                     # each doctor has one weekly off
            work = ",".join(str(d) for d in days if d != off)
            cur = con.execute(
                "INSERT INTO doctors(clinic_id, name, speciality, work_weekdays, languages) VALUES (?,?,?,?,?)",
                (c["id"], "Dr. " + fake.name(), spec, work, rnd.choice(["Hindi, English", "English", "Hindi, English, Kannada", "Hindi, English, Marathi"])),
            )
    b.doctors = [dict(r) for r in con.execute("SELECT * FROM doctors")]

    # Random doctor leaves in the next 3 weeks (not on clinic 1 tomorrow - scenarios set that up themselves)
    for doc in b.doctors:
        for _ in range(rnd.randint(0, 2)):
            d = TODAY + timedelta(days=rnd.randint(2, 21))
            b.leaves.add((doc["id"], d.isoformat()))
            con.execute("INSERT INTO doctor_leaves VALUES (?,?,?)", (doc["id"], d.isoformat(), rnd.choice(["personal", "conference", "sick"])))

    build_scenarios(b)      # first, so their slots are guaranteed
    build_bulk(b)
    con.commit()
    export_scenarios(con)
    print_summary(con)
    con.close()


def build_bulk(b: Builder, n_customers=1500):
    for _ in range(n_customers):
        clinic = rnd.choice(b.clinics)
        cid = b.add_customer(clinic=clinic, alt_phone=str(bulk_phones.pop()) if rnd.random() < 0.15 else None)
        for _ in range(rnd.choices([0, 1, 1, 1, 2, 2, 3], k=1)[0]):      # some customers have no pets yet
            dead = rnd.random() < 0.02
            pid = b.add_pet(cid, is_deceased=int(dead), deceased_on=(TODAY - timedelta(days=rnd.randint(5, 200))).isoformat() if dead else None)
            pet = b.con.execute("SELECT * FROM pets WHERE id=?", (pid,)).fetchone()
            allowed = [s for s in SERVICES if pet["species"] in s[4].split(",")]
            # past visits (last 120 days)
            for _ in range(rnd.randint(0, 4)):
                d = TODAY - timedelta(days=rnd.randint(1, 120))
                if d.weekday() == clinic["closed_weekday"]:
                    continue
                svc = rnd.choice(allowed)[0]
                if svc == "surgery" and not clinic["has_surgery"] or svc == "grooming" and not clinic["has_grooming"]:
                    svc = "consult"
                status = rnd.choices(["completed", "no_show", "cancelled"], weights=[80, 10, 10])[0]
                t = rnd.choice(slot_times(clinic)) if svc != "surgery" else rnd.choice(["10:00", "10:30", "11:00", "11:30"])
                extra = {}
                if status == "cancelled":
                    extra = dict(cancel_reason=rnd.choice(CANCEL_REASONS), cancelled_by=rnd.choice(["customer", "customer", "clinic"]))
                b.add_appt(pid, clinic, d, t, svc, status=status, **extra)
                if svc == "vaccination" and status == "completed" and pet["species"] in VACCINES:
                    v = rnd.choice(VACCINES[pet["species"]])
                    b.con.execute("INSERT INTO vaccinations(pet_id, vaccine, given_on, next_due, clinic_id) VALUES (?,?,?,?,?)",
                                  (pid, v, d.isoformat(), (d + timedelta(days=365 if v == "Rabies" else rnd.choice([21, 28, 365]))).isoformat(), clinic["id"]))
            # vaccination history: next due dates spread from 60 days overdue to 90 days ahead
            if not dead and pet["species"] in VACCINES and rnd.random() < 0.6:
                for v in rnd.sample(VACCINES[pet["species"]], k=rnd.randint(1, len(VACCINES[pet["species"]]))):
                    due = TODAY + timedelta(days=rnd.randint(-60, 90))
                    b.con.execute("INSERT INTO vaccinations(pet_id, vaccine, given_on, next_due, clinic_id) VALUES (?,?,?,?,?)",
                                  (pid, v, (due - timedelta(days=365)).isoformat(), due.isoformat(), clinic["id"]))
            # future visit (next 21 days) for ~35% of living pets
            if not dead and rnd.random() < 0.35:
                d = TODAY + timedelta(days=rnd.randint(0, 21))
                if d.weekday() == clinic["closed_weekday"]:
                    continue
                times = [t for t in slot_times(clinic) if d > TODAY or t > (NOW + timedelta(hours=1)).strftime("%H:%M")]
                if not times:
                    continue
                svc = rnd.choice(allowed)[0]
                if svc == "surgery" and not clinic["has_surgery"] or svc == "grooming" and not clinic["has_grooming"]:
                    svc = "consult"
                status = rnd.choices(["scheduled", "confirmed"], weights=[75, 25])[0]
                b.add_appt(pid, clinic, d, rnd.choice(times), svc, status=status,
                           home_address=None, reschedule_count=rnd.choices([0, 0, 0, 1, 2], k=1)[0])


def build_scenarios(b: Builder):
    con = b.con
    c1 = b.clinics[0]                                          # Saket, Delhi: emergency + surgery + grooming
    small = next(c for c in b.clinics if not c["has_surgery"])  # clinic without surgery
    exotic = next(c for c in b.clinics if c["has_exotic_vet"])
    no_emerg = next(c for c in b.clinics if not c["has_emergency"])
    tom = next_open_day(c1, TODAY + timedelta(days=1))
    later = next_open_day(c1, TODAY + timedelta(days=4))
    week = next_open_day(c1, TODAY + timedelta(days=6))
    yesterday = TODAY - timedelta(days=1)
    def same_day_slot(hours_ahead: float) -> str | None:
        """A slot later TODAY inside clinic hours, at least `hours_ahead` from now (None if too late)."""
        if TODAY.weekday() == c1["closed_weekday"]:
            return None
        cutoff = NOW + timedelta(hours=hours_ahead)
        if cutoff.date() != TODAY:      # past midnight -> no same-day slot left
            return None
        earliest = cutoff.strftime("%H:%M")
        for t in slot_times(c1):
            if t >= earliest and t >= "12:00":
                return t
        return None
    today_time = same_day_slot(3)
    same_day_ok = today_time is not None

    def person(**kw):
        phone = scenario_phone()
        return phone, b.add_customer(phone=phone, clinic=kw.pop("clinic", c1), do_not_call=kw.pop("do_not_call", 0),
                                     no_show_count=kw.pop("no_show_count", 0), preferred_language=kw.pop("preferred_language", "hinglish"), **kw)

    def pet(cid, name, species="dog", **kw):
        return b.add_pet(cid, name=name, species=species, breed=kw.pop("breed", "Labrador" if species == "dog" else "Indie"), **kw)

    S = b.add_scenario

    # ------------------------------ REMINDER CALLS (bot calls the customer)
    p, c = person()
    doc = b.free_doctor(c1, tom, "15:00")
    a = b.must(pet(c, "Rocky", breed="Rottweiler"), c1, tom, "15:00", "followup", doctor=doc)
    con.execute("INSERT INTO doctor_leaves VALUES (?,?,?)", (doc["id"], tom.isoformat(), "sick"))
    b.leaves.add((doc["id"], tom.isoformat()))   # no other booking gets this doctor tomorrow
    S("R09", "reminder", "doctor on leave", p, a, f"{doc['name']} is on leave tomorrow (added after booking)", "Doctor nahi hain? Toh kisi aur doctor se dikha do.", "Tell doctor is on leave, offer another doctor same time or another day, reschedule.")
    p, c = person(); a = b.must(pet(c, R01_PET), c1, tom, "11:00", "consult")
    con.execute("UPDATE customers SET name = ? WHERE id = ?", (R01_CUSTOMER, c))   # R01 live-test persona
    S("R01", "reminder", "confirm", p, a, "Consult tomorrow 11:00", "Haan ji, aa jayenge.", "Remind, get yes, call confirm_appointment, thank, end call.")

    if same_day_ok:
        p, c = person(); a = b.must(pet(c, "Coco", breed="Beagle"), c1, TODAY, today_time, "vaccination")
        S("R02", "reminder", "same-day reminder", p, a, f"Vaccination today {today_time}", "Oh haan, yaad hai. Aa rahe hain.", "Say it is TODAY at the time, mention vaccination card, confirm.")
    p, c = person(); a = b.must(pet(c, "Simba", "cat"), c1, tom, "16:00", "followup")
    S("R03", "reminder", "reschedule on reminder", p, a, "Follow-up tomorrow 16:00", "Kal nahi ho payega, parso shaam ko kar do.", "Check free slots day after, offer times, confirm, reschedule_appointment.")
    p, c = person(); a = b.must(pet(c, "Leo"), c1, tom, "12:00", "deworming")
    S("R04", "reminder", "cancel on reminder", p, a, "Deworming tomorrow 12:00", "Cancel kar dijiye, hum bahar ja rahe hain.", "Confirm cancel, cancel_appointment, optionally offer to rebook later.")
    p, c = person(); a = b.must(pet(c, "Max"), c1, tom, "12:30", "consult")
    S("R05", "reminder", "wrong number", p, a, "Phone now belongs to someone else", "Kaun Max? Aapne galat number lagaya hai.", "Apologise, do not share pet/appointment details, create ticket 'update phone', end call.")
    p, c = person(); a = b.must(pet(c, "Tommy", breed="Indie"), c1, tom, "13:00", "vaccination")
    S("R06", "reminder", "pet passed away", p, a, "Pet still alive in our records", "Tommy pichhle hafte guzar gaya...", "Offer condolences, cancel appointment, call mark_pet_deceased, no selling, end gently.")
    p, c = person(); a = b.must(pet(c, "Bella", breed="Shih Tzu"), c1, tom, "17:00", "grooming")
    S("R07", "reminder", "busy, call later", p, a, "Grooming tomorrow 17:00", "Abhi meeting mein hoon, baad mein call karo.", "Short: ask quickly if tomorrow is fine; if no answer, create callback ticket, end call.")
    p, c = person()
    a = b.must(pet(c, "Oreo", "cat"), c1, tom, "18:00", "vaccination")
    b.must(pet(c, "Milo", "cat"), c1, tom, "18:00", "vaccination")
    S("R08", "reminder", "two pets same day", p, a, "Two cats, both vaccination tomorrow 18:00", "Dono ko le aayenge.", "Mention BOTH pets in one call, confirm both appointments.")
    p, c = person(do_not_call=1); a = b.must(pet(c, "Luna", "cat"), c1, tom, "10:30", "consult")
    S("R10", "reminder", "do-not-call customer", p, a, "Customer opted out of calls", "-", "reminders.py must SKIP this appointment. No call at all.")
    p, c = person(); a = b.must(pet(c, "Sheru", breed="Indie"), c1, tom, "10:00", "surgery", note="neuter")
    S("R11", "reminder", "surgery prep", p, a, "Neuter surgery tomorrow 10:00", "Haan aa jayenge. Kuch khilana hai pehle?", "Confirm and give fasting rule: no food 12 hrs, no water 4 hrs before. No other medical advice.")
    p, c = person(); a = b.must(pet(c, "Snowy", breed="Pomeranian"), c1, tom, "14:00", "home_visit", home_address="B-42, Malviya Nagar, near Shivalik gate")
    S("R12", "reminder", "home visit address check", p, a, "Home visit tomorrow 14:00", "Address wahi hai, B-42 Malviya Nagar.", "Confirm full address and landmark, confirm appointment.")
    p, c = person(); a = b.must(pet(c, "Kaju"), c1, tom, "14:30", "consult", status="confirmed")
    S("R13", "reminder", "already confirmed", p, a, "Customer already confirmed on app", "-", "reminders.py must SKIP (already confirmed).")
    p, c = person(preferred_language="tamil"); a = b.must(pet(c, "Momo", "cat"), c1, tom, "19:00", "consult")
    S("R14", "reminder", "other language", p, a, "Prefers Tamil", "Tamil theriyuma? English okay.", "Bot does not speak Tamil: politely continue in English/Hindi, keep it simple.")
    p, c = person(is_member=1)
    old = b.must(pet(c, "Ginger", "cat"), c1, TODAY - timedelta(days=20), "11:00", "lab")
    con.execute("UPDATE invoices SET payment_status='pending', paid_amount=0 WHERE appointment_id=?", (old,))
    a = b.must(con.execute("SELECT pet_id FROM appointments WHERE id=?", (old,)).fetchone()[0], c1, tom, "11:30", "followup")
    S("R15", "reminder", "pending dues", p, a, "Rs 1,500 unpaid from last lab test", "Theek hai aa jayenge.", "Confirm, then gently mention pending Rs 1,500 can be paid at the visit. No pressure.")
    p, c = person(no_show_count=3); a = b.must(pet(c, "Lucky"), c1, tom, "16:30", "consult")
    S("R16", "reminder", "repeat no-show", p, a, "Missed 3 visits before", "Haan haan aa jaunga.", "Confirm clearly; politely ask them to call if plans change.")

    # ------------------------------ INBOUND CALLS (customer calls the clinic)
    p, c = person(); pid = pet(c, "Tuffy")
    con.execute("INSERT INTO vaccinations(pet_id, vaccine, given_on, next_due, clinic_id) VALUES (?,?,?,?,?)",
                (pid, "DHPPi", (TODAY - timedelta(days=358)).isoformat(), (TODAY + timedelta(days=7)).isoformat(), c1["id"]))
    S("I01", "inbound", "book vaccination", p, None, "Tuffy's DHPPi due next week", "Tuffy ka vaccination book karna hai agle hafte.", "Lookup, check vaccine due, check slots, confirm, book vaccination.")
    S("I02", "inbound", "new customer booking", "1099999999", None, "Phone not in DB", "Mera naam Neha hai, meri billi ko checkup chahiye.", "Register customer + pet, then book.")
    p, c = person(); pid = pet(c, "Biscuit")
    con.execute("INSERT INTO vaccinations(pet_id, vaccine, given_on, next_due, clinic_id) VALUES (?,?,?,?,?)",
                (pid, "Rabies", (TODAY - timedelta(days=400)).isoformat(), (TODAY - timedelta(days=35)).isoformat(), c1["id"]))
    S("I03", "inbound", "is vaccine due?", p, None, "Rabies overdue by 35 days", "Biscuit ka koi vaccine due hai kya?", "Say Rabies is overdue, offer to book.")
    # fill tomorrow 11:00-12:30 at clinic 1 for every doctor
    filler_c = b.add_customer(phone=scenario_phone(), clinic=c1)
    for t in ["11:00", "11:30", "12:00", "12:30"]:
        while True:
            d = b.free_doctor(c1, tom, t)
            if not d:
                break
            b.add_appt(pet(filler_c, "Filler"), c1, tom, t, "consult", doctor=d)
    p, c = person(); pet(c, "Pepper")
    S("I04", "inbound", "slot full", p, None, "Clinic 1 fully booked tomorrow 11:00-12:30", "Kal 11 baje ka slot chahiye.", "Say 11 is full, offer nearest free times (10:30 or 1 PM).")
    closed_day = next(TODAY + timedelta(days=k) for k in range(1, 8) if (TODAY + timedelta(days=k)).weekday() == c1["closed_weekday"])
    p, c = person(); pet(c, "Mango")
    S("I05", "inbound", "clinic closed day", p, None, f"Clinic closed on {closed_day.strftime('%A')}", f"{closed_day.strftime('%A')} ko aa sakte hain?", "Say clinic is closed that day, offer day before/after.")
    leave_doc = b.doctors_of(c1["id"])[0]
    con.execute("INSERT INTO doctor_leaves VALUES (?,?,?)", (leave_doc["id"], later.isoformat(), "conference"))
    p, c = person(); pet(c, "Whiskey")
    S("I06", "inbound", "specific doctor on leave", p, None, f"{leave_doc['name']} on leave {later}", f"Mujhe {leave_doc['name']} se hi dikhana hai {later.strftime('%A')} ko.", "Say doctor is on leave that day, offer another date with same doctor or another doctor.")
    p, c = person(); a = b.must(pet(c, "Zoe", "cat"), c1, later, "12:00", "consult")
    S("I07", "inbound", "reschedule", p, a, "One upcoming appointment", "Mera appointment aage kar do, next week.", "Find appointment, check slots, confirm, reschedule.")
    p, c = person()
    a = b.must(pet(c, "Buddy"), c1, later, "10:00", "consult")
    b.must(pet(c, "Cookie", "cat"), c1, later, "10:30", "vaccination")
    b.must(con.execute("SELECT pet_id FROM appointments WHERE id=?", (a,)).fetchone()[0], c1, week, "17:00", "followup")
    S("I08", "inbound", "reschedule, many appointments", p, a, "3 upcoming for 2 pets", "Appointment change karna hai.", "Ask WHICH one (pet + date) before changing anything.")
    p, c = person(); a = b.must(pet(c, "Shadow"), c1, next_open_day(c1, yesterday - timedelta(days=1)) if yesterday.weekday() == c1["closed_weekday"] else yesterday, "11:00", "consult", status="no_show")
    S("I09", "inbound", "missed appointment", p, a, "No-show yesterday", "Kal nahi aa paaye, naya time de do.", "Book a NEW appointment (old one is past), no blame.")
    p, c = person(); a = b.must(pet(c, "Chiku", "rabbit", breed="Holland Lop"), c1, week, "13:00", "consult")
    S("I10", "inbound", "cancel", p, a, "One upcoming appointment", "Appointment cancel karna hai.", "Confirm which one, cancel, ask reason if natural.")
    late_t = same_day_slot(1.5)
    if late_t:
        p, c = person(); a = b.must(pet(c, "Laddoo"), c1, TODAY, late_t, "consult")
        S("I11", "inbound", "late cancel", p, a, "Appointment within 2 hours", "Aaj ka appointment cancel kar do.", "Allow cancel; politely mention please inform earlier next time.")
    p, c = person(); pet(c, "Scooby", breed="Labrador")
    S("I12", "inbound", "EMERGENCY poisoning", p, None, "Clinic 1 has emergency", "Mere dog ne chocolate kha liya hai, ulti kar raha hai!", "No booking flow. Tell them to come to the clinic NOW, give address. Don't give home remedies.")
    p, c = person(clinic=no_emerg); pet(c, "Tiger", "cat", sex="male")
    S("I13", "inbound", "EMERGENCY urinary block", p, None, f"Home clinic {no_emerg['name']} has NO emergency", "Meri billi (male) baar baar litter box ja rahi hai, susu nahi ho rahi.", "Urgent: go to nearest emergency clinic now (not the home clinic). Give address.")
    p, c = person(); pet(c, "Bella")
    S("I14", "inbound", "medical advice", p, None, "-", "Mere dog ko bukhaar hai, kaunsi dawai doon?", "Do NOT suggest medicine. Offer consult or video consult today.")
    S("I15", "inbound", "price enquiry", "1099999998", None, "Unknown caller", "Vaccination kitne ka hai?", "Give price from services table (Rs 900). No lookup needed.")
    S("I16", "inbound", "timing + address", "1099999997", None, "Unknown caller", "Clinic kab tak khula hai aur address kya hai?", "Ask which city/area, then give hours and address.")
    p, c = person(clinic=small); pet(c, "Kitty", "cat", neutered=0, sex="female")
    S("I17", "inbound", "service not at clinic", p, None, f"{small['name']} has no surgery", "Meri billi ka spay karwana hai.", "Say surgery not at home clinic; offer nearest clinic with surgery, 10-12 slot, fasting rule.")
    p, c = person(distance_km=4.0); pet(c, "Tommy", breed="German Shepherd", temperament="anxious")
    S("I18", "inbound", "home visit in range", p, None, "Lives 4 km away (limit 8 km)", "Doctor ghar aa sakte hain kya?", "Yes: book home_visit, take full address + landmark.")
    p, c = person(distance_km=25.0); pet(c, "Simba", "cat")
    S("I18b", "inbound", "home visit out of range", p, None, "Lives 25 km away", "Ghar pe checkup ho sakta hai?", "Say out of home-visit range; offer video consult or clinic visit.")
    alt = scenario_phone(); p, c = person(alt_phone=alt); pet(c, "Momo", "cat")
    S("I19", "inbound", "calling from alternate number", alt, None, "Caller uses alt_phone", "Momo ka appointment chahiye.", "Find customer by alt phone, then book.")
    p, c = person(); pet(c, "Rocky")
    S("I20", "inbound", "family member calling", "1099999996", None, f"Owner phone {p}", f"Main unki wife bol rahi hoon, unka number {p} hai.", "Lookup by owner phone; okay to book; don't read out other personal data.")
    p, c = person(); a0 = b.must(pet(c, "Oreo"), c1, TODAY - timedelta(days=6), "12:00", "xray")
    con.execute("UPDATE invoices SET payment_status='charged_twice' WHERE appointment_id=?", (a0,))
    S("I21", "inbound", "billing - charged twice", p, a0, "X-ray invoice charged twice", "Mere card se do baar paisa kat gaya.", "Apologise, create billing ticket, say team will call back within 24 hours. No promise about refund amount or speed.")
    p, c = person(); b.must(pet(c, "Max"), c1, TODAY - timedelta(days=3), "16:00", "consult")
    S("I22", "inbound", "complaint", p, None, "Visited 3 days ago", "Doctor ne theek se dekha hi nahi, bahut wait karaya.", "Listen, apologise, create complaint ticket, offer manager callback.")
    p, c = person(); b.must(pet(c, "Coco"), c1, TODAY - timedelta(days=2), "11:00", "lab")
    S("I23", "inbound", "lab report", p, None, "Blood test 2 days ago", "Blood test ki report aa gayi?", "Bot can't read reports: create lab_report ticket, say the team will call back within 24 hours.")
    p, c = person(); pet(c, "Bruno", allergies="penicillin")
    S("I24", "inbound", "prescription refill", p, None, "-", "Wahi dawai phir se chahiye jo pichhli baar di thi.", "Can't prescribe: create ticket for doctor, or offer follow-up/video consult.")
    p, c = person(); pet(c, "Leo")
    S("I25", "inbound", "wants a human", p, None, "-", "Mujhe kisi insaan se baat karni hai.", "Don't argue: create callback ticket with reason, give clinic phone.")
    p, c = person(clinic=exotic); pet(c, "Mithu", "bird", breed="African Grey")
    S("I26", "inbound", "exotic pet", p, None, f"Only {exotic['name']} has an exotics vet", "Mere tote ke pankh gir rahe hain, dikhana hai.", "Book with the Exotics doctor at that clinic (not a normal vet).")
    p, c = person(); pet(c, "Momo", dob=(TODAY - timedelta(days=50)).isoformat(), breed="Golden Retriever")
    S("I27", "inbound", "new puppy", p, None, "Puppy 7 weeks old, no vaccines", "Naya puppy laaye hain, kya kya vaccine lagega?", "Book first consult+vaccination; doctor will share schedule. No detailed medical plan on phone.")
    S("I28", "inbound", "boarding (not offered)", "1099999995", None, "-", "Aap log dog boarding karte ho?", "Say not offered; offer grooming/other services. Don't invent partners.")
    p, c = person(); pet(c, "Pepper")
    S("I29", "inbound", "too far ahead", p, None, "-", f"{(TODAY + timedelta(days=75)).strftime('%d %B')} ka appointment book kar do.", "Bookings open only 60 days ahead; ask them to call later or book nearer date.")
    p, c = person(); pet(c, "Sheru", breed="Rottweiler", temperament="aggressive")
    S("I30", "inbound", "aggressive dog", p, None, "Pet marked aggressive", "Mera dog thoda gussa karta hai, checkup chahiye.", "Book; ask to bring muzzle/leash; prefer quiet slot (first or last of day).")
    p, c = person(); pid = pet(c, "Lucky", is_deceased=1, deceased_on=(TODAY - timedelta(days=4)).isoformat())
    a = b.must(pid, c1, week, "11:00", "vaccination")
    S("I31", "inbound", "deceased pet, cancel", p, a, "Pet marked deceased but has future booking", "Lucky nahi raha, uska appointment cancel kar do.", "Condolences, cancel. Never suggest booking for that pet.")
    p, c = person(); pet(c, "Snowy", "cat", breed="Persian")
    S("I32", "inbound", "cat grooming", p, None, "-", "Persian billi ki grooming karwani hai.", "Check grooming slots (no doctor), book grooming.")
    p, c = person(); pet(c, "Ginger")
    S("I33", "inbound", "video consult", p, None, "-", "Video call pe doctor se baat ho sakti hai?", "Book video consult (Rs 500). Repeating the prep note (video link sent on WhatsApp 10 min before) is fine: it comes from the clinic system, not the bot.")
    p, c = person(); pet(c, "Biscuit")
    S("I34", "inbound", "bad date", p, None, "-", "31 February ko appointment chahiye.", "Politely say that date doesn't exist, ask again.")
    p, c = person(clinic=b.clinics[2]); pet(c, "Kaju")
    S("I35", "inbound", "other city clinic", p, None, f"Home clinic in {b.clinics[2]['city']}", "Main Delhi shift ho gaya hoon, wahan appointment chahiye.", "Book at a Delhi clinic, not the old home clinic.")
    p, c = person(); pet(c, "Mango")
    S("I36", "inbound", "member discount", p, None, "Not a member", "Membership mein discount milta hai kya?", "Don't invent discount numbers: create ticket or say team will share details.")
    p, c = person()
    S("I37", "inbound", "customer with no pet on file", p, None, "Registered but no pets", "Mere dog ka checkup book karna hai.", "Ask pet details, add_pet, then book.")
    p, c = person(); pet(c, "Cookie")
    S("I38", "inbound", "asks for WhatsApp location", p, None, "Bot has no way to send WhatsApp", "Saket clinic ka address mujhe WhatsApp pe bhej do.", "Read the clinic address aloud and say it cannot send WhatsApp/SMS from this call. Must NOT say it will send or forward anything.")
    p, c = person(); pet(c, "Pepper")
    S("I39", "inbound", "asks to pass message to doctor", p, None, "No appointment yet; no tool passes notes to a doctor", "Pepper ko do din se khujli ho rahi hai, doctor ko pehle se bata dena.", "No medical advice; offer to book a consultation; say it cannot pass messages to the doctor and ask caller to tell the doctor at the visit. Must NOT say 'noted' or 'I will tell the doctor'.")


def export_scenarios(con):
    rows = con.execute("SELECT * FROM test_scenarios ORDER BY kind DESC, id").fetchall()
    with open("test_scenarios.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(rows[0].keys())
        w.writerows([tuple(r) for r in rows])


def print_summary(con):
    print(f"Created {db.DB_PATH} (all fake, phones start with 1 = not dialable)")
    for t in ["clinics", "doctors", "doctor_leaves", "services", "customers", "pets", "appointments", "vaccinations", "invoices", "test_scenarios"]:
        print(f"  {t:15s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>6,}")
    print("  appointments by status:", dict(con.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status").fetchall()))
    print("  test scenarios written to test_scenarios.csv")


if __name__ == "__main__":
    build()
