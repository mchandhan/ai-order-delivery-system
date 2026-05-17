"""
app.py  —  Flask backend for the Order Chat System
"""

import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv

load_dotenv()

import database as db
import huggingface_client as ai

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "order-chat-secret-2024"

# ── Startup ────────────────────────────────────────────────────────────────────

@app.before_request
def setup():
    db.init_db()

# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("chat_page"))


@app.route("/chat")
def chat_page():
    recent_orders = db.get_all_orders()[:5]
    return render_template("chat.html", recent_orders=recent_orders)


@app.route("/orders")
def dashboard_page():
    orders = db.get_all_orders()
    stats  = db.get_order_stats()
    return render_template("dashboard.html", orders=orders, stats=stats)


# ── Chat API ───────────────────────────────────────────────────────────────────

@app.route("/chat/send", methods=["POST"])
def chat_send():
    data    = request.get_json()
    message = (data or {}).get("message", "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    try:
        action = ai.chat(message)
    except ValueError as e:
        return jsonify({
            "reply": f"⚠️ Configuration error: {e}",
            "type":  "error"
        }), 500
    except ConnectionError as e:
        return jsonify({
            "reply": f"⚠️ {e}",
            "type":  "error"
        }), 503
    except (TimeoutError, RuntimeError, PermissionError) as e:
        return jsonify({
            "reply": f"⚠️ {e}",
            "type":  "error"
        }), 500

    return _handle_action(action)


def _handle_action(action: dict):
    act = action.get("action", "unknown")

    # ── Create Order ──────────────────────────────────────────────────────────
    if act == "create_order":
        part      = action.get("part", "Unknown Part")
        material  = action.get("material", "Not specified")
        quantity  = int(action.get("quantity", 1))
        deadline  = action.get("deadline") or (
            datetime.now() + timedelta(days=30)
        ).strftime("%Y-%m-%d")

        order_id = db.create_order(part, material, quantity, deadline)
        reply = (
            f"✅ **Order #{order_id} created successfully!**\n\n"
            f"- **Part:** {part}\n"
            f"- **Material:** {material}\n"
            f"- **Quantity:** {quantity:,}\n"
            f"- **Deadline:** {deadline}\n"
            f"- **Status:** Pending\n\n"
            f"The order has been added to the dashboard."
        )
        return jsonify({"reply": reply, "type": "success", "action": act, "order_id": order_id})

    # ── Update Status ─────────────────────────────────────────────────────────
    elif act == "update_status":
        order_id = action.get("order_id")
        status   = action.get("status", "Pending")

        if not order_id:
            return jsonify({"reply": "⚠️ I couldn't find the order ID in your message. Please specify, e.g. 'Mark order #3 as accepted'.", "type": "warning"})

        order = db.get_order(order_id)
        if not order:
            return jsonify({"reply": f"⚠️ Order #{order_id} does not exist.", "type": "warning"})

        db.update_order_status(order_id, status)
        reply = (
            f"✅ **Order #{order_id} updated!**\n\n"
            f"- **Part:** {order['part']}\n"
            f"- **New Status:** {status}\n\n"
            f"Dashboard has been refreshed."
        )
        return jsonify({"reply": reply, "type": "success", "action": act, "order_id": order_id})

    # ── Add Quality Log ───────────────────────────────────────────────────────
    elif act == "add_quality_log":
        order_id = action.get("order_id")
        note     = action.get("note", "")

        if not order_id:
            return jsonify({"reply": "⚠️ Please specify the order ID for the quality note.", "type": "warning"})

        order = db.get_order(order_id)
        if not order:
            return jsonify({"reply": f"⚠️ Order #{order_id} does not exist.", "type": "warning"})

        log_id = db.add_quality_log(order_id, note)
        reply = (
            f"📋 **Quality log added to Order #{order_id}**\n\n"
            f"- **Part:** {order['part']}\n"
            f"- **Note:** {note}\n"
            f"- **Log ID:** #{log_id}"
        )
        return jsonify({"reply": reply, "type": "success", "action": act})

    # ── Query Single Order ────────────────────────────────────────────────────
    elif act == "query_order":
        order_id = action.get("order_id")
        if not order_id:
            return jsonify({"reply": "⚠️ Please provide the order ID to look up.", "type": "warning"})

        order = db.get_order(order_id)
        if not order:
            return jsonify({"reply": f"⚠️ Order #{order_id} not found.", "type": "warning"})

        logs  = db.get_quality_logs(order_id)
        logs_text = ""
        if logs:
            logs_text = "\n\n**Quality Logs:**\n" + "\n".join(
                f"  - [{l['timestamp'][:16]}] {l['note']}" for l in logs
            )

        reply = (
            f"🔍 **Order #{order_id} Details**\n\n"
            f"- **Part:** {order['part']}\n"
            f"- **Material:** {order['material']}\n"
            f"- **Quantity:** {order['quantity']:,}\n"
            f"- **Deadline:** {order['deadline']}\n"
            f"- **Status:** {order['status']}\n"
            f"- **Created:** {order['created_at'][:16]}"
            f"{logs_text}"
        )
        return jsonify({"reply": reply, "type": "info", "action": act})

    # ── List Orders ───────────────────────────────────────────────────────────
    elif act == "list_orders":
        status_filter = action.get("filter", "all")
        orders = db.get_all_orders(status_filter)

        if not orders:
            return jsonify({"reply": f"No orders found with filter: **{status_filter}**.", "type": "info"})

        header = f"📦 **{status_filter.title()} Orders ({len(orders)} total)**\n\n"
        rows = "\n".join(
            f"- **#{o['order_id']}** {o['part']} — {o['quantity']} units — "
            f"**{o['status']}** (due {o['deadline']})"
            for o in orders[:20]  # cap at 20 for readability
        )
        if len(orders) > 20:
            rows += f"\n\n_...and {len(orders) - 20} more. Check the dashboard for the full list._"

        return jsonify({"reply": header + rows, "type": "info", "action": act})

    # ── Unknown / Fallback ────────────────────────────────────────────────────
    else:
        fallback = action.get("reply", "I'm not sure how to handle that. Try asking me to create an order, update a status, or list orders.")
        return jsonify({"reply": fallback, "type": "chat", "action": act})


# ── Orders REST API (for dashboard polling) ────────────────────────────────────

@app.route("/orders/api")
def orders_api():
    status_filter = request.args.get("status", "all")
    search_query  = request.args.get("q", "")
    sort_by       = request.args.get("sort", "order_id")
    sort_dir      = request.args.get("dir", "DESC")
    
    orders = db.get_all_orders(status_filter, search_query, sort_by, sort_dir)
    stats  = db.get_order_stats()
    return jsonify({"orders": orders, "stats": stats})


@app.route("/orders/api/<int:order_id>")
def order_detail_api(order_id):
    order = db.get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    logs = db.get_quality_logs(order_id)
    return jsonify({"order": order, "quality_logs": logs})


@app.route("/orders/update", methods=["POST"])
def direct_update():
    data     = request.get_json()
    order_id = data.get("order_id")
    status   = data.get("status")
    if not order_id or not status:
        return jsonify({"error": "Missing order_id or status"}), 400
    success = db.update_order_status(order_id, status)
    return jsonify({"success": success})


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    print("\n[OrderMind] Server running at http://localhost:5000\n")
    app.run(debug=True, port=5000)
