"""Own the server process and database; never reset an existing stand."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def stand(mode="fixed", log=None):
    with tempfile.TemporaryDirectory(prefix="load-shop-") as data:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "APP_MODE": mode, "SHOP_DB": data + "/shop.sqlite"}
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            cwd=ROOT,
            stdout=log or subprocess.DEVNULL,
            stderr=log or subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Shop exited during startup; inspect server.log")
                    try:
                        if client.get(url + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Shop did not become ready")
            yield url
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
