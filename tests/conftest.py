import os
import subprocess
import time
import requests
import pytest


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Start the local Flask app on port 5001 for integration tests that use requests."""
    env = os.environ.copy()
    env["PORT"] = "5001"
    env["FLASK_ENV"] = "development"

    # Start the app.py using the project's venv python
    p = subprocess.Popen(["venv310/bin/python", "app.py"], env=env)

    # Wait until server is ready (simple HTTP poll)
    try:
        for _ in range(40):
            try:
                r = requests.get("http://127.0.0.1:5001/", timeout=1)
                if r.status_code in (200, 302, 404):
                    break
            except Exception:
                time.sleep(0.25)
        else:
            p.kill()
            raise RuntimeError("Failed to start local server for tests on port 5001")

        yield

    finally:
        # Shutdown the server process
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
