"""Check booking rules against the test scenarios (no voice, no API keys needed).

  python generate_data.py && python check_rules.py
"""

from datetime import date, timedelta

import db

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


def sc(i):
    return db.scenario(i)


def cust(i):
    return db.find_customer(sc(i)["caller_phone"])


today = db.now().date()
tom = today + timedelta(days=1)
c1 = db.clinic(1)

print("Reminder selection")
due_ids = {a["id"] for a in db.due_for_reminder()}
check("R01 normal reminder is due", sc("R01")["appointment_id"] in due_ids)
check("R10 do-not-call is skipped", sc("R10")["appointment_id"] not in due_ids)
check("R13 already-confirmed is skipped", sc("R13")["appointment_id"] not in due_ids)
r08 = db.find_customer(sc("R08")["caller_phone"])["id"]
check("R08 two pets -> 2 appointments for one customer", sum(1 for a in db.due_for_reminder() if a["customer_id"] == r08) == 2)
check("R09 doctor on leave is flagged", db.get_appointment(sc("R09")["appointment_id"])["doctor_on_leave"] is True)
check("R11 surgery has fasting note", "No food" in db.get_appointment(sc("R11")["appointment_id"])["prep_note"])
check("No due reminder belongs to a deceased pet", all(a["is_deceased"] == 0 for a in db.due_for_reminder()))
check("No phone number is dialable (all start with 1)", db._one("SELECT COUNT(*) n FROM customers WHERE substr(phone,1,1) != '1'")["n"] == 0)

print("\nSlots and booking rules")
check("I04 clinic 1 full tomorrow 11:00", "11:00" not in db.free_slots(1, tom, "consult")["slots"])
check("I04 but 13:00 still free", "13:00" in db.free_slots(1, tom, "consult")["slots"])
closed = next(today + timedelta(days=k) for k in range(1, 8) if (today + timedelta(days=k)).weekday() == c1["closed_weekday"])
check("I05 closed day has no slots", not db.free_slots(1, closed, "consult")["slots"])
leave = db._one("SELECT d.name, l.leave_date FROM doctor_leaves l JOIN doctors d ON d.id=l.doctor_id WHERE d.clinic_id=1 AND l.reason='conference' ORDER BY l.leave_date LIMIT 1")
r = db.free_slots(1, date.fromisoformat(leave["leave_date"]), "consult", doctor_name=leave["name"])
check("I06 doctor on leave has no slots", not r["slots"], r["reason"])
small = cust("I17")["home_clinic_id"]
check("I17 small clinic can't do surgery", "does not do surgery" in db.free_slots(small, tom + timedelta(days=1), "surgery")["reason"])
check("Surgery only 10-12", set(db.free_slots(1, today + timedelta(days=5), "surgery")["slots"]) <= db.SURGERY_SLOTS)
bird_clinic = cust("I26")["home_clinic_id"]
closed = db.clinic(bird_clinic)["closed_weekday"]
bird_day = next(today + timedelta(days=n) for n in range(2, 9) if (today + timedelta(days=n)).weekday() != closed)  # skip the clinic's closed day
s = db.free_slots(bird_clinic, bird_day, "consult", "bird")
docs = {n for v in s["slots"].values() for n in v}
exotic_docs = {d["name"] for d in db.doctors(bird_clinic) if d["speciality"] == "Exotics"}
check("I26 bird only with Exotics doctor", docs and docs <= exotic_docs, str(docs))
check("Bird at clinic without exotics vet -> refused", not db.free_slots(1, today + timedelta(days=3), "consult", "bird")["slots"])
check("I29 75 days ahead refused", "60 days" in db.free_slots(1, today + timedelta(days=75), "consult")["reason"])
check("Past date refused", not db.free_slots(1, today - timedelta(days=1), "consult")["slots"])
check("Grooming for a bird refused", not db.free_slots(1, tom, "grooming", "bird")["slots"])

print("\nCustomer lookups")
check("I19 found by alternate phone", cust("I19") is not None)
check("I02 new caller not found", db.find_customer("1099999999") is None)
check("I37 customer with no pets", cust("I37")["pets"] == [])
i03 = cust("I03")
check("I03 rabies overdue", any(v["status"] == "overdue" for v in db.vaccines(i03["pets"][0]["id"])))
i31 = cust("I31")
check("I31 deceased pet can't be booked", db.book(i31["pets"][0]["id"], 1, "consult", today + timedelta(days=3), "15:00")[0] is None)
check("I08 customer has 3 upcoming", len(db.customer_appointments(cust("I08")["id"])["upcoming"]) == 3)
check("I09 no-show shows in last 30 days", any(a["status"] == "no_show" for a in db.customer_appointments(cust("I09")["id"])["last_30_days"]))

print("\nBook -> reschedule -> cancel (on a scratch copy of the row)")
p = cust("I01")["pets"][0]["id"]
day = today + timedelta(days=4)
if day.weekday() == c1["closed_weekday"]:
    day += timedelta(days=1)
free = list(db.free_slots(1, day, "vaccination")["slots"])
appt, why = db.book(p, 1, "vaccination", day, free[0])
check("book works", appt is not None, why)
before = len(db.free_slots(1, day, "vaccination")["slots"].get(free[0], []))
why = db.reschedule(appt, day, free[1])
check("reschedule works", why == "", why)
check("reschedule count +1", db.get_appointment(appt)["reschedule_count"] == 1)
check("old slot freed after reschedule", len(db.free_slots(1, day, "vaccination")["slots"].get(free[0], [])) == before + 1)
check("can't book a taken doctor+time", db.book(p, 1, "vaccination", day, "25:00")[0] is None)
db.cancel(appt, "test")
check("cancel works", db.get_appointment(appt)["status"] == "cancelled")
db._write("DELETE FROM appointments WHERE id = ?", (appt,))   # leave data as generated

print(f"\n{ok} passed, {fail} failed")
