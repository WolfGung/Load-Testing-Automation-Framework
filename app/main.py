"""A local shop with a bounded price-service pool and two catalogue implementations."""

import asyncio
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class PriceService:
    """Model downstream I/O; the pool, latency and timeout are identical in both modes."""

    def __init__(self, slots=8, delay=0.01, timeout=0.10):
        self.pool = asyncio.Semaphore(slots)
        self.delay, self.timeout = delay, timeout
        self.calls = self.active = self.waiting = self.timeouts = self.peak_active = 0
        self.wait_seconds = 0.0

    async def fetch(self, ids):
        started = time.perf_counter()
        self.waiting += 1
        try:
            await asyncio.wait_for(self.pool.acquire(), self.timeout)
        except TimeoutError:
            self.timeouts += 1
            raise HTTPException(503, "Price service pool exhausted") from None
        finally:
            self.waiting -= 1
            self.wait_seconds += time.perf_counter() - started
        self.calls += 1
        self.active += 1
        self.peak_active = max(self.active, self.peak_active)
        try:
            await asyncio.sleep(self.delay)
            return {i: 1000 + i * 25 for i in ids}
        finally:
            self.active -= 1
            self.pool.release()


def create_app(mode=None, database=None):
    mode = mode or os.getenv("APP_MODE", "fixed")
    if mode not in ("broken", "fixed"):
        raise ValueError("APP_MODE must be broken or fixed")
    database = database or os.getenv("SHOP_DB", ":memory:")
    prices = PriceService()
    sessions = set()
    db = sqlite3.connect(database, check_same_thread=False)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS carts(id TEXT PRIMARY KEY, owner TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS items(cart TEXT, product INTEGER, quantity INTEGER,
            PRIMARY KEY(cart, product));
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, owner TEXT, cart TEXT UNIQUE,
            total INTEGER, key TEXT, UNIQUE(owner, key));
    """)
    db.executemany(
        "INSERT OR IGNORE INTO products VALUES (?, ?)", [(i, f"Workshop item {i:03d}") for i in range(1, 201)]
    )
    db.commit()

    @asynccontextmanager
    async def lifespan(application):
        yield
        db.close()

    app = FastAPI(title="Workshop Shop", lifespan=lifespan)
    app.state.prices = prices
    app.state.db = db
    process = psutil.Process()
    process.cpu_percent()

    def user(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ")
        if token not in sessions:
            raise HTTPException(401, "Unknown session")
        return token

    def cart_owner(cart, owner):
        row = db.execute("SELECT owner FROM carts WHERE id=?", (cart,)).fetchone()
        if not row or row[0] != owner:
            raise HTTPException(404, "Cart not found")

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": mode}

    @app.get("/metrics")
    async def metrics():
        return {
            "mode": mode,
            "price_calls": prices.calls,
            "pool_active": prices.active,
            "pool_waiting": prices.waiting,
            "pool_timeouts": prices.timeouts,
            "pool_peak_active": prices.peak_active,
            "pool_wait_seconds": prices.wait_seconds,
            "rss_bytes": process.memory_info().rss,
            "cpu_percent": process.cpu_percent(),
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "carts": db.execute("SELECT COUNT(*) FROM carts").fetchone()[0],
            "database_bytes": Path(database).stat().st_size if database != ":memory:" else 0,
        }

    @app.post("/sessions", status_code=201)
    async def login():
        token = uuid4().hex
        sessions.add(token)
        return {"token": token}

    @app.get("/products")
    async def products():
        rows = db.execute("SELECT id,name FROM products ORDER BY id LIMIT 24").fetchall()
        ids = [r[0] for r in rows]
        if mode == "broken":
            quotes = {}
            for i in ids:
                quotes.update(await prices.fetch([i]))
        else:
            quotes = await prices.fetch(ids)
        return {"items": [{"id": i, "name": name, "price_cents": quotes[i]} for i, name in rows]}

    @app.get("/products/{product}")
    async def detail(product: int):
        row = db.execute("SELECT name FROM products WHERE id=?", (product,)).fetchone()
        if not row:
            raise HTTPException(404, "Product not found")
        quote = await prices.fetch([product])
        return {"id": product, "name": row[0], "price_cents": quote[product]}

    @app.post("/carts", status_code=201)
    async def create_cart(owner: str = Depends(user)):
        cart = uuid4().hex
        db.execute("INSERT INTO carts VALUES (?,?)", (cart, owner))
        db.commit()
        return {"id": cart}

    class Item(BaseModel):
        product_id: int = Field(ge=1, le=200)
        quantity: int = Field(ge=1, le=5)

    @app.post("/carts/{cart}/items")
    async def add_item(cart: str, item: Item, owner: str = Depends(user)):
        cart_owner(cart, owner)
        db.execute(
            "INSERT INTO items VALUES (?,?,?) ON CONFLICT(cart,product) "
            "DO UPDATE SET quantity=excluded.quantity",
            (cart, item.product_id, item.quantity),
        )
        db.commit()
        return {"product_id": item.product_id, "quantity": item.quantity}

    @app.post("/carts/{cart}/checkout", status_code=201)
    async def checkout(
        cart: str, owner: str = Depends(user), idempotency_key: str = Header(min_length=1, max_length=128)
    ):
        cart_owner(cart, owner)
        previous = db.execute(
            "SELECT id,total,cart FROM orders WHERE owner=? AND key=?", (owner, idempotency_key)
        ).fetchone()
        if previous:
            if previous[2] != cart:
                raise HTTPException(409, "Key used for another cart")
            return {"id": previous[0], "total_cents": previous[1]}
        rows = db.execute("SELECT product,quantity FROM items WHERE cart=?", (cart,)).fetchall()
        if not rows:
            raise HTTPException(422, "Empty cart")
        quotes = await prices.fetch([r[0] for r in rows])
        total = sum(quotes[i] * qty for i, qty in rows)
        order = uuid4().hex
        # No await within the write transaction. The database also enforces idempotency.
        try:
            db.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (order, owner, cart, total, idempotency_key))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            previous = db.execute(
                "SELECT id,total,cart FROM orders WHERE owner=? AND key=?", (owner, idempotency_key)
            ).fetchone()
            if not previous:
                raise HTTPException(409, "Cart already checked out") from None
            if previous[2] != cart:
                raise HTTPException(409, "Key used for another cart") from None
            return {"id": previous[0], "total_cents": previous[1]}
        return {"id": order, "total_cents": total}

    @app.get("/orders/{order}")
    async def read_order(order: str, owner: str = Depends(user)):
        row = db.execute("SELECT total FROM orders WHERE id=? AND owner=?", (order, owner)).fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        return {"id": order, "total_cents": row[0]}

    @app.delete("/carts/{cart}", status_code=204)
    async def delete_cart(cart: str, owner: str = Depends(user)):
        cart_owner(cart, owner)
        db.execute("DELETE FROM items WHERE cart=?", (cart,))
        db.execute("DELETE FROM carts WHERE id=?", (cart,))
        db.commit()

    return app
