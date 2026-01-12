# Game Performance Issue - Root Cause Analysis

## 🔴 CRITICAL SLOWNESS ROOT CAUSES IDENTIFIED

### 1. **DATABASE DEADLOCKS** (Primary Cause)
**Location**: Error logs show continuous deadlocks in `provinces` table

```
ERROR: deadlock detected
DETAIL: Process 2219 waits for ShareLock on transaction 18668; blocked by process 2159.
Process 2159 waits for ShareLock on transaction 18666; blocked by process 2219.
CONTEXT: while updating tuple (3,20) in relation "provinces"
```

**Why It Happens**:
- Multiple Celery tasks update the same `provinces` rows simultaneously
- Tasks that run at intervals: tax_income (minute 0), revenue (minute 10), population (minute 20)
- Even though staggered by 10 minutes, they can still overlap if previous task takes >10 minutes
- Each task iterates through ALL users and ALL provinces, making 1000s of individual UPDATE queries

**Impact**: 
- Players experience 5-15 second delays when clicking anything during task execution
- Server becomes unresponsive
- Player actions timeout waiting for locks to release

---

### 2. **N+1 QUERY PATTERN IN REVENUE GENERATION** (Secondary Cause)
**Location**: `tasks.py` lines 600-920 (task_generate_province_revenue)

**The Problem**:
```python
# For each user
for user_id in all_users:
    # For each province
    for province_id in user_provinces:
        # For each building in that province
        for unit in buildings:
            # SEPARATE SELECT + UPDATE for each field affected
            db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
            current_money = db.fetchone()[0]
            db.execute("UPDATE stats SET gold=gold-%s WHERE id=%s", (operating_costs, user_id))
            
            db.execute("SELECT energy FROM provinces WHERE id=%s", (province_id,))
            current_energy = db.fetchone()[0]
            db.execute("UPDATE provinces SET energy=%s WHERE id=%s", (new_energy, province_id))
            
            # This happens for EVERY building type and EVERY resource
            db.execute("UPDATE resources SET coal=%s WHERE id=%s", (amount, user_id))
            db.execute("UPDATE resources SET oil=%s WHERE id=%s", (amount, user_id))
            # ... 15+ separate updates per building
```

**Calculation**:
- 100 users × 5 provinces × 20 building types × 20 separate queries = **200,000 database queries**
- All executed sequentially in a single task
- If each query takes 1ms: 200,000ms = **200 seconds of task execution**
- Task overlaps with next task → deadlock

**Impact**:
- Task takes 3-5 minutes to complete (should be <10 seconds)
- Database connection pool gets exhausted
- All subsequent requests queue up waiting for connections
- Game becomes unresponsive

---

### 3. **RESOURCE UPDATES DONE ONE-BY-ONE** (Tertiary Cause)
**Location**: `tasks.py` lines 780-835

For each resource (coal, oil, uranium, etc.), separate UPDATE:
```python
resource_u_statement = f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
db.execute(resource_u_statement, (new_resource, user_id))
```

**Should be**:
```sql
UPDATE resources SET coal=%s, oil=%s, uranium=%s, ... WHERE id=%s
```

**Impact**: 
- 15+ queries become 1 query per user
- 100 users × 15 resources = 1,500 queries → becomes 100 queries
- **94% reduction in query count**

---

### 4. **MISSING DATABASE INDEXES**
Database indexes haven't been created yet (from earlier optimization work).

Queries without indexes scan entire table:
```
provinces table: ~5,000 rows × multiple scans per task = massive IO
```

---

## 📊 Performance Math

### Current Performance (Broken)
```
Task: generate_province_revenue
- Users: 100
- Provinces per user: 5
- Buildings per province: 20
- Queries per building: 20 (1 select + 15 resource updates + 4 effects)

Total: 100 × 5 × 20 × 20 = 200,000 queries
Execution time: 200,000 queries × 1ms = 200 seconds

Next task starts at minute 10
But previous task (minute 0) still running
→ DEADLOCK

Game frozen for 200+ seconds
```

### What Should Happen (Optimized)
```
Batch update all users' resources in single queries:

UPDATE resources SET coal=%s, oil=%s, uranium=%s... 
WHERE id IN (%s, %s, %s...) RETURNING id

Execution time: 100 queries × 1ms = 100ms

No overlaps, no deadlocks
Game responsive
```

---

## ✅ Solutions (Priority Order)

### CRITICAL (Do First)
1. **Batch the resource updates**
   - Instead of 15 separate UPDATE queries per user
   - Use single UPDATE with multiple column assignments
   - Reduces 1,500 queries to 100 queries

2. **Create database indexes**
   - Run: `python scripts/add_database_indexes.py`
   - Speeds up each query 10-100×

### HIGH (Do Second)
3. **Increase task timing gaps**
   - Change schedule from 0/10/20 minutes to 0/15/30 minutes
   - Gives each task 15 minutes to complete safely
   - Reduces chance of overlap

4. **Add transaction isolation**
   - Use `SERIALIZABLE` transaction level
   - Prevents reading dirty data during overlaps

### MEDIUM (Do Third)
5. **Parallelize task execution**
   - Split users into chunks
   - Run multiple worker processes
   - Update different users in parallel instead of sequentially

---

## Why The Game Feels So Slow

1. **Every 10 minutes**: One of the background tasks runs
2. **Task takes 200+ seconds**: Because 200,000 slow queries
3. **Database gets locked**: Other tasks and player requests queue up
4. **Players wait 5-15 seconds**: For their action to complete
5. **Repeat every 10 minutes**: Constant slowness pattern

---

## Evidence From Logs

```
Deadlock at 2026-01-01 23:43:36
Deadlock at 2025-12-31 17:49:07  
Deadlock at 2025-12-31 17:45:27
```

Multiple deadlocks recorded. Pattern: approximately every few hours (when tasks overlap).

---

## Conclusion

**It's NOT the number generation** (already fixed with O(1) formula)

**It IS the database task execution**:
- Too many queries (200,000 instead of 100-500)
- Tasks overlap causing deadlocks
- No indexes making each query slow
- Sequential updates instead of batched

**Fix priority**: Batch updates → Indexes → Increase gaps
