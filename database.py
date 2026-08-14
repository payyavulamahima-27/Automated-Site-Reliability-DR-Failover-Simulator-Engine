import sqlite3
from datetime import datetime

DB_NAME = "dr_failover.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            region TEXT NOT NULL,
            role TEXT NOT NULL,              -- 'primary' or 'secondary'
            is_active INTEGER DEFAULT 0,     -- 1 = currently serving traffic
            status TEXT DEFAULT 'healthy',   -- healthy / degraded / down
            health_score INTEGER DEFAULT 100,-- 0-100
            latency_ms INTEGER DEFAULT 20,
            error_rate REAL DEFAULT 0.0,
            forced_outage INTEGER DEFAULT 0, -- manual chaos injection flag
            last_checked TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,        -- health_check, auto_failover, manual_failover, failback, chaos_injected, chaos_recovered
            site_name TEXT,
            from_site TEXT,
            to_site TEXT,
            detail TEXT,
            severity TEXT DEFAULT 'info',    -- info, warning, critical
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS engine_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            consecutive_failures INTEGER DEFAULT 0,
            auto_failover_enabled INTEGER DEFAULT 1,
            check_interval_seconds INTEGER DEFAULT 3
        )
    """)

    cur.execute("SELECT COUNT(*) FROM sites")
    if cur.fetchone()[0] == 0:
        sites = [
            ("Primary - US East", "us-east-1", "primary", 1, "healthy", 100, 18, 0.0),
            ("Secondary - US West", "us-west-2", "secondary", 0, "healthy", 100, 25, 0.0),
            ("Secondary - EU Central", "eu-central-1", "secondary", 0, "healthy", 100, 40, 0.0),
        ]
        cur.executemany(
            """INSERT INTO sites (name, region, role, is_active, status, health_score, latency_ms, error_rate, last_checked)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(*s, datetime.now().strftime("%Y-%m-%d %H:%M:%S")) for s in sites],
        )

    cur.execute("SELECT COUNT(*) FROM engine_state")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO engine_state (id, consecutive_failures, auto_failover_enabled, check_interval_seconds) VALUES (1, 0, 1, 3)")

    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """INSERT INTO events (event_type, site_name, detail, severity, created_at)
               VALUES ('system_start', NULL, 'DR Failover Simulator Engine initialized. Primary - US East is serving traffic.', 'info', ?)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )

    conn.commit()
    conn.close()


def log_event(event_type, site_name=None, from_site=None, to_site=None, detail=None, severity="info"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO events (event_type, site_name, from_site, to_site, detail, severity, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event_type, site_name, from_site, to_site, detail, severity,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized with 3 simulated sites (1 primary, 2 secondary).")
