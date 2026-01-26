import time
import requests
from multiprocessing import Process
import pytest


def _run_app():
    # Import inside function to avoid importing app at module import time
    from app import app

    # Run without the reloader so we don't spawn extra processes
    app.run(host="127.0.0.1", port=5001, use_reloader=False, threaded=True)


@pytest.fixture(scope="session", autouse=True)
def server():
    p = Process(target=_run_app)
    p.daemon = True
    p.start()

    # Wait for the server to be up
    timeout = 10.0
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get("http://127.0.0.1:5001/", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        pytest.skip("Could not start test server on 127.0.0.1:5001")

    yield

    # Teardown
    try:
        p.terminate()
        p.join(timeout=5)
    except Exception:
        pass
