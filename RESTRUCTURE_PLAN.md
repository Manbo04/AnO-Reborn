# Complete Code Restructure Plan — Fixing Loading Times

## Executive Summary

The current architecture has several systemic issues causing slow page loads:
1. **N+1 query patterns** — fetching data in loops instead of batch queries
2. **No request-level caching** — same data fetched multiple times per request
3. **Monolithic route files** — 700+ line files mixing DB, logic, and presentation
4. **Synchronous blocking** — all DB work happens in the request thread
5. **Missing database indexes** — slow scans on large tables

**Goal**: Reduce page load times from 3-15 seconds to under 500ms.

---

## Phase 1: Database Layer (Week 1)

### 1.1 Add Missing Indexes
```bash
python scripts/add_database_indexes.py
```

Critical indexes to create:
```sql
CREATE INDEX IF NOT EXISTS idx_provinces_userid ON provinces(userId);
CREATE INDEX IF NOT EXISTS idx_proinfra_id ON proInfra(id);
CREATE INDEX IF NOT EXISTS idx_military_id ON military(id);
CREATE INDEX IF NOT EXISTS idx_resources_id ON resources(id);
CREATE INDEX IF NOT EXISTS idx_stats_id ON stats(id);
CREATE INDEX IF NOT EXISTS idx_upgrades_userid ON upgrades(user_id);
CREATE INDEX IF NOT EXISTS idx_offers_userid ON offers(user_id);
CREATE INDEX IF NOT EXISTS idx_wars_attacker ON wars(attacker);
CREATE INDEX IF NOT EXISTS idx_wars_defender ON wars(defender);
CREATE INDEX IF NOT EXISTS idx_coalitions_userid ON coalitions(userId);
```

### 1.2 Create Composite Indexes for Common Joins
```sql
CREATE INDEX IF NOT EXISTS idx_provinces_userid_id ON provinces(userId, id);
CREATE INDEX IF NOT EXISTS idx_offers_resource_type ON offers(resource, type);
```

### 1.3 Analyze and Vacuum Tables
```sql
VACUUM ANALYZE provinces;
VACUUM ANALYZE proInfra;
VACUUM ANALYZE military;
VACUUM ANALYZE resources;
VACUUM ANALYZE stats;
```

---

## Phase 2: Data Access Layer (Week 1-2)

### 2.1 Create Repository Pattern

**New file: `repositories/__init__.py`**
```python
# Centralized data access with built-in caching
```

**New file: `repositories/user_repository.py`**
```python
from database import get_db_cursor, query_cache
from psycopg2.extras import RealDictCursor

class UserRepository:
    """All user-related database operations"""

    @staticmethod
    def get_full_user_data(user_id: int) -> dict:
        """Single query to get all user data needed for most pages"""
        cache_key = f"user_full_{user_id}"
        cached = query_cache.get(cache_key)
        if cached:
            return cached

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute("""
                SELECT
                    u.id, u.username, u.flag, u.date,
                    s.gold, s.location, s.governmentType,
                    m.soldiers, m.tanks, m.artillery, m.fighters, m.bombers,
                    m.apaches, m.destroyers, m.cruisers, m.submarines,
                    m.spies, m.ICBMs, m.nukes, m.manpower,
                    r.*
                FROM users u
                LEFT JOIN stats s ON u.id = s.id
                LEFT JOIN military m ON u.id = m.id
                LEFT JOIN resources r ON u.id = r.id
                WHERE u.id = %s
            """, (user_id,))
            result = dict(db.fetchone() or {})

        query_cache.set(cache_key, result)
        return result

    @staticmethod
    def get_provinces_summary(user_id: int) -> list:
        """Get all provinces for a user in one query"""
        cache_key = f"provinces_summary_{user_id}"
        cached = query_cache.get(cache_key)
        if cached:
            return cached

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute("""
                SELECT p.*, pi.*
                FROM provinces p
                LEFT JOIN proInfra pi ON p.id = pi.id
                WHERE p.userId = %s
                ORDER BY p.id
            """, (user_id,))
            result = [dict(row) for row in db.fetchall()]

        query_cache.set(cache_key, result)
        return result

    @staticmethod
    def invalidate_user_cache(user_id: int):
        """Clear all cached data for a user after mutations"""
        query_cache.invalidate(f"user_full_{user_id}")
        query_cache.invalidate(f"provinces_summary_{user_id}")
        query_cache.invalidate(f"influence_{user_id}")
        query_cache.invalidate(f"econ_stats_{user_id}")
        query_cache.invalidate(f"revenue_{user_id}")
```

