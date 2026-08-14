from flask import Flask, render_template, jsonify, request
from datetime import datetime

from database import get_connection, init_db, log_event
from engine import start_engine, HEALTH_FAILURE_THRESHOLD

app = Flask(__name__)

# Initialize DB and start the background failover engine as soon as this module
# is loaded (works whether run via `python app.py`, a test client, or a WSGI server).
init_db()
start_engine()


@app.route("/")
def dashboard():
    return render_template("dashboard.html", threshold=HEALTH_FAILURE_THRESHOLD)


@app.route("/api/status")
def api_status():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM sites ORDER BY role DESC, id ASC")
    sites = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT * FROM engine_state WHERE id = 1")
    state = dict(cur.fetchone())

    cur.execute("SELECT * FROM events ORDER BY id DESC LIMIT 25")
    events = [dict(row) for row in cur.fetchall()]

    active = next((s for s in sites if s["is_active"]), None)

    conn.close()
    return jsonify({
        "sites": sites,
        "events": events,
        "active_site": active["name"] if active else None,
        "auto_failover_enabled": bool(state["auto_failover_enabled"]),
        "consecutive_failures": state["consecutive_failures"],
        "threshold": HEALTH_FAILURE_THRESHOLD,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/chaos/<int:site_id>", methods=["POST"])
def inject_chaos(site_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    site = cur.fetchone()
    if not site:
        conn.close()
        return jsonify({"error": "Site not found"}), 404

    cur.execute("UPDATE sites SET forced_outage = 1 WHERE id = ?", (site_id,))
    conn.commit()
    conn.close()
    log_event("chaos_injected", site_name=site["name"],
               detail=f"Manual chaos injection: forced outage triggered on {site['name']}.",
               severity="critical")
    return jsonify({"success": True})


@app.route("/api/recover/<int:site_id>", methods=["POST"])
def recover_site(site_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    site = cur.fetchone()
    if not site:
        conn.close()
        return jsonify({"error": "Site not found"}), 404

    cur.execute("UPDATE sites SET forced_outage = 0 WHERE id = ?", (site_id,))
    conn.commit()
    conn.close()
    log_event("chaos_recovered", site_name=site["name"],
               detail=f"{site['name']} manually recovered from forced outage.",
               severity="info")
    return jsonify({"success": True})


@app.route("/api/failover/<int:site_id>", methods=["POST"])
def manual_failover(site_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM sites WHERE is_active = 1")
    current = cur.fetchone()
    cur.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    target = cur.fetchone()

    if not target:
        conn.close()
        return jsonify({"error": "Target site not found"}), 404
    if current and current["id"] == target["id"]:
        conn.close()
        return jsonify({"error": "That site is already active"}), 400

    if current:
        cur.execute("UPDATE sites SET is_active = 0 WHERE id = ?", (current["id"],))
    cur.execute("UPDATE sites SET is_active = 1 WHERE id = ?", (target["id"],))
    cur.execute("UPDATE engine_state SET consecutive_failures = 0 WHERE id = 1")
    conn.commit()
    conn.close()

    log_event(
        "manual_failover",
        from_site=current["name"] if current else None,
        to_site=target["name"],
        detail=f"Manual failover triggered by operator: switched active traffic to {target['name']}.",
        severity="warning",
    )
    return jsonify({"success": True})


@app.route("/api/toggle-auto-failover", methods=["POST"])
def toggle_auto_failover():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT auto_failover_enabled FROM engine_state WHERE id = 1")
    current = cur.fetchone()["auto_failover_enabled"]
    new_val = 0 if current else 1
    cur.execute("UPDATE engine_state SET auto_failover_enabled = ? WHERE id = 1", (new_val,))
    conn.commit()
    conn.close()
    log_event("config_change",
               detail=f"Automatic failover {'ENABLED' if new_val else 'DISABLED'} by operator.",
               severity="info")
    return jsonify({"success": True, "auto_failover_enabled": bool(new_val)})


@app.route("/api/reset", methods=["POST"])
def reset_simulation():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sites")
    cur.execute("DELETE FROM events")
    cur.execute("DELETE FROM engine_state")
    conn.commit()
    conn.close()
    init_db()
    log_event("system_reset", detail="Simulation reset to initial state by operator.", severity="info")
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5002)
