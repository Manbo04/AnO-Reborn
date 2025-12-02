# Deployment Guide for Affairs & Order

## Quick Deploy Options

### Option 1: Railway (Recommended - Easiest)

**Free Tier**: $5 credit/month, perfect for small-medium traffic

1. **Setup:**
   ```bash
   # Install Railway CLI (optional)
   npm i -g @railway/cli
   
   # Or use web interface at railway.app
   ```

2. **Deploy Steps:**
   - Go to [railway.app](https://railway.app) and sign in with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your AnO repository
   - Railway auto-detects the Procfile

3. **Add Services:**
   - Add PostgreSQL database (click "New" → "Database" → "PostgreSQL")
   - Add Redis (click "New" → "Database" → "Redis")
   - Railway auto-sets DATABASE_URL and REDIS_URL

4. **Environment Variables:**
   Set these in Railway dashboard:
   ```
   ENVIRONMENT=PROD
   SECRET_KEY=<generate-random-string>
   DISCORD_WEBHOOK_URL=<your-webhook>
   ```

5. **Deploy Workers:**
   - Create new service for Celery worker (use same repo)
   - Set start command: `celery -A tasks.celery worker --loglevel=INFO`
   - Create another for beat: `celery -A tasks.celery beat --loglevel=INFO`

**Cost**: Free for ~500 hours/month, then $5-20/month

---

### Option 2: Render.com

**Free Tier**: Available with limitations

1. **Create render.yaml:**
   ```yaml
   services:
     - type: web
       name: ano-web
       env: python
       buildCommand: pip install -r requirements.txt
       startCommand: gunicorn wsgi:app --workers 4
       
     - type: worker
       name: ano-worker
       env: python
       buildCommand: pip install -r requirements.txt
       startCommand: celery -A tasks.celery worker
       
   databases:
     - name: ano-db
       databaseName: ano
       user: ano
   ```

2. Go to [render.com](https://render.com), connect GitHub
3. Create PostgreSQL database
4. Deploy web service and workers

**Cost**: Free tier available, paid starts at $7/month

---

### Option 3: DigitalOcean App Platform

**No free tier but very reliable**

1. Create `app.yaml`:
   ```yaml
   name: affairs-and-order
   services:
     - name: web
       github:
         repo: YOUR-USERNAME/AnO
         branch: master
       run_command: gunicorn wsgi:app --workers 4
       
     - name: worker
       run_command: celery -A tasks.celery worker
       
   databases:
     - name: db
       engine: PG
   ```

2. Push to GitHub
3. Create app at [digitalocean.com/products/app-platform](https://digitalocean.com/products/app-platform)

**Cost**: $5-12/month

---

### Option 4: Self-Host on VPS (Full Control)

**For advanced users, cheapest long-term**

1. **Get VPS** (Linode, DigitalOcean, Vultr): $5-10/month

2. **Setup Script:**
   ```bash
   # Install dependencies
   sudo apt update
   sudo apt install python3-pip postgresql nginx redis-server
   
   # Clone repo
   git clone https://github.com/YOUR-USERNAME/AnO.git
   cd AnO
   
   # Install Python deps
   pip3 install -r requirements.txt
   
   # Setup PostgreSQL
   sudo -u postgres createdb ano
   python3 affo/create_db.py
   
   # Setup systemd services (see below)
   ```

3. **Create systemd services** for:
   - Gunicorn (web server)
   - Celery worker
   - Celery beat
   - Nginx (reverse proxy)

**Cost**: $5-10/month + your time

---

## Recommended for You: Railway

**Why Railway:**
- ✅ Easiest setup (5 minutes)
- ✅ Free tier available
- ✅ Auto-scaling
- ✅ Built-in PostgreSQL & Redis
- ✅ Auto-deploys from GitHub
- ✅ Great for game traffic patterns

**Quick Start:**
```bash
# 1. Push to GitHub (if not already)
git add .
git commit -m "Prepare for deployment"
git push origin master

# 2. Go to railway.app
# 3. "New Project" → "Deploy from GitHub"
# 4. Select AnO repo
# 5. Add PostgreSQL + Redis databases
# 6. Set environment variables
# 7. Deploy! 🚀
```

Your game will be live at: `your-app.railway.app`

---

## Pre-Deployment Checklist

- [ ] Push latest code to GitHub
- [ ] Test database migrations work
- [ ] Set ENVIRONMENT=PROD in .env
- [ ] Generate strong SECRET_KEY
- [ ] Update ALLOWED_HOSTS/CORS if needed
- [ ] Test Celery tasks work
- [ ] Setup monitoring/logging
- [ ] Plan for database backups

---

## Post-Deployment

1. **Custom Domain** (optional):
   - Buy domain (Namecheap, Google Domains)
   - Point to Railway/Render/etc
   - Add in platform settings

2. **Monitoring**:
   - Railway has built-in metrics
   - Add Sentry for error tracking
   - Setup uptime monitoring (UptimeRobot)

3. **Backups**:
   - Railway auto-backs up databases
   - Consider additional backup strategy

Need help with any specific step? Let me know!