**New file: `repositories/province_repository.py`**
```python
class ProvinceRepository:
    """Province-related database operations"""

    @staticmethod
    def get_province_with_infrastructure(province_id: int) -> dict:
        """Single query for province page data"""
        # ... implementation

    @staticmethod
    def get_user_provinces_with_stats(user_id: int) -> list:
        """All provinces with calculated stats"""
        # ... implementation
```

### 2.2 Create Request-Scoped Cache

**Update `database.py`** — Add request-level caching:
```python
from flask import g

def get_request_cache():
    """Per-request cache that lives for one HTTP request"""
    if not hasattr(g, '_request_cache'):
        g._request_cache = {}
    return g._request_cache

def request_cached(key_prefix):
    """Decorator for request-level caching"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_request_cache()
            key = f"{key_prefix}_{args}_{kwargs}"
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        return wrapper
    return decorator
```

---

## Phase 3: Route Refactoring (Week 2-3)

### 3.1 Split Monolithic Files

Current structure (problematic):
```
countries.py     # 795 lines - mixed concerns
province.py      # 571 lines - repeated queries
military.py      # 233 lines - some N+1 patterns
market.py        # 777 lines - complex query logic
```

New structure:
```
routes/
├── __init__.py
├── countries.py      # Just route handlers (~100 lines)
├── provinces.py      # Just route handlers (~100 lines)
├── military.py       # Just route handlers (~80 lines)
├── market.py         # Just route handlers (~150 lines)

services/
├── __init__.py
├── country_service.py    # Business logic
├── province_service.py   # Business logic
├── military_service.py   # Business logic
├── market_service.py     # Business logic

repositories/
├── __init__.py
├── user_repository.py
├── province_repository.py
├── market_repository.py
```

### 3.2 Example Refactored Route

**Before (`province.py` — current):**
```python
@bp.route("/province/<pId>", methods=["GET"])
@login_required
def province(pId):
    with get_db_cursor() as db:
        # 10+ separate queries...
        db.execute("SELECT ... FROM provinces WHERE id=%s", (pId,))
        db.execute("SELECT ... FROM stats WHERE id=%s", (cId,))
        db.execute("SELECT ... FROM resources WHERE id=%s", (cId,))
        db.execute("SELECT * FROM proInfra WHERE id=%s", (pId,))
        # ... more queries
```

**After (`routes/provinces.py` — refactored):**
```python
from services.province_service import ProvinceService

@bp.route("/province/<pId>", methods=["GET"])
@login_required
@cache_response(ttl_seconds=15)
def province(pId):
    user_id = session["user_id"]

    # Single service call that batches all queries
    data = ProvinceService.get_province_page_data(pId, user_id)

    if not data:
        return error(404, "Province doesn't exist")

    return render_template("province.html", **data)
```

**New service (`services/province_service.py`):**
```python
class ProvinceService:
    @staticmethod
    def get_province_page_data(province_id: int, user_id: int) -> dict:
        """Fetch ALL data needed for province page in minimal queries"""
        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            # ONE query to get province + infrastructure + user resources
            db.execute("""
                SELECT
                    p.*,
                    pi.*,
                    r.consumer_goods, r.rations,
                    s.location,
                    u.upgrades_json
                FROM provinces p
                LEFT JOIN proInfra pi ON p.id = pi.id
                LEFT JOIN resources r ON p.userId = r.id
                LEFT JOIN stats s ON p.userId = s.id
                LEFT JOIN (
                    SELECT user_id, json_agg(upgrade_name) as upgrades_json
                    FROM upgrades
                    GROUP BY user_id
                ) u ON p.userId = u.user_id
                WHERE p.id = %s
            """, (province_id,))

            result = db.fetchone()
            if not result:
                return None

            # Process and return template-ready data
            return {
                'province': dict(result),
                'own': result['userId'] == user_id,
                'energy': calculate_energy(result),
                # ... other computed values
            }
```

