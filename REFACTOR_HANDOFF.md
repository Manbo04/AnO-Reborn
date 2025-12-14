# Refactor Handoff - Next Iteration

## Current Status
✅ **Committed**: All work from partial iteration complete
- Commit hash: `2ad6a780`
- Branch: `master`
- Latest push: Ready to go

## What's Working Now ✅
1. **App boots and serves pages** - Full Flask app operational
2. **Coalitions module has psycopg2 import** - Ready for context manager migration
3. **DB context manager pattern established** in `database.py`:
   ```python
   @contextmanager
   def get_db_cursor():
       conn = psycopg2.connect(...)
       cur = conn.cursor()
       try:
           yield cur
       finally:
           cur.close()
           conn.close()
   ```
4. **Traceback logging in 500 handler** - app.py error handler includes logging
5. **upgrades dict fix** - upgrades.py initialization corrected
6. **Partial migrations completed**:
   - `change.py` - context manager pattern applied
   - `login.py` - context manager pattern applied
   - `policies.py` - context manager pattern applied
   - `wars.py` - partial migration (some calls updated)

---

## TODO for Next Agent (Priority Order)

### 1. Replace Raw psycopg2.connect() Calls (16 total)

#### `coalitions.py` - 11 calls
**Lines**: 551, 584, 654, 746, 836, 887, 915, 954, 1011, 1055, 1082

Pattern to replace:
```python
# OLD
conn = psycopg2.connect(host=PG_HOST, database=PG_DATABASE, user=PG_USER, password=PG_PASSWORD)
cur = conn.cursor()
# ... code ...
cur.close()
conn.close()

# NEW
from contextlib import contextmanager
from database import get_db_cursor

with get_db_cursor() as cur:
    # ... code ...
```

#### `military.py` - 1 call
**Line**: 41

#### `wars.py` - 4 additional calls
Beyond what was partially updated - check for remaining raw `psycopg2.connect()` calls

**Verification**: After migration, run:
```bash
grep -n "psycopg2.connect" coalitions.py military.py wars.py
# Should return: 0 results (except import statements)
```

---

### 2. Tighten Error Handling

**Current issue**: Broad `except:` clauses without specific exceptions

**Locations to check**:
- Look for `except:` and `except Exception:`
- Replace with specific exceptions: `psycopg2.DatabaseError`, `psycopg2.IntegrityError`, `ValueError`, etc.
- Add logging to error handlers using Python's `logging` module

**Pattern**:
```python
import logging
logger = logging.getLogger(__name__)

try:
    # database operation
except psycopg2.DatabaseError as e:
    logger.error(f"Database error: {e}", exc_info=True)
    # handle error
```

---

### 3. Add Type Hints

**Priority files**:
1. `helpers.py` - All functions need type annotations
2. `database.py` - DB functions need type hints
3. Other core modules as time permits

**Pattern**:
```python
def get_user_data(user_id: int) -> dict:
    """Fetch user data from database."""
    # ...

def validate_input(value: str) -> bool:
    """Validate user input."""
    # ...
```

---

### 4. Create Pytest Smoke Tests

**Target routes**:
- `/login` - POST with valid/invalid credentials
- `/signup` - POST with valid/invalid data
- `/provinces` - GET authenticated access
- `/upgrades` - GET authenticated access

**Test file**: `tests/test_smoke.py`

**Pattern**:
```python
import pytest
from app import app

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_login_get(client):
    """Test /login GET returns login page."""
    response = client.get('/login')
    assert response.status_code == 200

def test_login_post_valid(client):
    """Test /login POST with valid credentials."""
    # ...

def test_signup_get(client):
    """Test /signup GET returns signup page."""
    # ...
```

---

## Key Files Modified This Iteration
- `change.py` - ✅ Migrated
- `login.py` - ✅ Migrated
- `policies.py` - ✅ Migrated
- `wars.py` - ⚠️ Partially migrated
- `database.py` - ✅ Context manager added
- `app.py` - ✅ Error handler improved

## Key Files TO DO Next
- `coalitions.py` - **HIGH PRIORITY** (11 calls)
- `military.py` - (1 call)
- `wars.py` - (4+ remaining calls)
- `helpers.py` - Type hints
- `database.py` - Type hints
- New: `tests/test_smoke.py` - Smoke tests

---

## Testing Before Next Commit
1. Boot app: `python app.py`
2. Test a protected route: `curl http://localhost:5000/provinces`
3. Verify no database connection errors in logs
4. Run smoke tests (once created): `pytest tests/test_smoke.py -v`

---

## Notes for Next Agent
- The `get_db_cursor()` pattern is stable and ready to use everywhere
- Database config is in `config.py` - already handling `DATABASE_URL` parsing
- Most of the refactor is mechanical (find/replace patterns)
- Token limit for this iteration was approached - that's why we're splitting
- Focus on coalitions.py first (11 calls is most of the remaining work)
- After coalitions.py done, tests will be easier to write
