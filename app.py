import csv
import io
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, abort, jsonify, render_template, request

DB_PATH = os.environ.get("PATCHING_DB", "patching.db")

app = Flask(__name__)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS status_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patching_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patching_servers (
                host TEXT PRIMARY KEY,
                cycle_id TEXT NOT NULL,
                imported_at TEXT NOT NULL
            )
            """
        )


def store_status_update(host, step, status):
    now = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO status_updates (host, step, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (host, step, status, now),
        )

        step_lower = step.strip().lower()
        open_run = conn.execute(
            """
            SELECT id FROM patching_runs
            WHERE host = ? AND end_time IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (host,),
        ).fetchone()

        status_lower = status.strip().lower()

        if step_lower == "start":
            conn.execute(
                """
                INSERT INTO patching_runs (host, start_time, end_time)
                VALUES (?, ?, NULL)
                """,
                (host, now),
            )
        elif step_lower == "complete" or "fail" in status_lower:
            if open_run:
                conn.execute(
                    """
                    UPDATE patching_runs
                    SET end_time = ?
                    WHERE id = ?
                    """,
                    (now, open_run["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO patching_runs (host, start_time, end_time)
                    VALUES (?, ?, ?)
                    """,
                    (host, now, now),
                )
        elif not open_run:
            conn.execute(
                """
                INSERT INTO patching_runs (host, start_time, end_time)
                VALUES (?, ?, NULL)
                """,
                (host, now),
            )


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/status", methods=["GET"])
def get_latest_status():
    with get_db_connection() as conn:
        server_rows = conn.execute(
            """
            SELECT host, cycle_id, imported_at
            FROM patching_servers
            ORDER BY host
            """
        ).fetchall()

        status_rows = conn.execute(
            """
            SELECT host, step, status, created_at
            FROM status_updates
            WHERE id IN (
                SELECT MAX(id) FROM status_updates GROUP BY host
            )
            ORDER BY host
            """
        ).fetchall()

        run_rows = conn.execute(
            """
            SELECT host, start_time, end_time
            FROM patching_runs
            WHERE id IN (
                SELECT MAX(id) FROM patching_runs GROUP BY host
            )
            """
        ).fetchall()

    status_by_host = {row["host"]: row for row in status_rows}
    runs_by_host = {
        row["host"]: {
            "start_time": row["start_time"],
            "end_time": row["end_time"],
        }
        for row in run_rows
    }

    hosts = {row["host"] for row in status_rows}
    if server_rows:
        hosts.update(row["host"] for row in server_rows)

    response = []
    for host in sorted(hosts):
        status_row = status_by_host.get(host)
        run_row = runs_by_host.get(host, {})
        if status_row:
            step = status_row["step"]
            status = status_row["status"]
            created_at = status_row["created_at"]
        else:
            step = "not-started"
            status = "Not Started"
            created_at = None

        completed = run_row.get("end_time") is not None
        response.append(
            {
                "host": host,
                "step": step,
                "status": status,
                "created_at": created_at,
                "started_at": run_row.get("start_time"),
                "ended_at": run_row.get("end_time"),
                "duration_seconds": _duration_seconds(run_row),
                "running": _is_running(run_row),
                "completed": completed,
            }
        )

    return jsonify(response)


@app.route("/api/servers/import", methods=["POST"])
def import_servers():
    raw_data = b""
    if "file" in request.files:
        upload = request.files["file"]
        if not upload.filename:
            return jsonify({"error": "missing filename"}), 400
        raw_data = upload.read()
    elif request.data:
        raw_data = request.data
    else:
        return jsonify({"error": "missing file"}), 400
    try:
        text = raw_data.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_data.decode("latin-1")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return jsonify({"error": "empty CSV"}), 400

    header = [cell.strip() for cell in rows[0]]
    header_lower = [cell.lower() for cell in header]
    host_keys = {"host", "hostname", "name", "fqdn", "server", "device"}
    has_header = any(cell in host_keys for cell in header_lower)

    hosts = []
    if has_header:
        reader = csv.DictReader(io.StringIO(text))
        field_map = {name.lower(): name for name in reader.fieldnames or []}
        host_field = next((field_map[key] for key in host_keys if key in field_map), None)
        if host_field is None:
            return jsonify({"error": "no host column found"}), 400
        for row in reader:
            value = (row.get(host_field) or "").strip()
            if value:
                hosts.append(value)
    else:
        for row in rows:
            if not row:
                continue
            value = row[0].strip()
            if value:
                hosts.append(value)

    unique_hosts = sorted(set(hosts))
    if not unique_hosts:
        return jsonify({"error": "no hosts found"}), 400

    cycle_id = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM patching_servers")
        conn.executemany(
            "DELETE FROM status_updates WHERE host = ?",
            [(host,) for host in unique_hosts],
        )
        conn.executemany(
            "DELETE FROM patching_runs WHERE host = ?",
            [(host,) for host in unique_hosts],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO patching_servers (host, cycle_id, imported_at)
            VALUES (?, ?, ?)
            """,
            [(host, cycle_id, cycle_id) for host in unique_hosts],
        )

    return jsonify({"imported": len(unique_hosts), "cycle_id": cycle_id})


def _duration_seconds(run_row):
    if not run_row or not run_row.get("start_time"):
        return None

    start = datetime.fromisoformat(run_row["start_time"])
    end_time = run_row.get("end_time")
    end = datetime.fromisoformat(end_time) if end_time else datetime.now(timezone.utc)
    return int((end - start).total_seconds())


def _is_running(run_row):
    if not run_row:
        return False
    return run_row.get("start_time") is not None and run_row.get("end_time") is None


@app.route("/status", methods=["POST"])
@app.route("/patching", methods=["POST"])
def process_status_update():
    if not request.json or "status" not in request.json:
        abort(400)

    host = request.json.get("host")
    step = request.json.get("step")
    status = request.json.get("status")

    if not host or not step or not status:
        abort(400)

    store_status_update(host, step, status)
    print(f"Received status update from {host}:{step}:{status}")

    return jsonify({"answer": "ACK"})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=9999, debug=True)
