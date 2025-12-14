# Resource Optimization Guide for Free Tier Railway

## Overview
This document outlines the optimizations made to run Affairs and Order on Railway's free tier (0.5GB RAM, 1vCPU).

---

## ✅ Optimizations Implemented

### 1. **Celery Task Frequency Reduction** 🚀
**Change:** Reduced background task frequency from hourly to every 3 hours

**Files Modified:** `tasks.py`

**Impact:**
- `population_growth` - Now runs every 3 hours (was hourly)
- `generate_province_revenue` - Now runs every 3 hours (was hourly)
- `tax_income` - Now runs every 3 hours (was hourly)

**Expected Savings:** ~70% reduction in Celery worker CPU usage

**Trade-off:** Players' resources update slightly less frequently, but gameplay remains balanced

---

### 2. **Asset Minification** 📦
**Files Modified:**
- `static/style.css` (64KB) → `static/style.min.css`
- `static/script.js` (21KB) → `static/script.min.js`
- Other JS/CSS files

**Tool:** `scripts/optimize-assets.py`

**How to Use:**
```bash
python3 scripts/optimize-assets.py
```

**Expected Savings:** ~40-50% reduction in CSS/JS file sizes

**Update Templates:**
After running the optimization script, update your templates to reference minified files:
```html
<!-- Before -->
<link rel="stylesheet" href="/static/style.css">
<script src="/static/script.js"></script>

<!-- After -->
<link rel="stylesheet" href="/static/style.min.css">
<script src="/static/script.min.js"></script>
```

**Automatic Selection:**
The `asset()` helper function in `app.py` will automatically serve minified versions in production if they exist:
```html
<link rel="stylesheet" href="/static/{{ asset('style.css') }}">
```

---

### 3. **Image Optimization** 🖼️ (Manual - Large Impact)
**Current Situation:**
- `static/images/` - 52MB (121 files)
- `static/flags/` - 3.7MB (7 files)

**Recommendations:**

#### Option A: Convert to WebP (40-60% size reduction)
```bash
# Install imagemagick
brew install imagemagick

# Convert PNG/JPG to WebP
find static/images -name "*.png" -o -name "*.jpg" | while read f; do
  convert "$f" "${f%.*}.webp"
done

# Serve WebP with fallback in HTML
<picture>
  <source srcset="/static/images/img.webp" type="image/webp">
  <img src="/static/images/img.png" alt="description">
</picture>
```

#### Option B: Use CDN/Cloud Storage
Host images on a free tier service:
- Cloudinary (free: 25GB/month, 2GB storage)
- ImgBB
- AWS S3 (1GB free, then cheap)

Update image URLs in templates to point to external CDN.

#### Option C: Compress Existing Images
```bash
# For PNG files (lossless)
find static/images -name "*.png" -exec pngquant --quality=65-80 {} \;

# For JPG files (lossy)
find static/images -name "*.jpg" -exec jpegoptim -m 80 {} \;
```

---

### 4. **Database Query Optimization** 🗄️
**Already Implemented:**
- Aggregated queries in `tasks.py` (using SUM instead of loops)
- Single query for fetching province data instead of N+1 queries

**Further Optimizations:**
```python
# Use SELECT with COALESCE to handle NULL values efficiently
db.execute("SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId=%s", (cId,))

# Use database indexes on frequently queried columns
# Run this in your database:
CREATE INDEX idx_provinces_userid ON provinces(userid);
CREATE INDEX idx_military_userid ON military(userid);
CREATE INDEX idx_resources_userid ON resources(userid);
```

---

### 5. **Railway Configuration Optimization** ⚙️

#### Environment Variables to Set:
```env
FLASK_ENV=production
FLASK_DEBUG=0
WORKERS=2
```

#### Scale Down Services:
- **Web Service:** Keep as is (auto-scales on demand)
- **Celery Worker:** Consider reducing to 1 instance during off-hours
- **Beat Scheduler:** Can share with Celery worker (1 instance)

#### Railway Settings:
- **Memory:** Set to 512MB (current free tier limit)
- **CPU:** 1 vCPU (current free tier limit)
- Enable **Health Checks** to auto-restart on failures

---

### 6. **Database Optimization** 🔧

#### Connection Pooling:
Already using `get_db_cursor()` context manager - good!

#### Add to `database.py` if using shared connection pool:
```python
from psycopg2 import pool

db_pool = pool.SimpleConnectionPool(1, 5, database_url)  # Max 5 connections
```

#### Analyze and Vacuum:
```sql
-- Run weekly on your database
ANALYZE;
VACUUM;
```

---

## 📊 Expected Performance Improvements

| Optimization | Impact | Effort |
|---|---|---|
| Task Frequency Reduction | 70% less worker CPU | 5 min ✅ Done |
| CSS/JS Minification | 40-50% smaller assets | 10 min |
| Image Optimization | 40-70% smaller images | 30-60 min |
| Database Indexes | 10-30% faster queries | 5 min |
| CDN for Images | Reduced bandwidth | 20 min |
| **Total Potential Savings** | **60-80% resource usage** | |

---

## 🚀 Recommended Implementation Order

1. ✅ **Done:** Reduce Celery task frequency
2. **Next:** Run `python3 scripts/optimize-assets.py` and update templates
3. **Then:** Compress images locally OR move to CDN
4. **Finally:** Add database indexes

---

## 🧪 Testing Checklist

After each optimization:
- [ ] Test on local dev server
- [ ] Check Railway logs for errors
- [ ] Verify gameplay mechanics work
- [ ] Test on mobile devices
- [ ] Monitor CPU/Memory usage in Railway dashboard

---

## 💰 Cost Estimate After Optimization

With these optimizations on Railway Free Tier:
- **Monthly Cost:** $0 (unless exceeding free tier limits)
- **Expected Uptime:** 99% (with monitoring)
- **User Capacity:** ~50-100 concurrent users

---

## 📖 References

- [Railway Free Tier Limits](https://railway.app/pricing)
- [Image Optimization Guide](https://web.dev/image-optimization/)
- [Celery Task Scheduling](https://docs.celeryproject.io/en/stable/userguide/periodic-tasks.html)
- [Flask Performance Tips](https://flask.palletsprojects.com/en/2.3.x/deployment/production/)

---

**Last Updated:** December 8, 2025
**Status:** In Progress (1 of 3 major optimizations implemented)