---

## Phase 4: Slow Page Fixes (Week 3)

### 4.1 Countries Page (`/countries`)
**Current issue**: Loads all users, calculates influence per user
**Fix**: Already has pagination — ensure batch influence loading works

```python
# Verify this optimization is active in countries.py
def countries():
    # Get page of users FIRST (50 at a time)
    users = get_paginated_users(page, per_page=50)

    # Batch load influence for just those 50 users
    user_ids = [u['id'] for u in users]
    influences = batch_get_influences(user_ids)  # Single query

    # Merge and return
    for user in users:
        user['influence'] = influences.get(user['id'], 0)
```

### 4.2 Province Page (`/province/<id>`)
**Current issue**: 10+ queries per page load
**Fix**: Single joined query

| Before | After |
|--------|-------|
| SELECT provinces | Single JOIN query |
| SELECT stats | ↑ |
| SELECT resources | ↑ |
| SELECT proInfra | ↑ |
| SELECT upgrades | ↑ |
| Calculate energy | In-memory from same query |
| Check consumer goods | In-memory from same query |
| **7+ round trips** | **1 round trip** |

### 4.3 Military Page (`/military`)
**Current issue**: Multiple queries for units, limits, upgrades
**Fix**: Batch query

```python
def get_military_page_data(user_id):
    with get_db_cursor(cursor_factory=RealDictCursor) as db:
        db.execute("""
            SELECT
                m.*,
                mp.manpower,
                u.*,
                (SELECT json_agg(json_build_object(
                    'building', building_type,
                    'count', count
                )) FROM proInfra pi
                JOIN provinces p ON pi.id = p.id
                WHERE p.userId = m.id
                GROUP BY p.userId) as building_counts
            FROM military m
            LEFT JOIN upgrades u ON m.id = u.user_id
            WHERE m.id = %s
        """, (user_id,))
        return db.fetchone()
```

### 4.4 Market Page (`/market`)
**Current issue**: N+1 for getting usernames per offer
**Fix**: Already fixed with JOIN — verify it's working

```python
# Verify this JOIN is active
query = """
    SELECT o.*, u.username
    FROM offers o
    INNER JOIN users u ON o.user_id = u.id
    ORDER BY o.price ASC
    LIMIT 100
"""
```

---

## Phase 5: Caching Strategy (Week 4)

### 5.1 Cache Hierarchy

```
Level 1: Request Cache (g._request_cache)
├── Lives for one HTTP request
├── Prevents duplicate queries within same request
└── Zero TTL (cleared automatically)

Level 2: Query Cache (query_cache)
├── Lives for 5 minutes (configurable)
├── User data, influence scores, province summaries
└── Invalidated on writes

Level 3: Response Cache (@cache_response)
├── Lives for 15-60 seconds
├── Full rendered pages
└── User-specific cache keys
```

### 5.2 Cache Invalidation Rules

```python
# After ANY write operation:
def invalidate_user_caches(user_id):
    patterns = [
        f"user_full_{user_id}",
        f"provinces_summary_{user_id}",
        f"influence_{user_id}",
        f"econ_stats_{user_id}",
        f"revenue_{user_id}",
        f"military_{user_id}",
    ]
    for pattern in patterns:
        query_cache.invalidate(pattern)

# Call after:
# - Buy/sell military units
# - Build/demolish infrastructure
# - Buy/sell resources
# - Province creation
# - Any gold/resource change
```

### 5.3 Aggressive Caching for Read-Heavy Pages

```python
# Countries list - cache for 60 seconds (doesn't change often)
@cache_response(ttl_seconds=60)
def countries():
    ...

# Province view - cache for 15 seconds (updates from tasks)
@cache_response(ttl_seconds=15)
def province(pId):
    ...

# Market - cache for 30 seconds (moderate activity)
@cache_response(ttl_seconds=30)
def market():
    ...
```

---

## Phase 6: Frontend Optimizations (Week 4)

### 6.1 Lazy Loading for Heavy Sections

