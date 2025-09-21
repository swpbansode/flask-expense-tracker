import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get('EXPENSE_DB') or os.path.join(BASE_DIR, 'expenses.db')
SECRET_KEY = os.environ.get('FLASK_SECRET') or 'change-me-for-production'

app = Flask(__name__, template_folder='.', static_folder='static')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = DB_PATH

# ---------------- DB helpers ----------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(BASE_DIR, "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            db.executescript(f.read())
        db.commit()

# ---------------- Auth helper ----------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    cur = get_db().execute("SELECT id, username FROM users WHERE id = ?", (uid,))
    return cur.fetchone()

# ---------------- Routes ----------------
@app.route("/")
def home():
    return render_template("home.html", user=current_user())

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("Missing username or password")
            return redirect(url_for("signup"))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("Username already exists")
            return redirect(url_for("signup"))
        flash("Account created. Please login.")
        return redirect(url_for("login"))
    return render_template("signup.html", user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = get_db()
        cur = db.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            flash("Logged in")
            return redirect(url_for("expenses"))
        flash("Invalid credentials")
        return redirect(url_for("login"))
    return render_template("login.html", user=current_user())

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for("home"))

@app.route("/expenses")
def expenses():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    db = get_db()
    cur = db.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user["id"],))
    expenses = cur.fetchall()
    return render_template("expenses.html", user=user, expenses=expenses)

@app.route("/add", methods=["GET", "POST"])
def add_expense():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "POST":
        category = request.form["category"].strip()
        try:
            amount = float(request.form["amount"])
        except ValueError:
            flash("Invalid amount format")
            return redirect(url_for("add_expense"))
        comments = request.form.get("comments", "").strip()
        now = datetime.now(timezone.utc).isoformat()
        db = get_db()
        db.execute(
            "INSERT INTO expenses (user_id, category, amount, comments, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (user["id"], category, amount, comments, now, now),
        )
        db.commit()
        flash("Expense added")
        return redirect(url_for("expenses"))
    return render_template("add_edit.html", user=user, expense=None)

@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    db = get_db()
    cur = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user["id"]))
    expense = cur.fetchone()
    if not expense:
        flash("Not found")
        return redirect(url_for("expenses"))
    if request.method == "POST":
        category = request.form["category"].strip()
        try:
            amount = float(request.form["amount"])
        except ValueError:
            flash("Invalid amount format")
            return redirect(url_for("edit_expense", expense_id=expense_id))
        comments = request.form.get("comments", "").strip()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE expenses SET category=?, amount=?, comments=?, updated_at=? WHERE id=? AND user_id=?",
            (category, amount, comments, now, expense_id, user["id"]),
        )
        db.commit()
        flash("Updated")
        return redirect(url_for("expenses"))
    return render_template("add_edit.html", user=user, expense=expense)

@app.route("/delete/<int:expense_id>")
def delete_expense(expense_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user["id"]))
    db.commit()
    flash("Deleted")
    return redirect(url_for("expenses"))

@app.route("/chart")
def chart_page():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    return render_template("chart.html", user=user)

@app.route("/api/chart_data")
def chart_data():
    user = current_user()
    if not user:
        return jsonify({"labels": [], "values": []})
    db = get_db()
    cur = db.execute("SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ? GROUP BY category", (user["id"],))
    rows = cur.fetchall()
    labels = [r["category"] for r in rows]
    values = [r["total"] for r in rows]
    return jsonify({"labels": labels, "values": values})

# ---------------- Run ----------------
if __name__ == "__main__":
    if not os.path.exists(app.config["DATABASE"]):
        init_db()
        print("Database initialized.")
    app.run(debug=True)
