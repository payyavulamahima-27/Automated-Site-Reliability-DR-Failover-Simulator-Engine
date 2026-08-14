# Automated Site Reliability DR Failover Simulator Engine

A live simulation of a Disaster Recovery (DR) system: one **primary** site and two
**secondary/DR** sites are continuously health-checked by a background engine. If the
active site's health drops below a threshold for consecutive checks, the engine
**automatically fails over** to the healthiest secondary — just like a real SRE failover
system, without a human needing to intervene. You can also inject simulated outages and
trigger manual failovers for a live demo.

## Tech Stack
- **Backend:** Python, Flask
- **Database:** SQLite (stores site state + full event/audit log)
- **Engine:** A background Python thread that ticks every few seconds, simulating
  latency/error-rate metrics per site and running the failover decision logic
- **Frontend:** HTML/CSS/vanilla JS polling `/api/status` every 2 seconds for a live view
  (no page refresh needed)

## Project Structure
```
dr_failover_simulator/
├── app.py              # Flask routes + REST API
├── engine.py           # Background health-simulation & auto-failover logic
├── database.py         # Schema, seed data, event logging helper
├── requirements.txt
├── run.bat              # One-click installer + launcher (Windows)
├── static/
│   ├── style.css         # Dark ops-dashboard styling
│   └── script.js         # Live polling + dashboard rendering + button actions
└── templates/
    ├── base.html
    └── dashboard.html
```

## How to Run

### Easiest way (Windows)
Double-click `run.bat`. It installs dependencies, starts the server in a separate
window, and auto-opens the dashboard in your browser.

### Manual way
```
pip install -r requirements.txt
python app.py
```
Then open **http://127.0.0.1:5002**

## How It Works

### The Engine (`engine.py`)
Every 3 seconds (configurable), the engine:
1. **Simulates metrics** for all 3 sites — latency and error rate evolve with small
   random walks, plus occasional random "spikes" for realism.
2. **Computes a health score (0-100)** per site from latency + error rate.
3. **Classifies status:** `healthy` (≥70), `degraded` (40-69), `down` (<40).
4. **Checks the active site.** If its health drops below the threshold for **2
   consecutive ticks**, and auto-failover is enabled, the engine automatically:
   - Finds the healthiest secondary site that's above the threshold
   - Promotes it to active
   - Demotes the old active site
   - Logs a `critical` severity `auto_failover` event with the reason

### Manual Controls (from the dashboard)
- **Inject Outage** — forces a site's health to 0 (simulates a real datacenter outage),
  which the engine will detect on its next tick just like a real failure
- **Recover** — clears the forced outage
- **Failover Here** — manually promote any secondary to active immediately
- **Toggle Auto-Failover** — turn the automatic engine decision-making on/off, to
  demonstrate the difference between automatic vs. manual DR response
- **Reset Simulation** — wipes state back to the initial Primary/Secondary setup

### Live Dashboard
The frontend polls `GET /api/status` every 2 seconds and re-renders:
- Site health bars (color-coded green/amber/red)
- Which site is currently ACTIVE
- A full chronological event/audit log of every health check, failover, and manual action

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | Full current state: sites, events, active site, engine config |
| POST | `/api/chaos/<site_id>` | Inject a forced outage on a site |
| POST | `/api/recover/<site_id>` | Clear a forced outage |
| POST | `/api/failover/<site_id>` | Manually make a site active |
| POST | `/api/toggle-auto-failover` | Enable/disable automatic failover |
| POST | `/api/reset` | Reset the whole simulation |

## Demo Script (for your presentation)
1. Show the dashboard — 3 sites, Primary is active, all healthy.
2. Click **"Inject Outage"** on the Primary site.
3. Watch the health bar drop to 0 and status turn red.
4. Within ~6-9 seconds (2 engine ticks), watch the **event log** show the health
   degradation, then the **automatic failover** event — the ACTIVE tag jumps to a
   secondary site on its own, no button pressed.
5. Click **"Recover"** on the old primary to bring it back healthy.
6. Optionally demonstrate **Toggle Auto-Failover OFF**, inject another outage, and show
   that nothing happens automatically — then use **"Failover Here"** to do it manually,
   illustrating the value the automatic engine adds.

## Possible Future Enhancements (good to mention if asked about scope)
- Real health checks (actual HTTP pings to real servers/microservices) instead of
  simulated metrics
- Configurable thresholds and check intervals from the UI
- Multi-engine support (per-service failover, not just per-site)
- Slack/email alerting on failover events
- Historical health charts (latency/error trend graphs over time)
