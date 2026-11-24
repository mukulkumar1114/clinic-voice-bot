"""Browser mic test for the clinic bot. Serves ONLY on this Mac (127.0.0.1).
Run the worker first:  SCENARIO=R01 .venv/bin/python agent.py dev
Then:                  .venv/bin/python web_test.py   -> open http://127.0.0.1:8787
"""
import json, os, time, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from livekit import api

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Clinic bot test</title>
<body style="font-family:system-ui;max-width:520px;margin:40px auto;padding:0 16px">
<h2>Reminder call test (fake data)</h2>
<p>You are the customer in scenario R01 (see test_scenarios.csv: consult tomorrow 11:00). Click Start and speak when the bot greets.</p>
<button id=b style="font-size:18px;padding:10px 22px">Start call</button> <span id=s></span>
<div id=a></div>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2.5.7/dist/livekit-client.umd.min.js"></script>
<script>
let room;
const s = t => document.getElementById('s').textContent = t;
b.onclick = async () => {
  if (room) { room.disconnect(); room = null; b.textContent = 'Start call'; s('ended'); return; }
  s('connecting...');
  const r = await (await fetch('/token')).json();
  room = new LivekitClient.Room();
  room.on(LivekitClient.RoomEvent.TrackSubscribed, (t) => { if (t.kind === 'audio') document.getElementById('a').appendChild(t.attach()); });
  room.on(LivekitClient.RoomEvent.Disconnected, () => { b.textContent = 'Start call'; s('ended'); room = null; });
  await room.connect(r.url, r.token);
  await room.localParticipant.setMicrophoneEnabled(true);
  b.textContent = 'End call'; s('connected - wait for the bot to speak');
};
</script>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/token":
            room = f"test-{uuid.uuid4().hex[:8]}"
            tok = (api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
                   .with_identity("tester").with_ttl(__import__("datetime").timedelta(minutes=30))
                   .with_grants(api.VideoGrants(room_join=True, room=room))
                   .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name="clinic-receptionist")])))
            body = json.dumps({"url": os.environ["LIVEKIT_URL"], "token": tok.to_jwt()}).encode()
            ct = "application/json"
        else:
            body, ct = PAGE.encode(), "text/html"
        self.send_response(200); self.send_header("Content-Type", ct); self.end_headers(); self.wfile.write(body)

HTTPServer(("127.0.0.1", 8787), H).serve_forever()
