# Ensure test runner can import project top-level modules like `app` and `tasks`.
# Some CI environments or local pytest invocations do not automatically add
# the repository root to sys.path. Insert it explicitly at test collection.
import os
import sys

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


import pytest  # noqa: E402
from app import app as flask_app  # noqa: E402
import tasks  # ensure module is importable during test collection  # noqa: F401,E402


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
