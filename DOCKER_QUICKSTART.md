# Docker Quick Start Guide for AnO-Reborn

This guide will help you get AnO-Reborn running with Docker in minutes.

## Prerequisites

- **Docker Desktop** installed ([Download here](https://docs.docker.com/get-docker/))
- **Docker Compose** (included with Docker Desktop)
- **Git** (to clone the repository)

## Setup Steps

### 1. Clone the Repository

```bash
git clone https://github.com/Manbo04/AnO-Reborn.git
cd AnO-Reborn
```

### 2. Create Environment File

Copy the Docker environment example file:

```bash
cp .env.docker.example .env
```

Or, if you prefer to use the Railway example:

```bash
cp .env.example .env
```

Edit `.env` and customize your values (at minimum, change the passwords and secret key):

```bash
# Database Configuration
PG_DATABASE=ano
PG_USER=ano
PG_PASSWORD=your_secure_password_here
PG_HOST=db
PG_PORT=5432

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Application Configuration
ENVIRONMENT=DEV
SECRET_KEY=your_secret_key_here
FLASK_ENV=development

# Optional: Discord Webhook for notifications
DISCORD_WEBHOOK_URL=
```

**Important**: Generate a secure SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start All Services

```bash
docker-compose up --build
```

This command will:
- Build the Flask application image
- Pull PostgreSQL and Redis images
- Start all services (web, database, redis, celery worker, celery beat)
- Show logs from all containers

### 4. Initialize the Database (First Time Only)

In a new terminal window:

```bash
# Access the web container
docker-compose exec web bash

# Run database initialization script
python init_db_railway.py

# Or, if you have a different init script:
python affo/create_db.py

# Exit the container
exit
```

### 5. Access the Application

Open your browser and navigate to:

```
http://localhost:5000
```

You should see the AnO-Reborn login/signup page!

## Common Commands

### Start Services (Detached Mode)

Run in background without showing logs:

```bash
docker-compose up -d
```

### Stop Services

```bash
docker-compose down
```

### View Logs

All services:
```bash
docker-compose logs -f
```

Specific service:
```bash
docker-compose logs -f web      # Flask app
docker-compose logs -f worker   # Celery worker
docker-compose logs -f beat     # Celery beat
docker-compose logs -f db       # PostgreSQL
docker-compose logs -f redis    # Redis
```

### Restart a Service

```bash
docker-compose restart web
docker-compose restart worker
```

### Rebuild After Code Changes

```bash
docker-compose up --build
```

### Execute Commands in Containers

Access Flask shell:
```bash
docker-compose exec web flask shell
```

Access PostgreSQL:
```bash
docker-compose exec db psql -U ano -d ano
```

Access Python in web container:
```bash
docker-compose exec web python
```

Run bash in web container:
```bash
docker-compose exec web bash
```

### Check Running Containers

```bash
docker-compose ps
```

### Remove Everything (Including Volumes)

**Warning**: This deletes all data!

```bash
docker-compose down -v
```

## Troubleshooting

### Port Already in Use

If port 5000 is already in use, change it in `.env`:

```bash
PORT=8080
```

Then restart:
```bash
docker-compose down
docker-compose up
```

### Database Connection Error

1. Check if database is running:
   ```bash
   docker-compose ps
   ```

2. Check database logs:
   ```bash
   docker-compose logs db
   ```

3. Verify `.env` has correct database settings

### Code Changes Not Reflected

The docker-compose.yml mounts your local code directory, so changes should be automatic. If not:

```bash
docker-compose restart web
```

Or rebuild:
```bash
docker-compose up --build
```

### Container Fails to Start

Check logs:
```bash
docker-compose logs
```

Common issues:
- Missing `.env` file → Create from `.env.example`
- Wrong database credentials → Check `.env`
- Port conflicts → Change ports in `.env`

### Clear Docker Cache

If you're having persistent issues:

```bash
# Stop containers
docker-compose down -v

# Remove all unused Docker resources
docker system prune -a

# Rebuild from scratch
docker-compose up --build
```

## Development Workflow

1. **Make code changes** in your editor
2. Changes are automatically available (code is mounted as volume)
3. **Restart service** if needed:
   ```bash
   docker-compose restart web
   ```
4. **View logs** to debug:
   ```bash
   docker-compose logs -f web
   ```

## Production Deployment

For production, remove the volume mounts in `docker-compose.yml`:

```yaml
# Comment out these lines in web, worker, and beat services:
# volumes:
#   - .:/app
#   - /app/venv310
```

And set production environment variables:

```bash
ENVIRONMENT=PROD
FLASK_ENV=production
SECRET_KEY=<strong-secret-key>
```

## Architecture

When you run `docker-compose up`, you start 5 containers:

```
┌─────────────────────────────────────────┐
│              Docker Network              │
│                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │   Web    │  │  Worker  │  │  Beat  ││
│  │  (Flask) │  │ (Celery) │  │(Celery)││
│  │ Port:5000│  └────┬─────┘  └───┬────┘│
│  └────┬─────┘       │            │     │
│       │             │            │     │
│  ┌────┴─────────────┴────────────┴───┐ │
│  │            Redis                   │ │
│  │       (Message Broker)             │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │         PostgreSQL                 │ │
│  │         (Database)                 │ │
│  │      Persistent Volume             │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

All containers can communicate with each other by service name (e.g., `db`, `redis`).

## Next Steps

- Read [CONTAINERS.md](./CONTAINERS.md) for comprehensive container documentation
- Customize `docker-compose.yml` for your needs
- Set up CI/CD with Docker
- Deploy to cloud platforms that support Docker

## Getting Help

- **Docker Documentation**: https://docs.docker.com/
- **Docker Compose Documentation**: https://docs.docker.com/compose/
- **Project Issues**: https://github.com/Manbo04/AnO-Reborn/issues

Happy coding with Docker! 🐳
