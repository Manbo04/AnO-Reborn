# Railway Deployment Guide for Affairs & Order

This guide will help you deploy the Affairs & Order game to Railway.app.

## Prerequisites

- GitHub account with AnO repository
- Railway account (sign up at https://railway.app)
- All changes committed and pushed to your repository

## Architecture Overview

Your Railway deployment will consist of:
1. **PostgreSQL Database** - Stores all game data
2. **Redis Instance** - Message broker for Celery tasks
3. **Web Service** - Main Flask application (Gunicorn)
4. **Worker Service** - Celery worker for background tasks
5. **Beat Service** - Celery beat scheduler for periodic tasks

---

## Step 1: Create Railway Project

1. Go to https://railway.app and sign in with GitHub
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `AnO` repository
5. Railway will create a new project

---

## Step 2: Add PostgreSQL Database

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically creates a `DATABASE_URL` environment variable
4. **No additional configuration needed** - the code will parse it automatically

---

## Step 3: Add Redis

1. Click **"+ New"** again
2. Select **"Database"** → **"Add Redis"**
3. Railway automatically creates a `REDIS_URL` environment variable
4. **No additional configuration needed** - the code will parse it automatically

---

## Step 4: Configure Web Service (Main App)

1. Click on your main service (the one connected to GitHub)
2. Go to **"Settings"** tab
3. Set the **Start Command**:
   ```
   gunicorn wsgi:app --workers 4 --timeout 120 --bind 0.0.0.0:$PORT
   ```
4. Add **Environment Variables** (Settings → Variables):
   ```
   ENVIRONMENT=PROD
   SECRET_KEY=<generate-a-long-random-string>
   DISCORD_WEBHOOK_URL=<your-discord-webhook-url>
   SENDGRID_API_KEY=<your-sendgrid-api-key>
   ```

   To generate a secure SECRET_KEY, run in terminal:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

5. Under **"Networking"**, enable **Public Networking** and note your URL

---

## Step 5: Create Celery Worker Service

1. Click **"+ New"** → **"GitHub Repo"**
2. Select the **same AnO repository**
3. Railway will create a new service
4. Go to **"Settings"** tab
5. Set **Service Name**: `celery-worker`
6. Set **Start Command**:
   ```
   celery -A tasks.celery worker --loglevel=INFO
   ```
7. Under **"Variables"**, add the same environment variables:
   ```
   ENVIRONMENT=PROD
   SECRET_KEY=<same-as-web-service>
   DISCORD_WEBHOOK_URL=<your-discord-webhook-url>
   SENDGRID_API_KEY=<your-sendgrid-api-key>
   ```
8. **Important**: Link to the same PostgreSQL and Redis instances:
   - Click **"Variables"** → **"Reference Variables"**
   - Add references from the PostgreSQL and Redis services

---

## Step 6: Create Celery Beat Service

1. Click **"+ New"** → **"GitHub Repo"**
2. Select the **same AnO repository** again
3. Go to **"Settings"** tab
4. Set **Service Name**: `celery-beat`
5. Set **Start Command**:
   ```
   celery -A tasks.celery beat --loglevel=INFO
   ```
6. Add the same environment variables as worker
7. Link to the same PostgreSQL and Redis instances

---

## Step 7: Apply Changes and Deploy

1. In the Railway dashboard, you should see **"Apply 2 changes"** (or similar)
2. Click **"Details"** to review changes
3. Click **"Deploy"** or **"Apply changes"**
4. Wait for all services to build and deploy (this may take 5-10 minutes)

---

## Step 8: Initialize Database (First Deployment Only)

After the first successful deployment:

1. Click on the **Web Service**
2. Go to **"Deployments"** tab
3. Click on the latest deployment
4. You may need to run database initialization scripts

Option A: Use Railway CLI (if you have it installed):
```bash
railway run python affo/create_db.py
```

Option B: Add a one-time initialization task to your code

---

## Monitoring & Logs

### View Logs
- Click on any service (Web, Worker, Beat)
- Go to **"Logs"** tab
- Monitor for errors or issues

### Common Issues & Solutions

**Problem**: "Failed to connect to database"
- **Solution**: Check that PostgreSQL service is running and DATABASE_URL is available

**Problem**: "Failed to connect to Redis"
- **Solution**: Check that Redis service is running and REDIS_URL is available

**Problem**: "Worker not processing tasks"
- **Solution**: Ensure Worker and Beat services are both running and connected to Redis

**Problem**: "Application Error" or 500 errors
- **Solution**: Check web service logs for Python errors, ensure all environment variables are set

---

## Environment Variables Summary

### Required for ALL services:
- `DATABASE_URL` - Automatically provided by Railway PostgreSQL
- `REDIS_URL` - Automatically provided by Railway Redis
- `ENVIRONMENT` - Set to `PROD`
- `SECRET_KEY` - Generate a secure random string

### Optional (but recommended):
- `DISCORD_WEBHOOK_URL` - For error notifications
- `SENDGRID_API_KEY` - For email functionality

### Legacy variables (now auto-parsed from DATABASE_URL):
These are automatically set by the `config.py` module:
- `PG_HOST`
- `PG_PORT`
- `PG_USER`
- `PG_PASSWORD`
- `PG_DATABASE`

---

## Cost Estimates

Railway pricing (as of 2024):
- **Free Trial**: $5 credit (good for testing)
- **Hobby Plan**: $5/month + usage
- **Typical monthly cost**: $10-25/month depending on traffic

Resource usage:
- PostgreSQL: ~$2-5/month
- Redis: ~$2-3/month
- Web Service: ~$3-10/month
- Worker + Beat: ~$3-7/month

---

## Scaling & Performance

### Scale Web Service:
1. Go to Web Service → Settings
2. Adjust **Workers** in start command (currently 4)
3. Monitor RAM usage and adjust as needed

### Scale Worker Service:
1. Create additional worker services if needed
2. All workers will share the same Redis queue

### Database Optimization:
- Monitor query performance in logs
- Consider upgrading PostgreSQL plan if needed
- The new `database.py` module includes connection pooling for better performance

---

## Support & Troubleshooting

### Railway Dashboard
- View all services: https://railway.app/dashboard
- Check service health and resource usage

### Common Commands (if using Railway CLI)
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# View logs
railway logs

# Run commands in production
railway run python manage.py migrate
```

---

## Updating Your Deployment

When you push changes to GitHub:
1. Railway automatically detects the push
2. Services rebuild and redeploy
3. Zero-downtime deployment (if configured)

To deploy manually:
1. Go to service in Railway dashboard
2. Click **"Deploy"** → **"Trigger Deploy"**

---

## Next Steps After Deployment

1. ✅ Test the game at your Railway URL
2. ✅ Configure custom domain (optional)
3. ✅ Set up monitoring/alerts
4. ✅ Test Celery tasks are running (check logs)
5. ✅ Verify database is accessible
6. ✅ Test user registration and login

---

## Notes

- The `config.py` module automatically parses Railway's `DATABASE_URL` and `REDIS_URL` into the format your application expects
- Connection pooling is enabled via `database.py` for better performance
- All services share the same database and Redis instances
- Logs are available in real-time in the Railway dashboard

## Questions?

Check Railway documentation: https://docs.railway.app
