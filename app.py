from __future__ import annotations

import base64
import io
import os
import secrets
import sqlite3
from pathlib import Path

import qrcode
from flask import Flask, abort, flash, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "marketqr.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-in-production")


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner_name TEXT,
                contact TEXT,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                image_url TEXT,
                FOREIGN KEY(store_id) REFERENCES stores(id)
            );
        """)


def get_store_or_404(slug: str):
    with db() as conn:
        store = conn.execute("SELECT * FROM stores WHERE slug = ?", (slug,)).fetchone()
    if not store:
        abort(404)
    return store


def qr_data_uri(link: str) -> str:
    image = qrcode.make(link)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/create", methods=["GET", "POST"])
def create_store():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Your business name is required.", "error")
            return render_template("create_store.html")
        slug = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].lower()
        with db() as conn:
            conn.execute(
                "INSERT INTO stores (slug, name, owner_name, contact, description) VALUES (?, ?, ?, ?, ?)",
                (slug, name, request.form.get("owner_name", "").strip(), request.form.get("contact", "").strip(), request.form.get("description", "").strip()),
            )
        return redirect(url_for("manage_store", slug=slug))
    return render_template("create_store.html")


@app.route("/manage/<slug>", methods=["GET", "POST"])
def manage_store(slug: str):
    store = get_store_or_404(slug)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        if not name or not price:
            flash("Item name and price are required.", "error")
        else:
            try:
                value = float(price)
                if value < 0:
                    raise ValueError
                with db() as conn:
                    conn.execute("INSERT INTO items (store_id, name, price, description, image_url) VALUES (?, ?, ?, ?, ?)",
                                 (store["id"], name, value, request.form.get("description", "").strip(), request.form.get("image_url", "").strip()))
                flash("Item added to your storefront.", "success")
                return redirect(url_for("manage_store", slug=slug))
            except ValueError:
                flash("Use a valid non-negative price.", "error")
    with db() as conn:
        items = conn.execute("SELECT * FROM items WHERE store_id = ? ORDER BY id DESC", (store["id"],)).fetchall()
    store_url = url_for("storefront", slug=slug, _external=True)
    return render_template("manage.html", store=store, items=items, store_url=store_url, qr_image=qr_data_uri(store_url))


@app.post("/manage/<slug>/items/<int:item_id>/delete")
def delete_item(slug: str, item_id: int):
    store = get_store_or_404(slug)
    with db() as conn:
        conn.execute("DELETE FROM items WHERE id = ? AND store_id = ?", (item_id, store["id"]))
    flash("Item removed.", "success")
    return redirect(url_for("manage_store", slug=slug))


@app.route("/store/<slug>")
def storefront(slug: str):
    store = get_store_or_404(slug)
    with db() as conn:
        items = conn.execute("SELECT * FROM items WHERE store_id = ? ORDER BY id DESC", (store["id"],)).fetchall()
    return render_template("storefront.html", store=store, items=items)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
