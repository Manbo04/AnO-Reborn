# Docker & Railway Deployment Guide for AnO

## Quick Start - Local Development with Docker

### Prerequisites
- Docker and Docker Compose installed
- `.env` file with your configuration

### Setup

1. **Copy environment template**:
```bash
cp .env.example .env
# Edit .env with your actual values
```

2. **Build and run containers**:
```bash
docker-compose up -d
```

3. **Initialize database** (first time only):
```bash
docker-compose exec web python3 init_db_railway.py
```

4. **Access the application**:
- Web: http://localhost:5000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

5. **View logs**:
```bash
# Web server
docker-compose logs -f web

# Celery worker
docker-compose logs -f celery-worker

# Beat scheduler
docker-compose logs -f beat

# All services
docker-compose logs -f
```

## Production Deployment on Railway with Docker

### Using Railway CLI

1. **Ensure you're logged in to Railway**:
```bash
railway login
```

2. **Link your project**:
```bash
railway link
```

3. **Deploy with Docker**:
```bash
railway up
```

4. **Set environment variables**:
```bash
railway variable add ENVIRONMENT=PROD
railway variable add DISCORD_CLIENT_ID=your_id
railway variable add DISCORD_CLIENT_SECRET=your_secret
railway variable add SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
railway variable add RECAPTCHA_SECRET_KEY=your_recaptcha_key
railway variable add DISCORD_REDIRECT_URI=https://your-domain.com/callback
```

### Post-Deployment

1. **Initialize database**:
```bash
railway run python3 init_db_railway.py
```

2. **Check service status**:
```bash
railway status
```

## Docker Commands Reference

### Build
```bash
docker build -t ano-app:latest .
```

### Development
```bash
docker-compose up -d              # Start all services
docker-compose down               # Stop all services
docker-compose exec web bash      # Shell into web container
docker-compose logs -f web        # Follow web logs
docker-compose ps                 # Show running containers
```

### Database Management
```bash
docker-compose exec postgres psql -U ano_user -d ano_game
docker-compose exec web python3 init_db_railway.py
```

### Celery Management
```bash
docker-compose exec celery-worker celery -A tasks inspect active
docker-compose exec celery-worker celery -A tasks inspect stats
```

## Security Notes

1. **Change default passwords** in `.env`:
   - `PG_PASSWORD`
   - `REDIS_PASSWORD`
   - `SECRET_KEY`

2. **Use strong secrets**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. **Store secrets securely**:
   - Never commit `.env` to git
   - Use Railway's secret management for production
