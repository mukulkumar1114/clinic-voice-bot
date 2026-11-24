# Clinic Voice Bot (fake data only)

A Hinglish voice receptionist for a pet clinic chain:
- **Reminder calls:** a day before or the same day; the customer can confirm, reschedule or cancel.
- **Inbound calls:** book, reschedule, cancel, vaccine due, prices, timings, emergencies, hand-offs to the team.

All data is made up with Faker. Phone numbers start with `1`, so none can reach a real person.
Real calls (phase 2) only ever go to `TEST_CALL_NUMBER` in `.env`.

## Files
| File | What it does |
|---|---|
| `generate_data.py` | Builds `clinic.db`: 6 clinics, 18 doctors, ~1,550 customers, ~2,250 pets, ~4,400 appointments, ~3,000 vaccinations, invoices, and 56 test scenarios. Dates are relative to today, so re-run before each test session. |
| `test_scenarios.csv` | The 56 test cases: what the caller says, and what the bot should do. |
| `db.py` | Booking rules (hours, closed day, doctor leave, surgery 10-12, exotics doctor, 60-day limit...). |
| `agent.py` | The voice bot and its tools. |
| `reminders.py` | Who needs a reminder call (dry run), and starts calls in phase 2. |
| `check_rules.py` | 32 automatic checks of the booking rules against the scenarios (no voice needed). |

## Run
```bash
cd ~/Projects/clinic-voice-bot
.venv/bin/python generate_data.py      # fresh data for today
.venv/bin/python check_rules.py        # should say 32 passed, 0 failed
.venv/bin/python reminders.py          # who would get a reminder call

# Voice test (needs keys in .env): pick any scenario id from test_scenarios.csv
SCENARIO=R03 .venv/bin/python agent.py console
SCENARIO=I12 .venv/bin/python agent.py console
```
The console prints the scenario, a line to say, and what the bot should do.
