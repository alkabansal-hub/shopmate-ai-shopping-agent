"""ShopMate's tools. Each function here is one tool the agent can call (PRD section 7)."""

import os
import sqlite3

from initial_setup.reviews_api import get_ratings_for_products

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_preferences_table():
    """Create the preferences table (FR-23). setup_db.py never touches it, so it survives re-runs (FR-24)."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def get_preferences():
    """Stored preferences as a dict, e.g. {"is_organic": "1", "max_price": "20"}."""
    with _connect() as conn:
        return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM preferences")}


def search_products(keyword, max_price=None, is_organic=None):
    """Keyword search across name, description and category (FR-02), with price and organic filters (FR-03, FR-04).

    Stored preferences are applied on top of whatever the agent asked for (FR-25).
    """
    prefs = get_preferences()

    organic_only = is_organic == "yes" or prefs.get("is_organic") == "1"
    caps = [float(p) for p in (max_price, prefs.get("max_price")) if p is not None]
    price_cap = min(caps) if caps else None

    sql = "SELECT id, name, category, price, is_organic FROM products WHERE (name LIKE ? OR description LIKE ? OR category LIKE ?)"
    params = [f"%{keyword}%"] * 3
    if price_cap is not None:
        sql += " AND price <= ?"
        params.append(price_cap)
    if organic_only:
        sql += " AND is_organic = 1"
    sql += " ORDER BY id"

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

        result = {
            "filters_applied": {"keyword": keyword, "max_price": price_cap, "organic_only": organic_only},
            "products": [
                {"id": r["id"], "name": r["name"], "category": r["category"], "price": r["price"], "is_organic": bool(r["is_organic"])}
                for r in rows
            ],
        }

        if not rows:
            # Tell the agent whether the store sells this kind of product at all, or only the filters ruled it out.
            keyword_only = conn.execute(
                "SELECT COUNT(*) FROM products WHERE name LIKE ? OR description LIKE ? OR category LIKE ?",
                [f"%{keyword}%"] * 3,
            ).fetchone()[0]
            result["store_sells_this_kind_of_product"] = keyword_only > 0
            result["available_categories"] = list_categories()

    return result


def list_categories():
    """The store's product categories, in catalogue order (FR-26)."""
    with _connect() as conn:
        return [r["category"] for r in conn.execute("SELECT category FROM products GROUP BY category ORDER BY MIN(id)")]


def get_products_by_id(product_ids):
    """Products keyed by ID, used to check a reply against the store data (GR-03)."""
    if not product_ids:
        return {}
    placeholders = ",".join("?" * len(product_ids))
    with _connect() as conn:
        rows = conn.execute(f"SELECT id, name, price FROM products WHERE id IN ({placeholders})", list(product_ids)).fetchall()
    return {r["id"]: dict(r) for r in rows}


def get_rating(product_ids):
    """Average rating and review count per product, only ever from the reviews API (FR-06, FR-09, GR-05).

    Takes every candidate at once so the agent fetches all ratings in one step.
    """
    return {"ratings": get_ratings_for_products([int(i) for i in product_ids])}


def checkout(product_id, shown_product_ids):
    """Place an order for one product (FR-18).

    GR-02 is enforced here: the ID must be one the agent showed in its most recent product list.
    Name and price come from the products table, never from the model.
    """
    product_id = int(product_id)
    if product_id not in shown_product_ids:
        return {
            "error": f"Product ID {product_id} was not in the list shown to the shopper, so no order was placed. "
                     "Ask the shopper to pick a product from the list."
        }

    with _connect() as conn:
        product = conn.execute("SELECT id, name, price FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return {"error": f"There is no product with ID {product_id}. No order was placed."}
        cursor = conn.execute(
            "INSERT INTO orders (product_id, product_name, price) VALUES (?, ?, ?)",
            (product["id"], product["name"], product["price"]),
        )
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return {
        "order_id": order["id"],
        "product_id": order["product_id"],
        "product_name": order["product_name"],
        "price": order["price"],
        "ordered_at": order["ordered_at"],
    }


def get_order_history():
    """Everything the shopper has ordered before, oldest first (FR-22)."""
    with _connect() as conn:
        rows = conn.execute("SELECT id, product_id, product_name, price, ordered_at FROM orders ORDER BY id").fetchall()
    return {"orders": [dict(r) for r in rows]}
