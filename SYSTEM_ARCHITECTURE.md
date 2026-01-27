# Affairs and Order - System Architecture Documentation

## Overview

Affairs and Order (AnO) is a complex Flask-based multiplayer strategy game with real-time resource management, military mechanics, coalition systems, and economic simulation. This document explains the core architecture and how all components work together.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Database Architecture](#database-architecture)
3. [Application Structure](#application-structure)
4. [Core Systems](#core-systems)
5. [Database Connection Management](#database-connection-management)
6. [Deployment on Railway](#deployment-on-railway)
7. [Game Mechanics](#game-mechanics)
8. [Important Patterns & Best Practices](#important-patterns--best-practices)

---

## Technology Stack

### Backend
- **Framework**: Flask 1.1.2 (lightweight Python web framework)
- **Web Server**: Gunicorn 20.1.0 (WSGI server for production)
- **Database**: PostgreSQL (relational database via Railway)
- **Job Queue**: Celery 5.2.2 with Redis backend
- **Scheduler**: Celery Beat (for recurring tasks)

### Frontend
- **HTML/CSS/JavaScript**: Jinja2 templating with vanilla JS
- **Styling**: Custom CSS with responsive design

### Infrastructure
- **Deployment**: Railway.app (Git-connected deployment)
- **Build System**: Nixpacks (deterministic build system)
- **Environment**: Python 3.8, Linux container

### Key Dependencies
```
Flask==1.1.2
psycopg2-binary==2.9.9  # PostgreSQL adapter
celery==5.2.2           # Task queue
python-dotenv           # Environment configuration
Jinja2==2.11.3          # Template engine (strict pinning for Flask 1.1.2)
```

---

## Database Architecture

### Core Tables

#### Users & Authentication
- **users**: Player accounts with usernames, passwords, descriptions, flags
- **stats**: Player statistics (gold, location, date created, etc.)
- **reset_codes**: Password reset functionality
- **registration_keys**: Registration access control (e.g., 'a', 'b', 'c' keys)

#### Territory & Infrastructure
- **provinces**: Player-owned provinces (name, population, land, city slots, coordinates)
- **proInfra**: Province infrastructure (buildings, military units, factories, farms, etc.)
- **stats**: Location/continent assignment for each player

#### Resources & Economy
- **resources**: Player inventory (gold, rations, oil, coal, uranium, lumber, etc.)
- **offers**: Trade offers between players
- **trades**: Completed trades with history
- **revenue**: Economic ledger (income/expense tracking)
- **upgrades**: Technology/policy purchases per player

#### Military & Combat
- **military**: Unit counts (soldiers, artillery, tanks, fighters, bombers, submarines, nukes, spies, etc.)
- **wars**: Active/completed wars with attacker, defender, amount, and outcome
- **peace**: Peace treaties between nations
- **reparation_tax**: War reparations payments

#### Coalition System
- **coalitions**: Members of coalitions with roles (leader, officer, member)
- **colNames**: Coalition metadata (name, flag, bank balance)
- **colBanks**: Coalition treasury accounts
- **colBanksRequests**: Money transfer requests between players/coalition
- **requests**: Pending coalition invitations/join requests

#### Intelligence & News
- **spyinfo**: Spy missions with spyer/spyee and outcome
- **news**: Messages sent to players about game events
- **treaties**: Trade agreements and alliances

#### Policies & Upgrades
- **policies**: Player policy choices affecting production/costs

---

## Application Structure

```
AnO/
├── app.py                      # Flask app initialization, route registration
├── wsgi.py                     # Entry point for Gunicorn
├── database.py                 # Centralized database connection management
├── helpers.py                  # Utility functions (login_required, error handling, etc.)
├── variables.py                # Game balance constants (unit prices, building costs, etc.)
├── tasks.py                    # Celery tasks (async jobs, recurring updates)
│
├── Route Modules (by game feature):
├── countries.py                # Country viewing, user account management
├── province.py                 # Province management and building
├── coalition.py                # Coalition system and management
├── wars.py                     # Warfare mechanics and combat resolution
├── military.py                 # Military unit training and movement
├── market.py                   # Trading system
├── upgrades.py                 # Technology/policy purchases
├── units.py                    # Unit-specific operations
├── intelligence.py             # Spy mechanics
├── policies.py                 # Policy system
├── business.py                 # Commerce and buildings
│
├── User Management:
├── login.py                    # Authentication routes
├── signup.py                   # Registration and account creation
│
├── Static Files:
├── static/
│   ├── style.css              # Main stylesheet
│   ├── script.js              # Main JavaScript
│   ├── images/                # Game assets
│   └── flags/                 # Player flag uploads
│
├── Templates:
├── templates/
│   ├── layout.html            # Base template
│   ├── index.html             # Home page
│   ├── country.html           # Country/player profile
│   ├── province.html          # Province detail view
│   ├── military.html          # Military management
│   ├── market.html            # Trading interface
│   └── [others for each feature]
│
├── Configuration:
├── .env                        # Environment variables (DATABASE_URL, SECRET_KEY, etc.)
├── nixpacks.toml              # Build configuration for Railway
├── Procfile                   # Process definitions (web, worker, beat scheduler)
├── requirements.txt           # Python dependencies
├── runtime.txt                # Python version specification
│
├── Database Initialization:
├── init_db_railway.py         # Database schema initialization
├── affo/postgres/             # SQL initialization files
│
├── Background Jobs:
├── celerybeat-schedule        # Celery Beat scheduler state file
│
└── Testing & Scripts:
    ├── test.py                # Manual testing
    ├── tests/                 # Test suite
    └── scripts/               # Utility scripts for database operations
```

---

## Core Systems

### 1. Authentication System

**Location**: `login.py`, `signup.py`, `helpers.py`

- Users register with username, password, and registration key
- Session-based authentication using Flask sessions
- `@login_required` decorator protects routes
- Password reset via email codes (reset_codes table)

```python
@app.route("/login", methods=["GET", "POST"])
def login():
    # Validates credentials against users table
    # Creates session on successful login
```

### 2. Database Connection Management

**Location**: `database.py`

This is the **most critical component** for stability:

```python
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool

# Lazy-initialized connection pool
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,  # min/max connections
            os.getenv("DATABASE_URL")
        )
    return _pool

@contextmanager
def get_db_cursor():
    """
    Context manager for database operations.
    Handles connection pooling, cursor creation, and automatic commit/close.
    """
    conn = get_pool().getconn()
    try:
        db = conn.cursor()
        yield db
        conn.commit()  # Auto-commit on success
    except Exception as e:
        conn.rollback()  # Rollback on error
        raise
    finally:
        db.close()
        get_pool().putconn(conn)
```

**Why this pattern matters**:
- **Connection pooling**: Reuses database connections instead of creating new ones
- **Automatic cleanup**: `finally` block ensures connections are returned to pool
- **Transaction safety**: Auto-commits on success, auto-rollbacks on error
- **Context manager**: Guarantees proper cleanup even if exceptions occur

**All database access must use**:
```python
with get_db_cursor() as db:
    db.execute("SELECT ...", params)
    result = db.fetchall()
    # No need to commit or close - context manager handles it
```

### 3. Route Structure

Each feature module exports route handlers registered with the Flask app:

```python
from src.app import app


@app.route("/country/id=<int:cId>", methods=["GET"])
@login_required
def country(cId):
    with get_db_cursor() as db:
        # Fetch data
        # Render template
        return render_template(...)
```

### 4. Game Loop & Scheduled Tasks

**Location**: `tasks.py`, `celerybeat-schedule`

Celery Beat scheduler runs recurring tasks:

- **Every turn cycle**: Update province production, consume resources, apply happiness modifiers
- **Military operations**: Process ongoing wars, apply casualties
- **Economic updates**: Calculate tax revenue, update market prices
- **News generation**: Create events for player newsfeeds

```python
from celery import shared_task

@shared_task
def update_all_provinces():
    # Run for every province in the game
    # Update resources based on infrastructure
    # Apply consumption (rations, consumer goods)
    # Update happiness
```

### 5. Province System

**Location**: `province.py`

Provinces are the core gameplay unit:

- Each player can own multiple provinces
- Each province has:
  - **Population**: Consumes rations, produces resources
  - **Infrastructure**: Buildings generate resources/effects
  - **Land**: Limited slots for military/industrial buildings
  - **City slots**: Limited urban infrastructure capacity

**Infrastructure Types**:
- **Energy**: Coal burners, oil burners, hydro dams, nuclear reactors, solar fields
- **Production**: Farms, pumpjacks, mines (coal, bauxite, copper, uranium, lead, iron, lumber)
- **Manufacturing**: Component factories, steel mills, ammunition factories, oil refineries, aluminium refineries
- **Commerce**: General stores, farmers markets, malls, banks
- **Urban**: City parks, hospitals, libraries, universities, monorails
- **Military**: Army bases, harbours, aerodomes
- **Administrative**: Admin buildings, silos

Each building has:
- `plus`: Resources it generates per turn
- `minus`: Resources it consumes per turn
- `money`: Gold operating cost per turn

### 6. Military System

**Location**: `military.py`, `wars.py`, `attack_scripts/`

Units available:
- Ground: Soldiers, Artillery, Tanks
- Air: Fighters, Bombers, Apaches
- Naval: Submarines, Destroyers, Cruisers
- Strategic: ICBMs, Nuclear Weapons
- Special: Spies

Wars involve:
- Declaration between two nations
- Automatic casualty calculation based on unit composition
- Winner/loser determination
- Reparations and peace treaties

### 7. Economic System

**Location**: `market.py`, `upgrades.py`

- **Trading**: Players can offer resources to each other
- **Market**: Global trading interface
- **Upgrades**: Technology purchases that improve efficiency
- **Policies**: Government policies affecting production/costs/military

### 8. Coalition System

**Location**: `coalitions.py`

Players can form coalitions (guilds/alliances):
- Leaders create coalitions
- Members join and contribute
- Coalition bank for shared resources
- Collective military operations
- Alliance bonuses

---

## Database Connection Management

### The Problem We Solved

Original code had **hardcoded connections** scattered throughout:

```python
# BAD - Don't do this!
connection = psycopg2.connect(
    database=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT")
)
db = connection.cursor()
db.execute("SELECT ...")
connection.commit()
connection.close()
```

**Issues**:
1. Creates new connection for every operation (slow, resource-intensive)
2. Manual connection management error-prone
3. Connection not returned to pool on exceptions
4. Difficult to scale, causes "too many connections" errors

### The Solution

Centralized in `database.py` with connection pooling and context manager pattern:

```python
# GOOD - Use this everywhere!
from src.database import get_db_cursor

with get_db_cursor() as db:
    db.execute("SELECT ...", params)
    result = db.fetchall()
    # Automatic commit and cleanup
```

### Migration Status

**Fixed** (✅):
- countries.py (complete)
- province.py (complete)
- intelligence.py (complete)
- upgrades.py (complete)
- helpers.py (complete)
- tasks.py (complete)

**Remaining** (~60+ instances in):
- coalitions.py (11 instances)
- wars.py (13 instances)
- military.py (1 instance)
- market.py (10 instances)
- units.py (5 instances)
- signup.py (2 instances)
- tasks.py (2 instances in other functions)
- attack_scripts/Nations.py (15 instances)
- scripts/ and tests/ (not critical for production)

---

## Deployment on Railway

### Current Setup

**Project**: natural-gratitude (on Railway.app)

**Services**:
1. **web**: Flask/Gunicorn server (handles HTTP requests)
2. **celery-worker**: Processes async tasks from queue
3. **celery-beat**: Scheduler for recurring tasks
4. **postgres**: PostgreSQL database
5. **redis**: Cache and message broker for Celery

### Build & Deployment Process

1. Push code to GitHub (Manbo04/AnO-Reborn)
2. Railway detects push and starts build
3. **Nixpacks** reads `nixpacks.toml` and builds container
4. Dependencies installed from `requirements.txt`
5. Database migrations applied (if any)
6. Services start:
   - Web service on port 8080
   - Celery worker connects to Redis
   - Celery beat starts scheduler

### Environment Configuration

Set in Railway Variables (not in `.env` file which is local-only):

```
DATABASE_URL=postgresql://user:pass@host:port/db
ENVIRONMENT=PROD
SECRET_KEY=<flask-session-key>
DISCORD_WEBHOOK_URL=<optional-webhook>
```

### Troubleshooting Deployments

**Issue**: App won't start
- Check: Syntax errors in Python code
- Solution: Run `python -m py_compile filename.py` locally

**Issue**: 500 errors on routes
- Cause: Hardcoded psycopg2.connect() calls
- Solution: Replace with `from database import get_db_cursor` pattern

**Issue**: Database shows as inaccessible
- Cause: DATABASE_URL not set in Railway Variables
- Solution: Add DATABASE_URL reference in Railway web service config

**Issue**: Multiple connections not closing
- Cause: Forgotten `connection.close()` or exception in try block
- Solution: Use context manager pattern in database.py

---

## Game Mechanics

### Resource System

**Primary Resources**:
- **Gold**: Currency for unit/building purchases
- **Rations**: Food for population (population / RATIONS_PER = rations consumed)
- **Consumer Goods**: Happiness modifier (population / CONSUMER_GOODS_PER = CG needed)
- **Energy**: Power production vs consumption (critical for infrastructure)

**Raw Materials**:
- Oil, Coal, Uranium, Bauxite, Iron, Lead, Copper, Lumber
- Used to craft components and ammunition

**Manufactured Goods**:
- Components, Steel, Ammunition, Gasoline, Aluminium

### Production Chain

Example - Producing Steel:
1. Iron mines extract iron from province land
2. Iron consumed by steel mills
3. Steel produced and stored in resources
4. Steel can be used for unit production

### Happiness & Productivity

Happiness affected by:
- Consumer goods availability
- Government policies (can improve/hurt happiness)
- War status
- Infrastructure (hospitals, parks, universities improve happiness)

Productivity:
- Base rate varies by location/terrain
- Affected by policies and infrastructure

### Cost Scaling

Building/unit costs increase with purchase count (exponential pricing):

```python
def sum_cost_exp(starting_value, rate_of_growth, current_owned, num_purchased):
    M = (starting_value * (1 - pow(rate_of_growth, (current_owned + num_purchased)))) / (1 - rate_of_growth)
    N = (starting_value * (1 - pow(rate_of_growth, (current_owned)))) / (1 - rate_of_growth)
    total_cost = M - N
    return round(total_cost)
```

First city costs 750,000 gold. By 10th city, costs millions.

---

## Important Patterns & Best Practices

### 1. Always Use Context Manager for DB

```python
# ✅ CORRECT
with get_db_cursor() as db:
    db.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = db.fetchone()

# ❌ WRONG
conn = psycopg2.connect(...)
```

### 2. Parameterized Queries (SQL Injection Prevention)

```python
# ✅ CORRECT - Uses parameters
db.execute("SELECT * FROM users WHERE id=%s", (user_id,))

# ❌ WRONG - String concatenation vulnerability
db.execute(f"SELECT * FROM users WHERE id={user_id}")
```

### 3. Error Handling in Routes

```python
@app.route("/user/<user_id>")
@login_required
def get_user(user_id):
    try:
        with get_db_cursor() as db:
            db.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            user = db.fetchone()
            if not user:
                return error(404, "User not found")
    except Exception as e:
        return error(500, "Database error")

    return render_template("user.html", user=user)
```

### 4. Session Security

```python
from src.helpers import login_required

# Access logged-in user ID
user_id = session["user_id"]  # Set during login


# Protected routes
@app.route("/my-profile")
@login_required
def my_profile():
# Automatically redirects to login if not authenticated
```

### 5. Configuration Management

All configuration via environment variables:
```python
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "DEV")
```

Local development: Create `.env` file
Production: Set in Railway Variables

### 6. Celery Task Pattern

```python
from celery_app import app as celery_app

@celery_app.task
def slow_operation(user_id):
    # Runs in background worker
    # Can take minutes without blocking web request
    pass

# In a route:
slow_operation.delay(user_id)  # Queue the task, return immediately
```

### 7. Template Rendering

```python
return render_template("page.html",
                      username=username,
                      user_level=user_level,
                      provinces=provinces)
```

In Jinja2 template:
```html
<h1>{{ username }}'s Profile</h1>
{% for province in provinces %}
    <p>{{ province.name }}: {{ province.population }} population</p>
{% endfor %}
```

---

## Summary

Affairs and Order is a complex strategy game built on:

- **Flask** for web routing and templating
- **PostgreSQL** for persistent data storage
- **Celery + Redis** for background jobs and caching
- **Connection pooling** via database.py for efficient DB access
- **Railway.app** for cloud hosting with automatic deployments

The key to stability and performance is the **centralized database connection management** in `database.py`. All database operations should go through `get_db_cursor()` context manager to ensure proper resource cleanup and connection pooling.

The game mechanics revolve around **province management**, **resource production/consumption**, **military warfare**, and **economic trading**. Everything is driven by a turn-based system with scheduled Celery tasks updating game state.

---

## Quick Reference

### Starting the App Locally
```bash
# Set up environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure local DB
export DATABASE_URL="postgresql://user:pass@localhost/anodb"
export SECRET_KEY="dev-key"

# Run Flask dev server
python app.py

# In separate terminal, run Celery worker:
celery -A tasks worker --loglevel=info

# In another terminal, run Celery beat:
celery -A tasks beat --loglevel=info
```

### Deploying to Railway
1. Push to master branch on GitHub
2. Railway auto-deploys via webhook
3. Monitor deployment at railway.app dashboard

### Common Tasks

**Add a new route**:
- Create function in appropriate module
- Add `@app.route()` decorator
- Register in app initialization if needed
- Use `get_db_cursor()` for database access

**Add a scheduled task**:
- Define in `tasks.py` with `@app.task`
- Add schedule to Celery Beat config
- Test locally before deployment

**Debug a 500 error**:
- Check logs in Railway or Flask dev server
- Ensure all `psycopg2.connect()` replaced with `get_db_cursor()`
- Verify DATABASE_URL is set
- Check for unhandled exceptions in route handlers
