import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import PriceService, create_app


@pytest.mark.parametrize("mode", ["broken", "fixed"])
def test_catalogue_has_identical_prices_and_different_dependency_call_counts(mode):
    app = create_app(mode)
    with TestClient(app) as client:
        response = client.get("/products")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 24
        assert all(i["price_cents"] == 1000 + i["id"] * 25 for i in items)
        assert app.state.prices.calls == (24 if mode == "broken" else 1)


def session(client):
    return {"Authorization": "Bearer " + client.post("/sessions").json()["token"]}


def test_checkout_is_isolated_correct_and_idempotent():
    with TestClient(create_app("fixed")) as client:
        owner, stranger = session(client), session(client)
        cart = client.post("/carts", headers=owner).json()["id"]
        path = f"/carts/{cart}"
        assert (
            client.post(path + "/items", headers=stranger, json={"product_id": 1, "quantity": 2}).status_code
            == 404
        )
        assert (
            client.post(path + "/items", headers=owner, json={"product_id": 1, "quantity": 2}).status_code
            == 200
        )
        headers = {**owner, "Idempotency-Key": "first-order"}
        one = client.post(path + "/checkout", headers=headers)
        two = client.post(path + "/checkout", headers=headers)
        assert one.status_code == two.status_code == 201
        assert one.json() == two.json()
        assert one.json()["total_cents"] == 2050
        order_path = "/orders/" + one.json()["id"]
        assert client.get(order_path, headers=owner).json() == one.json()
        assert client.get(order_path, headers=stranger).status_code == 404
        assert client.get("/metrics").json()["orders"] == 1
        assert client.delete(path, headers=owner).status_code == 204
        assert client.get("/metrics").json()["carts"] == 0


def test_authentication_validation_and_empty_cart():
    with TestClient(create_app()) as client:
        assert client.post("/carts").status_code == 401
        owner = session(client)
        cart = client.post("/carts", headers=owner).json()["id"]
        assert (
            client.post(
                f"/carts/{cart}/items", headers=owner, json={"product_id": 999, "quantity": 0}
            ).status_code
            == 422
        )
        assert client.post(f"/carts/{cart}/checkout", headers=owner).status_code == 422
        assert (
            client.post(f"/carts/{cart}/checkout", headers={**owner, "Idempotency-Key": "empty"}).status_code
            == 422
        )
        assert client.get("/products/999").status_code == 404


def test_pool_exhaustion_is_visible_and_slots_are_released():
    async def exercise():
        pool = PriceService(slots=1, delay=0.04, timeout=0.005)
        result = await asyncio.gather(pool.fetch([1]), pool.fetch([2]), return_exceptions=True)
        assert sum(isinstance(r, HTTPException) for r in result) == 1
        assert pool.timeouts == 1
        assert pool.active == pool.waiting == 0
        assert await pool.fetch([3]) == {3: 1075}

    asyncio.run(exercise())


def test_concurrent_checkout_creates_one_order():
    async def exercise():
        app = create_app("fixed")
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://shop") as c:
            owner = {"Authorization": "Bearer " + (await c.post("/sessions")).json()["token"]}
            cart = (await c.post("/carts", headers=owner)).json()["id"]
            await c.post(f"/carts/{cart}/items", headers=owner, json={"product_id": 1, "quantity": 2})
            headers = {**owner, "Idempotency-Key": "concurrent"}
            orders = await asyncio.gather(
                *[c.post(f"/carts/{cart}/checkout", headers=headers) for _ in range(5)]
            )
            assert all(r.status_code == 201 for r in orders)
            assert len({r.json()["id"] for r in orders}) == 1
            assert (await c.get("/metrics")).json()["orders"] == 1
        app.state.db.close()

    asyncio.run(exercise())
