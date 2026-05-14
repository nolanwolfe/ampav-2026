import os
import json
import sqlite3
import csv
import io
from datetime import date, datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, Response, g
from dotenv import load_dotenv
import stripe

load_dotenv()

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
READER_ID   = os.environ.get("READER_ID", "")
READER_ID_2 = os.environ.get("READER_ID_2", "")
READERS = {
    "r1": {"id": READER_ID,   "label": "WHITE"},
    "r2": {"id": READER_ID_2, "label": "BLACK"},
}
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "petitechef")
BASE_URL = os.environ.get("BASE_URL", "")
DB_PATH      = os.path.join(os.path.dirname(__file__), "sales.db")
MENU_PATH    = os.path.join(os.path.dirname(__file__), "menu.json")
VERSION_PATH = os.path.join(os.path.dirname(__file__), "VERSION")

app = Flask(__name__)


# ── Database ──────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at     TEXT DEFAULT (datetime('now', 'localtime')),
                payment_intent_id TEXT UNIQUE,
                total_cents    INTEGER,
                discount_label TEXT,
                customer_email TEXT,
                status         TEXT DEFAULT 'processing',
                items          TEXT
            )
        """)
        # Add discount_label column if upgrading from old DB
        try:
            db.execute("ALTER TABLE orders ADD COLUMN discount_label TEXT")
        except Exception:
            pass
        db.commit()


# ── Auth ──────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="AmPav Rapport"'})
        return f(*args, **kwargs)
    return decorated


# ── POS ───────────────────────────────────────────────────

@app.route("/")
def index():
    with open(MENU_PATH) as f:
        menu = json.load(f)
    with open(VERSION_PATH) as f:
        version = f.read().strip()
    return render_template("index.html",
        cuisine_items=menu.get("cuisine", []),
        bar_items=menu.get("bar", []),
        readers=READERS,
        base_url=BASE_URL,
        version=version,
    )


@app.route("/charge", methods=["POST"])
def charge():
    data = request.get_json()
    items = data.get("items", [])
    email = data.get("email", "").strip() or None
    discount_label = data.get("discount_label") or None
    total_cents = data.get("total_cents")
    reader_key = data.get("reader_key", "r1")

    reader_id = READERS.get(reader_key, {}).get("id") or READER_ID
    if not reader_id:
        return jsonify(error="No reader configured."), 400
    if not items:
        return jsonify(error="Cart is empty."), 400
    if total_cents is None:
        total_cents = sum(int(round(item["price"] * 100)) * item["qty"] for item in items)

    item_line = ", ".join(f"{item['qty']}x {item['name']}" for item in items)
    description = f"{item_line}{' [' + discount_label + ']' if discount_label else ''}"

    params = dict(
        amount=max(50, int(total_cents)),
        currency="eur",
        payment_method_types=["card_present"],
        capture_method="automatic",
        description=description,
    )
    if email:
        params["receipt_email"] = email

    intent = stripe.PaymentIntent.create(**params)
    stripe.terminal.Reader.process_payment_intent(reader_id, payment_intent=intent.id)

    db = get_db()
    db.execute(
        "INSERT INTO orders (payment_intent_id, total_cents, discount_label, customer_email, items) VALUES (?,?,?,?,?)",
        (intent.id, int(total_cents), discount_label, email, json.dumps(items)),
    )
    db.commit()

    return jsonify(payment_intent_id=intent.id, status="processing")


@app.route("/void", methods=["POST"])
def void_order():
    data = request.get_json()
    items = data.get("items", [])
    ref = "void_" + datetime.now().strftime("%Y%m%d%H%M%S")
    db = get_db()
    db.execute(
        "INSERT INTO orders (payment_intent_id, total_cents, discount_label, status, items) VALUES (?,?,?,?,?)",
        (ref, 0, "Staff Void", "voided", json.dumps(items)),
    )
    db.commit()
    return jsonify(status="voided", ref=ref)


@app.route("/refund/<pi_id>", methods=["POST"])
def refund(pi_id):
    try:
        stripe.Refund.create(payment_intent=pi_id)
        db = get_db()
        db.execute("UPDATE orders SET status='refunded' WHERE payment_intent_id=?", (pi_id,))
        db.commit()
        return jsonify(status="refunded")
    except stripe.error.StripeError as e:
        return jsonify(error=str(e)), 400


@app.route("/send-receipt/<pi_id>", methods=["POST"])
def send_receipt(pi_id):
    try:
        email = request.get_json().get("email", "").strip()
        if not email:
            return jsonify(error="Email required"), 400
        intent = stripe.PaymentIntent.retrieve(pi_id, expand=["latest_charge"])
        charge_id = intent.latest_charge.id
        stripe.Charge.modify(charge_id, receipt_email=email)
        stripe.Charge.send_receipt(charge_id)
        return jsonify(status="sent")
    except stripe.error.StripeError as e:
        return jsonify(error=str(e)), 400


@app.route("/status/<pi_id>")
def status(pi_id):
    intent = stripe.PaymentIntent.retrieve(pi_id)
    if intent.status in ("succeeded", "canceled", "failed"):
        db = get_db()
        db.execute("UPDATE orders SET status=? WHERE payment_intent_id=?", (intent.status, pi_id))
        db.commit()
    return jsonify(intent_status=intent.status)


@app.route("/cancel/<pi_id>", methods=["POST"])
def cancel(pi_id):
    try:
        stripe.terminal.Reader.cancel_action(READER_ID)
    except Exception:
        pass
    try:
        intent = stripe.PaymentIntent.cancel(pi_id)
        db = get_db()
        db.execute("UPDATE orders SET status='canceled' WHERE payment_intent_id=?", (pi_id,))
        db.commit()
        return jsonify(status=intent.status)
    except stripe.error.InvalidRequestError as e:
        return jsonify(status="error", error=str(e))


# ── Rapport ───────────────────────────────────────────────

@app.route("/rapport/poll")
def rapport_poll():
    date_str = request.args.get('date', date.today().isoformat())
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) cnt, COALESCE(SUM(total_cents),0) total FROM orders WHERE created_at LIKE ?",
        (date_str + "%",),
    ).fetchone()
    return jsonify(count=row["cnt"], total=row["total"])

@app.route("/rapport")
def rapport():
    from datetime import timedelta
    db = get_db()

    date_str = request.args.get('date', date.today().isoformat())
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        date_str = date.today().isoformat()

    row = db.execute(
        "SELECT COUNT(*) cnt, COALESCE(SUM(total_cents),0) total FROM orders WHERE status='succeeded' AND created_at LIKE ?",
        (date_str + "%",),
    ).fetchone()
    count, total_cents = row["cnt"], row["total"]

    voided_today = db.execute(
        "SELECT COUNT(*) cnt FROM orders WHERE status='voided' AND created_at LIKE ?",
        (date_str + "%",),
    ).fetchone()["cnt"]

    with open(MENU_PATH) as f:
        menu_data = json.load(f)
    cuisine_ids = {i["id"] for i in menu_data.get("cuisine", [])}
    bar_ids     = {i["id"] for i in menu_data.get("bar", [])}

    item_counts = {}
    cuisine_counts = {}
    bar_counts = {}
    for r in db.execute("SELECT items FROM orders WHERE status='succeeded' AND created_at LIKE ?", (date_str + "%",)):
        for item in json.loads(r["items"]):
            key = item["name"]
            iid = item.get("id", "")
            if key not in item_counts:
                item_counts[key] = {"qty": 0, "revenue": 0.0}
            item_counts[key]["qty"]     += item["qty"]
            item_counts[key]["revenue"] += item["price"] * item["qty"]
            if iid in cuisine_ids:
                cuisine_counts[key] = cuisine_counts.get(key, 0) + item["qty"]
            elif iid in bar_ids:
                bar_counts[key] = bar_counts.get(key, 0) + item["qty"]
    item_counts = sorted(item_counts.items(), key=lambda x: -x[1]["qty"])
    fav_cuisine = max(cuisine_counts, key=cuisine_counts.get) if cuisine_counts else "—"
    fav_drink   = max(bar_counts,     key=bar_counts.get)     if bar_counts     else "—"

    recent = []
    for r in db.execute(
        "SELECT id, payment_intent_id, created_at, total_cents, discount_label, customer_email, status, items FROM orders WHERE created_at LIKE ? ORDER BY id DESC",
        (date_str + "%",),
    ):
        lines = [{"name": i["name"], "qty": i["qty"], "price": i["price"]} for i in json.loads(r["items"])]
        recent.append({
            "id":       r["id"],
            "date":     r["created_at"][:10],
            "time":     r["created_at"][11:16],
            "lines":    lines,
            "discount": r["discount_label"] or "",
            "total":    r["total_cents"] / 100,
            "email":    r["customer_email"] or "",
            "status":   r["status"],
            "pi_id":    r["payment_intent_id"] or "",
        })

    d = date.fromisoformat(date_str)
    prev_date = (d - timedelta(days=1)).isoformat()
    next_date = (d + timedelta(days=1)).isoformat()

    with open(VERSION_PATH) as f:
        version = f.read().strip()
    return render_template("rapport.html",
        selected_date=date_str,
        prev_date=prev_date,
        next_date=next_date,
        is_today=(d == date.today()),
        count=count,
        total_eur=total_cents / 100,
        voided_today=voided_today,
        fav_cuisine=fav_cuisine,
        fav_drink=fav_drink,
        item_counts=item_counts,
        recent=recent,
        base_url=BASE_URL,
        version=version,
    )


@app.route("/export.csv")
@require_admin
def export_csv():
    db = get_db()
    rows = db.execute(
        "SELECT id, created_at, total_cents, discount_label, customer_email, status, items FROM orders ORDER BY id DESC"
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Date", "Time", "Total (EUR)", "Discount", "Email", "Status", "Items"])
    for r in rows:
        items_str = "; ".join(f"{i['qty']}x {i['name']} @€{i['price']}" for i in json.loads(r["items"]))
        w.writerow([
            r["id"], r["created_at"][:10], r["created_at"][11:16],
            f"{r['total_cents']/100:.2f}", r["discount_label"] or "",
            r["customer_email"] or "", r["status"], items_str,
        ])
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=ampav_rapport_{date.today()}.csv"})


# ── Startup ───────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