```javascript
// Load influence scores asynchronously
document.addEventListener('DOMContentLoaded', function() {
    const influenceElements = document.querySelectorAll('[data-user-id]');
    const userIds = Array.from(influenceElements).map(el => el.dataset.userId);

    fetch('/api/batch_influence', {
        method: 'POST',
        body: JSON.stringify({user_ids: userIds})
    })
    .then(response => response.json())
    .then(data => {
        influenceElements.forEach(el => {
            el.textContent = data[el.dataset.userId] || 0;
        });
    });
});
```

### 6.2 Add Loading States

```html
<!-- Show skeleton while data loads -->
<div class="province-stats" data-loading="true">
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
</div>
```

### 6.3 Prefetch Common Routes

```html
<link rel="prefetch" href="/military">
<link rel="prefetch" href="/provinces">
```

---

## Phase 7: Monitoring & Profiling (Ongoing)

### 7.1 Add Query Timing Logs

```python
import time
from functools import wraps

def log_slow_queries(threshold_ms=100):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms > threshold_ms:
                logger.warning(f"Slow query in {func.__name__}: {elapsed_ms:.0f}ms")
            return result
        return wrapper
    return decorator
```

### 7.2 Add Route Timing

```python
@app.before_request
def start_timer():
    g.start_time = time.time()

@app.after_request
def log_request(response):
    if hasattr(g, 'start_time'):
        elapsed = (time.time() - g.start_time) * 1000
        if elapsed > 500:
            logger.warning(f"Slow route {request.path}: {elapsed:.0f}ms")
    return response
```

### 7.3 PostgreSQL Slow Query Log

```sql
-- Enable in PostgreSQL config
ALTER SYSTEM SET log_min_duration_statement = 100;  -- Log queries > 100ms
SELECT pg_reload_conf();
```

---

## Implementation Checklist

### Week 1: Database & Foundation
- [ ] Run `scripts/add_database_indexes.py`
- [ ] Add composite indexes for common joins
- [ ] Verify indexes with `EXPLAIN ANALYZE`
- [ ] Create `repositories/` directory structure
- [ ] Implement `UserRepository` with batch queries
- [ ] Add request-level caching to `database.py`

### Week 2: Core Routes
- [ ] Refactor `/province/<id>` to use single query
- [ ] Refactor `/military` to use batch queries
- [ ] Refactor `/provinces` list to use batch queries
- [ ] Add `@cache_response` decorators where missing
- [ ] Verify `/countries` pagination is working

### Week 3: Secondary Routes
- [ ] Refactor `/market` queries
- [ ] Refactor `/coalitions` queries
- [ ] Refactor `/wars` queries
- [ ] Create service layer for complex logic
- [ ] Add cache invalidation on all write operations

### Week 4: Polish & Monitoring
- [ ] Add slow query logging
- [ ] Add route timing logging
- [ ] Implement frontend lazy loading
- [ ] Add loading states to templates
- [ ] Performance test all routes
- [ ] Document final architecture

---

## Expected Results

| Page | Before | After | Improvement |
|------|--------|-------|-------------|
| /countries | 5-15s | <500ms | 10-30× |
| /province/<id> | 2-5s | <300ms | 7-17× |
| /military | 1-3s | <200ms | 5-15× |
| /market | 2-4s | <400ms | 5-10× |
| /provinces | 1-2s | <200ms | 5-10× |

---

## Quick Wins (Do Today)

1. **Run database indexes script**
   ```bash
   python scripts/add_database_indexes.py
   ```

2. **Add `@cache_response` to slow routes**
   ```python
   @cache_response(ttl_seconds=30)
   def expensive_route():
       ...
   ```

3. **Verify batch influence loading is active**
   Check `countries.py` uses `batch_get_influences()`

4. **Check for N+1 patterns**
   ```bash
   grep -rn "for.*in.*:" --include="*.py" | grep -A2 "execute"
   ```

---

## Summary

The restructure focuses on three core principles:

1. **Fewer queries**: Batch operations, JOINs, single-query patterns
2. **More caching**: Request-level, query-level, response-level
3. **Cleaner architecture**: Repository pattern, service layer, thin routes

Estimated total effort: **4 weeks** for full implementation
Quick wins achievable: **Today** (indexes + caching decorators)
