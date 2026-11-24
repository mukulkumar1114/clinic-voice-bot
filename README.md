# Clinic Voice Bot

A Hinglish voice receptionist for a pet-clinic chain. It makes **reminder calls** (confirm, reschedule or cancel tomorrow's appointment) and answers **inbound calls** (book, reschedule, cancel, vaccine due, prices, timings, emergencies, hand-off to the human team).

**Fake data only.** Every customer, pet, doctor and appointment is generated with Faker. Phone numbers start with `1`, so none can reach a real person. Real phone calls (not built yet) would only ever go to one test number set in `.env`.

> Demo video: _(coming soon)_

## How it works

```
caller (mic or phone)
   |  audio
   v
speech-to-text (Deepgram nova-3) -> LLM "Asha" (Gemini 3 Flash) -> text-to-speech (Cartesia Sonic-3)
                                        |
                                        +-- tools: look up caller, check free slots, book, reschedule,
                                                   cancel, register, add pet, create team ticket, end call
                                        +-- db.py: all booking rules live in code, not in the prompt
```

- **Stack:** Python 3.13, [LiveKit Agents](https://docs.livekit.io/agents/) 1.8, LiveKit Inference (Deepgram, Gemini, Cartesia), Silero VAD, SQLite.
- **Rules in code, wording in the prompt.** Opening hours, closed days, doctor leave, one pet per doctor-slot, surgery only 10-12 and only at surgery clinics, exotics only with the exotics doctor, 60-day booking window, 30-minute notice. The bot cannot book something `db.py` refuses.
- **Caller is looked up in code before the call starts**, and the bot is locked to that identity, so it cannot read or change another customer's data.

## How it was tested

- **56 call scenarios** in `test_scenarios.csv` (16 reminder, 40 inbound): rescheduling, doctor on leave, closed days, emergencies, deceased pets, wrong person on the line, billing complaints, dates out of range, and more.
- **Automated runner (`run_all.py`):** an AI caller plays the scenario against the bot, and a separate AI judge (a different model from the bot) marks pass or fail against the expected behaviour.
- **32 code-level rule checks (`check_rules.py`)** that need no voice or AI.
- **Real-voice tests** from a browser microphone, with the per-turn timings and a transcript saved for each call.
- **The judge is not trusted blindly.** It was sometimes too lenient and sometimes wrong, so every failing transcript and a sample of passing ones were read by hand.

## What testing found (and what changed)

| Problem found | Fix |
|---|---|
| Bot skipped the caller lookup and re-registered an existing customer | Lookup happens in code before the call; identity lock on every tool |
| Bot offered times before checking free slots | Rule: check slots before offering any time or doctor |
| Bot said "booked" after a tool call had failed | Rule: never claim success unless the tool result says so |
| Bot heard "3 February" and booked 3 December | Today's date and last bookable date in the prompt; bot must flag any date mismatch |
| Bot said yes to a home visit before checking distance | Rule plus a code guard in the booking tool |
| Bot promised to "send the address on WhatsApp" and to "note this for the doctor", with no way to do either | Prompt lists what the bot cannot do and the exact phrases it must not say; new test scenarios for both; judge fails any promise no tool backed up. The first version of the rule still failed one test, and a stronger version passed |

## Known limits

- **Latency.** From the caller stopping to the bot speaking: about 2 to 3 seconds for a plain reply and 3.5 to 4.5 seconds when a tool is called. The LLM's first word (about 1.5 seconds) is the main cost; text-to-speech starts in 0.1 to 0.2 seconds. A person answers in about 1 second.
- **Speech recognition on Indian-accent Hinglish** was the weakest part (several turns per call misheard) with the automatic language mode. Hindi mode plus a word list of names is the current attempt.
- **Opening line is long** (about 16 seconds of speech).
- **No phone line yet.** Calls run from a laptop mic or a browser page. Connecting a real phone number (SIP trunk) is the next phase.

## Files

| File | What it does |
|---|---|
| `agent.py` | The voice bot: prompt, rules, tools, call logging |
| `db.py` | Booking rules and database helpers |
| `generate_data.py` | Builds `clinic.db` with fake clinics, doctors, customers, pets, appointments, vaccinations and the 56 scenarios. Dates are relative to today, so re-run it each day |
| `test_scenarios.csv` | The 56 test cases: what the caller says, what the bot should do |
| `reminders.py` | Which customers need a reminder call (dry run) |
| `check_rules.py` | 32 automatic rule checks |
| `run_all.py`, `text_test.py` | Text-based test runner with an AI caller and judge |
| `web_test.py` | Local browser page for a mic test (listens on your machine only) |
| `voice_samples/try_voices.py` | Generates samples of the available Hindi voices |

## Run it yourself

You need a free [LiveKit Cloud](https://cloud.livekit.io) project. Speech-to-text, the LLM and the voice all run through LiveKit Inference, so there are no other accounts to create.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                    # add your LiveKit URL, key and secret

.venv/bin/python generate_data.py       # fresh fake data for today
.venv/bin/python check_rules.py         # expect: 32 passed, 0 failed
.venv/bin/python reminders.py           # who would get a reminder call (dry run)

# Talk to the bot with your laptop mic. Pick any id from test_scenarios.csv
SCENARIO=R01 .venv/bin/python agent.py console   # a reminder call
SCENARIO=I12 .venv/bin/python agent.py console   # an inbound call

# Text-only tests with an AI caller and judge, one scenario at a time
.venv/bin/python run_all.py I38 I39
```

The console prints the scenario, a line you can say, and what the bot should do.

To try it in a browser instead: run `SCENARIO=R01 .venv/bin/python agent.py dev` in one terminal and `.venv/bin/python web_test.py` in another, then open http://127.0.0.1:8787.
