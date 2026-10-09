"""Weighted, stateful HTTP journeys with response validation and raw request evidence."""

import csv
import json
import os
import random
import time
from pathlib import Path
from uuid import uuid4

from locust import HttpUser, LoadTestShape, constant, events, task
from locust.exception import StopUser

from loadtest.config import Profile

PROFILE = Profile.read(os.getenv("LOAD_PROFILE", "smoke"))
OUTPUT = Path(os.getenv("LOAD_OUTPUT", "results/manual"))
measurement_start = None
started = None
request_file = None
writer = None


@events.test_start.add_listener
def begin(environment, **kwargs):
    global started, measurement_start, request_file, writer
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    measurement_start = started + PROFILE.warmup_seconds
    request_file = (OUTPUT / "requests.csv").open("w", newline="")
    writer = csv.writer(request_file)
    writer.writerow(["timestamp", "method", "route", "latency_ms", "failed", "error"])


@events.request.add_listener
def record(request_type, name, response_time, exception, start_time, **kwargs):
    # Start-time filtering also excludes requests begun in warm-up but completed later.
    if (
        writer is not None
        and measurement_start <= start_time < measurement_start + PROFILE.stages[-1]["until_seconds"]
    ):
        writer.writerow(
            [
                start_time,
                request_type,
                name,
                response_time,
                int(exception is not None),
                str(exception or "")[:180],
            ]
        )


@events.quitting.add_listener
def finish(environment, **kwargs):
    if request_file:
        request_file.close()
    metadata = {
        "profile": PROFILE.name,
        "started": started,
        "measurement_start": measurement_start,
        "finished": time.time(),
        "duration_seconds": PROFILE.duration,
        "thresholds": PROFILE.thresholds,
        "stages": PROFILE.stages,
        "warmup_seconds": PROFILE.warmup_seconds,
        "spawn_rate": PROFILE.spawn_rate,
        "think_seconds": PROFILE.think_seconds,
        "generator_cpu_warning": bool(environment.runner.cpu_warning_emitted),
    }
    (OUTPUT / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")


class Workload(LoadTestShape):
    def tick(self):
        users = PROFILE.users_at(self.get_run_time())
        return (users, PROFILE.spawn_rate) if users is not None else None


class Shopper(HttpUser):
    wait_time = constant(PROFILE.think_seconds)

    def call(self, method, path, route, status=200, check=None, **kwargs):
        with self.client.request(
            method, path, name=route, catch_response=True, timeout=3, **kwargs
        ) as response:
            if response.status_code != status:
                response.failure(f"Expected {status}, got {response.status_code}")
                return None
            if status == 204:
                return {}
            try:
                body = response.json()
                if check and not check(body):
                    response.failure("Response content check failed")
                    return None
                return body
            except (ValueError, KeyError, TypeError):
                response.failure("Response schema check failed")
                return None

    def on_start(self):
        body = self.call(
            "POST",
            "/sessions",
            "/sessions",
            status=201,
            check=lambda b: isinstance(b["token"], str) and len(b["token"]) == 32,
        )
        if body is None:
            raise StopUser()
        self.client.headers["Authorization"] = "Bearer " + body["token"]

    @task(4)
    def browse(self):
        self.call(
            "GET",
            "/products",
            "/products",
            check=lambda b: (
                len(b["items"]) == 24 and all(i["price_cents"] == 1000 + i["id"] * 25 for i in b["items"])
            ),
        )

    @task(1)
    def purchase(self):
        product = random.randint(1, 200)
        detail = self.call(
            "GET",
            f"/products/{product}",
            "/products/[id]",
            check=lambda b: b["id"] == product and b["price_cents"] == 1000 + product * 25,
        )
        if detail is None:
            return
        cart = self.call("POST", "/carts", "/carts", status=201, check=lambda b: isinstance(b["id"], str))
        if cart is None:
            return
        cart_id = cart["id"]
        try:
            added = self.call(
                "POST",
                f"/carts/{cart_id}/items",
                "/carts/[id]/items",
                json={"product_id": product, "quantity": 2},
                check=lambda b: b["product_id"] == product and b["quantity"] == 2,
            )
            if added is None:
                return
            order = self.call(
                "POST",
                f"/carts/{cart_id}/checkout",
                "/carts/[id]/checkout",
                status=201,
                headers={"Idempotency-Key": uuid4().hex},
                check=lambda b: b["total_cents"] == detail["price_cents"] * 2 and isinstance(b["id"], str),
            )
            if order:
                self.call(
                    "GET",
                    f"/orders/{order['id']}",
                    "/orders/[id]",
                    check=lambda b: b["id"] == order["id"] and b["total_cents"] == order["total_cents"],
                )
        finally:
            self.call("DELETE", f"/carts/{cart_id}", "/carts/[id]", status=204)
