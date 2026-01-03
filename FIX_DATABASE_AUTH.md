# Fix Database Authentication Error on Railway

## Problem
```
psycopg2.OperationalError: password authentication failed for user "postgres"
connection to server at "postgres.railway.internal" failed
```

## Root Cause
The `DATABASE_URL` environment variable in your Railway service has incorrect or outdated PostgreSQL credentials.

## Solution Steps

### 1. Get Correct Database Credentials

**In Railway Dashboard:**

1. Go to your project: https://railway.app/
2. Click on your **PostgreSQL** service (not the web service)
3. Go to the **Variables** tab
4. Find and copy the **full connection string** from one of these variables:
   - `DATABASE_URL` (internal network only)
   - `DATABASE_PUBLIC_URL` (accessible externally)

The connection string format:
```
postgresql://postgres:PASSWORD@HOSTNAME:PORT/railway
```

### 2. Update Web Service Environment Variables

**In Railway Dashboard:**

1. Click on your **Web Service** (Flask/Gunicorn service)
2. Go to the **Variables** tab
3. Update or add these variables:

   **Option A: Use Railway Variable References (Recommended)**
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   DATABASE_PUBLIC_URL=${{Postgres.DATABASE_PUBLIC_URL}}
   ```

   **Option B: Paste Connection String Directly**
   ```
   DATABASE_URL=postgresql://postgres:YOUR_ACTUAL_PASSWORD@postgres.railway.internal:5432/railway
   ```

4. **Save** the changes

### 3. Redeploy

Railway should automatically redeploy when you change environment variables. If not:

1. Go to the **Deployments** tab
2. Click **Redeploy** on the latest deployment

### 4. Verify

After redeployment, check the logs:
- You should **NOT** see "password authentication failed"
- Tasks should run successfully

---

## Why This Happens

Railway may rotate PostgreSQL passwords for security, or:
- Manual password change in database settings
- Database service was redeployed
- Environment variables were not properly linked

## Prevention

**Always use Railway's variable references** instead of hardcoding credentials:

```bash
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

This ensures credentials are always up-to-date, even if Railway rotates them.

---

## Quick Test Locally

Before deploying, test the connection locally:

1. Copy the `DATABASE_PUBLIC_URL` from Railway
2. Create/update `.env` file:
   ```bash
   DATABASE_PUBLIC_URL=postgresql://postgres:PASSWORD@...
   ```
3. Run the test script:
   ```bash
   python test_db_connection.py
   ```

If it fails locally, the credentials are wrong. Don't deploy until it works.

---

## Common Mistakes

❌ **Using internal URL externally**
```bash
# This only works INSIDE Railway's private network
DATABASE_URL=postgresql://...@postgres.railway.internal:5432/railway
```

✅ **Use public URL for external access**
```bash
# Use this for external connections (local dev, testing)
DATABASE_PUBLIC_URL=postgresql://...@monorail.proxy.rlwy.net:12345/railway
```

❌ **Hardcoded credentials**
```bash
DATABASE_URL=postgresql://postgres:oldpassword123@...
```

✅ **Variable references**
```bash
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

---

## Still Not Working?

### Check Database Service Status

1. In Railway, click your PostgreSQL service
2. Check if it's running (green indicator)
3. Look at database logs for connection attempts

### Check Web Service Logs

```bash
railway logs
```

Look for:
- "Failed to initialize database pool" - wrong credentials
- "could not translate host name" - network issue
- "connection to server ... failed: timeout" - firewall/network

### Nuclear Option: Recreate Database Connection

If all else fails:

1. **Backup your data first!**
2. In PostgreSQL service settings, regenerate password
3. Update `DATABASE_URL` in web service with new connection string
4. Redeploy

---

## Contact Support

If the issue persists after following these steps:
1. Railway Status Page: https://status.railway.app/
2. Railway Discord: https://discord.gg/railway
3. Include error logs and what you've tried
