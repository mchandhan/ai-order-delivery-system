import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            part       TEXT    NOT NULL,
            material   TEXT,
            quantity   INTEGER,
            deadline   DATE,
            status     TEXT DEFAULT 'Pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quality_logs (
            log_id    INTEGER  PRIMARY KEY AUTOINCREMENT,
            order_id  INTEGER,
            note      TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
    """)
    conn.commit()

    # Seed sample data only if empty
    count = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if count == 0:
        sample_orders = [
            ("Aluminum Brackets",    "Aluminum 6061",    50,  "2026-06-15", "Pending"),
            ("Steel Shafts",         "Stainless Steel",  120, "2026-06-20", "In Progress"),
            ("Titanium Bolts",       "Grade 5 Titanium", 200, "2026-06-10", "Completed"),
            ("Carbon Fiber Panels",  "Carbon Fiber T700",10,  "2026-07-01", "Pending"),
            ("Brass Fittings",       "Naval Brass",      75,  "2026-06-25", "Accepted"),
            ("Copper Coils",         "Pure Copper C110", 30,  "2026-07-05", "Pending"),
            ("Plastic Housings",     "ABS Plastic",      500, "2026-06-30", "In Progress"),
            ("Rubber Seals",         "EPDM Rubber",      1000,"2026-06-18", "Rejected"),
            ("Magnesium Alloy Rods", "AZ31 Magnesium",   60,  "2026-07-10", "Pending"),
            ("Zinc Die Cast Parts",  "Zinc Alloy #3",    250, "2026-06-28", "Accepted"),
        ]
        cur.executemany(
            "INSERT INTO orders (part, material, quantity, deadline, status) VALUES (?,?,?,?,?)",
            sample_orders
        )

        sample_logs = [
            (2, "Surface finish within tolerance."),
            (2, "Dimensional check passed at QC station 3."),
            (3, "Final inspection passed. Ready for shipment."),
            (5, "First article inspection approved."),
            (7, "Minor warping detected on batch #2, rework in progress."),
            (8, "Color inconsistency noted — supplier notified."),
        ]
        cur.executemany(
            "INSERT INTO quality_logs (order_id, note) VALUES (?,?)",
            sample_logs
        )
        conn.commit()

    conn.close()


# ── Order CRUD ─────────────────────────────────────────────────────────────────

def create_order(part, material, quantity, deadline, status="Pending"):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO orders (part, material, quantity, deadline, status) VALUES (?,?,?,?,?)",
        (part, material, quantity, deadline, status)
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def update_order_status(order_id, status):
    conn = get_connection()
    cur = conn.execute(
        "UPDATE orders SET status=? WHERE order_id=?", (status, order_id)
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_order(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_orders(status_filter=None, search=None, sort_by="order_id", sort_dir="DESC"):
    conn = get_connection()
    # Query that joins with the latest quality log note
    query = """
        SELECT o.*, q.note as latest_log 
        FROM orders o
        LEFT JOIN (
            SELECT order_id, note, MAX(timestamp) 
            FROM quality_logs 
            GROUP BY order_id
        ) q ON o.order_id = q.order_id
        WHERE 1=1
    """
    params = []

    if status_filter and status_filter.lower() != "all":
        query += " AND LOWER(o.status)=?"
        params.append(status_filter.lower())

    if search:
        query += " AND (o.part LIKE ? OR o.material LIKE ? OR CAST(o.order_id AS TEXT) LIKE ? OR q.note LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    # Validate sort_by to prevent injection
    allowed_cols = ["order_id", "part", "material", "quantity", "deadline", "status", "created_at"]
    if sort_by not in allowed_cols:
        sort_by = "order_id"
    
    if sort_dir not in ["ASC", "DESC"]:
        sort_dir = "DESC"

    query += f" ORDER BY o.{sort_by} {sort_dir} LIMIT 1000"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_stats():
    conn = get_connection()
    stats = {}
    for s in ["Received", "In Review", "Accepted", "Completed", "Rejected"]:
        count = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status=?", (s,)
        ).fetchone()[0]
        stats[s] = count
    stats["Total"] = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return stats


# ── Quality Logs ───────────────────────────────────────────────────────────────

def add_quality_log(order_id, note):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO quality_logs (order_id, note) VALUES (?,?)", (order_id, note)
    )
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id


def get_quality_logs(order_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM quality_logs WHERE order_id=? ORDER BY timestamp DESC",
        (order_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
