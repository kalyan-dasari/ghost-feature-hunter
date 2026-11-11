"""Deliberately broken Flask shop used as a local verification benchmark.

This app is intentionally insecure and should only run on loopback with synthetic data.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

PRODUCTS = (
    (1, "Trail Socks", 500, 10),
    (2, "Day Pack", 2500, 20),
)


def _connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL, stock INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, email TEXT NOT NULL, state TEXT NOT NULL,
                subtotal_cents INTEGER NOT NULL, payment_status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                order_id TEXT NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY, order_id TEXT, kind TEXT);
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO products (id, name, price_cents, stock) VALUES (?, ?, ?, ?)", PRODUCTS
        )
        connection.execute(
            """INSERT OR IGNORE INTO orders
               (id, user_id, email, state, subtotal_cents, payment_status, created_at)
               VALUES ('seed-order-alice', 'alice', 'alice@example.test', 'confirmed', 500, 'paid', ?)""",
            (datetime.now(UTC).isoformat(),),
        )
        connection.commit()
    finally:
        connection.close()


def create_app(database_path: str | Path | None = None) -> Flask:
    demo_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(demo_dir / "templates"),
        static_folder=str(demo_dir / "static"),
    )
    default_path = Path(__file__).parent / "instance" / "broken-shop.sqlite3"
    chosen_path = str(database_path or os.environ.get("GHOST_SHOP_DB") or default_path)
    app.config.update(DATABASE=chosen_path, TESTING=False)
    _initialize(chosen_path)

    def db() -> sqlite3.Connection:
        if "shop_db" not in g:
            g.shop_db = _connect(app.config["DATABASE"])
        return g.shop_db

    @app.teardown_appcontext
    def close_db(_error=None):
        connection = g.pop("shop_db", None)
        if connection is not None:
            connection.close()

    @app.get("/")
    def storefront():
        return render_template("index.html")

    @app.get("/api/products")
    def products():
        rows = db().execute("SELECT id, name, price_cents, stock FROM products ORDER BY id").fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/api/cart/calculate")
    def calculate_cart():
        payload = request.get_json(silent=True) or {}
        items = payload.get("items", [])
        subtotal = 0
        for item in items:
            product = db().execute("SELECT price_cents FROM products WHERE id = ?", (item.get("product_id"),)).fetchone()
            if product:
                subtotal += int(product["price_cents"]) * int(item.get("quantity", 1))
        tax = round(subtotal * 0.10)
        total = subtotal + tax + tax  # Defect: tax is applied twice.
        return jsonify({"subtotal_cents": subtotal, "tax_cents": tax, "total_cents": total})

    @app.post("/api/drafts")
    def create_draft():
        payload = request.get_json(silent=True) or {}
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        # Defect: returns success but never inserts into drafts.
        return jsonify({"ok": True, "draft_id": draft_id, "saved": True}), 201

    @app.get("/api/orders")
    def list_orders():
        user_id = request.args.get("user_id", "guest")
        rows = db().execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
        # Defect: no authentication is required.
        return jsonify([dict(row) for row in rows])

    @app.get("/api/orders/<order_id>")
    def get_order(order_id: str):
        row = db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        # Defect: the caller's identity/ownership is ignored.
        return jsonify(dict(row))

    @app.patch("/api/orders/<order_id>/state")
    def change_order_state(order_id: str):
        payload = request.get_json(silent=True) or {}
        state = payload.get("state", "")
        # Defect: accepts any transition and any state string.
        cursor = db().execute("UPDATE orders SET state = ? WHERE id = ?", (state, order_id))
        db().commit()
        if not cursor.rowcount:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True, "state": state})

    @app.post("/api/checkout")
    def checkout():
        order_id = f"order-{uuid.uuid4().hex[:10]}"
        try:
            payload = request.get_json(silent=True) or {}
            items = payload.get("items", [])
            # Defects: no auth, email/address validation, empty-cart validation, or quantity validation.
            user_id = str(payload.get("user_id", "guest"))
            email = str(payload.get("email", ""))
            subtotal = 0
            prepared_items = []
            for item in items:
                product_id = int(item.get("product_id"))
                quantity = int(item.get("quantity", 1))
                product = db().execute(
                    "SELECT price_cents FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if product:
                    subtotal += int(product["price_cents"]) * quantity
                    prepared_items.append((product_id, quantity))
            # Defect: failed payments are recorded as successful.
            payment_status = "paid"
            db().execute(
                """INSERT INTO orders
                   (id, user_id, email, state, subtotal_cents, payment_status, created_at)
                   VALUES (?, ?, ?, 'confirmed', ?, ?, ?)""",
                (order_id, user_id, email, subtotal, payment_status, datetime.now(UTC).isoformat()),
            )
            for product_id, quantity in prepared_items:
                db().execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                    (order_id, product_id, quantity),
                )
            db().commit()  # Defect: the order commits before stock updates (a partial transaction).

            if payload.get("simulate_inventory_error"):
                raise RuntimeError("simulated inventory write failure")

            for product_id, _quantity in prepared_items:
                # Defect: subtracts one unit regardless of the requested quantity.
                db().execute("UPDATE products SET stock = MAX(stock - 1, 0) WHERE id = ?", (product_id,))
            db().commit()
            # Defect: no notification record is created.
            # Defect: repeated idempotency keys are accepted as new orders.
            return jsonify({
                "ok": True,
                "order_id": order_id,
                "state": "confirmed",
                "payment_status": payment_status,
                "subtotal_cents": subtotal,
                "items": prepared_items,
            }), 201
        except Exception as exc:
            # Defect: errors are reported as successful HTTP 200 responses with internal detail.
            db().commit()
            return jsonify({"ok": True, "order_id": order_id, "state": "confirmed", "debug": repr(exc)}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
