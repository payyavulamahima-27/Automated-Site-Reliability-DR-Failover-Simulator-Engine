"""
Core DR Failover Simulator Engine.

Runs as a background thread. On every tick it:
  1. Simulates health metrics (latency, error rate) for every site.
  2. Computes a 0-100 health score per site.
  3. Checks the currently ACTIVE site's health against a threshold.
  4. If the active site is unhealthy for N consecutive checks, and
     auto-failover is enabled, it automatically promotes the healthiest
     secondary site to active and logs the failover event.
  5. A site can also be manually forced into "outage" mode (chaos
     injection) via the API, which the engine will detect exactly like
     a real failure.
"""

import random
import threading
import time
from datetime import datetime

from database import get_connection, log_event

HEALTH_FAILURE_THRESHOLD = 40      # below this = unhealthy
FAILURES_BEFORE_FAILOVER = 2       # consecutive bad checks before auto-failover
LATENCY_BASELINE = {"us-east-1": 18, "us-west-2": 25, "eu-central-1": 40}

_engine_lock = threading.Lock()
_engine_thread = None
_stop_flag = False


def _simulate_site_metrics(site):
    """Randomly evolve a site's latency/error-rate/health, unless it's under forced outage."""
    if site["forced_outage"]:
        latency = random.randint(800, 2000)
        error_rate = round(random.uniform(60, 100), 1)
        health = 0
        status = "down"
        return latency, error_rate, health, status

    baseline = LATENCY_BASELINE.get(site["region"], 30)
    # Small random walk around baseline, with rare latency spikes for realism
    spike = random.random() < 0.07
    latency = baseline + random.randint(-5, 15) + (random.randint(200, 600) if spike else 0)
    error_rate = round(max(0.0, random.gauss(0.5, 0.6)), 2)
    if spike:
        error_rate += random.uniform(5, 20)

    # Health score derived from latency + error rate
    health = 100
    health -= min(50, latency / 4)
    health -= min(50, error_rate * 3)
    health = max(0, min(100, round(health)))

    if health >= 70:
        status = "healthy"
    elif health >= HEALTH_FAILURE_THRESHOLD:
        status = "degraded"
    else:
        status = "down"

    return latency, round(error_rate, 1), health, status


def _run_engine_tick():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM sites")
    sites = cur.fetchall()

    updated = {}
    for site in sites:
        latency, error_rate, health, status = _simulate_site_metrics(site)
        cur.execute(
            """UPDATE sites SET latency_ms=?, error_rate=?, health_score=?, status=?, last_checked=?
               WHERE id=?""",
            (latency, error_rate, health, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), site["id"]),
        )
        updated[site["id"]] = {"health": health, "status": status, "name": site["name"], "role": site["role"]}

    conn.commit()

    # Evaluate active site health
    cur.execute("SELECT * FROM sites WHERE is_active = 1")
    active = cur.fetchone()
    cur.execute("SELECT * FROM engine_state WHERE id = 1")
    state = cur.fetchone()

    if active:
        active_health = updated[active["id"]]["health"]

        if active_health < HEALTH_FAILURE_THRESHOLD:
            new_count = state["consecutive_failures"] + 1
            cur.execute("UPDATE engine_state SET consecutive_failures = ? WHERE id = 1", (new_count,))
            conn.commit()

            if new_count == 1:
                log_event("health_check", site_name=active["name"],
                           detail=f"Health degraded to {active_health}/100 (latency/error spike detected).",
                           severity="warning")

            if new_count >= FAILURES_BEFORE_FAILOVER and state["auto_failover_enabled"]:
                # Find healthiest secondary that isn't down
                cur.execute("SELECT * FROM sites WHERE id != ? ORDER BY health_score DESC", (active["id"],))
                candidates = cur.fetchall()
                target = next((c for c in candidates if c["health_score"] >= HEALTH_FAILURE_THRESHOLD), None)

                if target:
                    cur.execute("UPDATE sites SET is_active = 0 WHERE id = ?", (active["id"],))
                    cur.execute("UPDATE sites SET is_active = 1 WHERE id = ?", (target["id"],))
                    cur.execute("UPDATE engine_state SET consecutive_failures = 0 WHERE id = 1")
                    conn.commit()
                    log_event(
                        "auto_failover",
                        from_site=active["name"], to_site=target["name"],
                        detail=f"Automatic failover triggered: {active['name']} health "
                               f"({active_health}/100) breached threshold for {new_count} consecutive checks. "
                               f"Promoted {target['name']} to active.",
                        severity="critical",
                    )
                else:
                    log_event(
                        "failover_unavailable",
                        site_name=active["name"],
                        detail="Active site is unhealthy but no healthy secondary is available for failover!",
                        severity="critical",
                    )
        else:
            if state["consecutive_failures"] > 0:
                cur.execute("UPDATE engine_state SET consecutive_failures = 0 WHERE id = 1")
                conn.commit()

    conn.close()


def _engine_loop():
    global _stop_flag
    while not _stop_flag:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT check_interval_seconds FROM engine_state WHERE id = 1")
            row = cur.fetchone()
            interval = row["check_interval_seconds"] if row else 3
            conn.close()

            _run_engine_tick()
        except Exception as e:
            print(f"[engine error] {e}")
            interval = 3
        time.sleep(interval)


def start_engine():
    global _engine_thread, _stop_flag
    with _engine_lock:
        if _engine_thread is None or not _engine_thread.is_alive():
            _stop_flag = False
            _engine_thread = threading.Thread(target=_engine_loop, daemon=True)
            _engine_thread.start()


def stop_engine():
    global _stop_flag
    _stop_flag = True
