# Coalition Flag Storage Issue

## Problem
Coalition and country flags are stored locally in `static/flags/` directory, which is **ephemeral** on Railway deployment. Every time the app redeploys (new commits, service restarts), all uploaded flags are lost.

## Current Implementation
- `coalitions.py:715` - Saves coalition flags to `UPLOAD_FOLDER`
- `countries.py:601, 626` - Saves country flags to `UPLOAD_FOLDER`
- Flags stored as filenames in database (`colNames.flag`, `users.flag`)

## Solutions (Ranked by Implementation Complexity)

### Option 1: Railway Volume (Recommended - Easiest)
Mount a persistent volume to `/app/static/flags`:

```bash
# In Railway dashboard:
# 1. Go to your web service
# 2. Add a volume mount
# 3. Mount path: /app/static/flags
```

Or in `railway.json`:
```json
{
  "build": {},
  "deploy": {
    "volumes": [
      {
        "source": "flags-data",
        "target": "/app/static/flags"
      }
    ]
  }
}
```

**Pros**: No code changes needed
**Cons**: Volume limited to one service, minor monthly cost

### Option 2: Store in PostgreSQL (Medium complexity)
Add a `flag_data` bytea column to store the image binary:

```sql
ALTER TABLE colNames ADD COLUMN flag_data BYTEA;
ALTER TABLE users ADD COLUMN flag_data BYTEA;
```

Then modify the upload code to base64 encode and store in DB:
```python
import base64

# Save
flag_data = base64.b64encode(flag.read()).decode('utf-8')
db.execute("UPDATE colNames SET flag_data=%s WHERE id=%s", (flag_data, colId))

# Load (new route needed)
db.execute("SELECT flag_data FROM colNames WHERE id=%s", (colId,))
return Response(base64.b64decode(flag_data), mimetype='image/png')
```

**Pros**: Persistent, no external services
**Cons**: Increases DB size, needs new serving route

### Option 3: Cloud Storage (S3/Cloudflare R2)
Use cloud object storage for flags.

**Pros**: Scalable, CDN-friendly
**Cons**: External dependency, needs credentials, more code changes

## Quick Fix (Temporary)
If flags keep disappearing, the `static/flags/` directory should be included in the Git repository with a `.gitkeep` file to ensure it exists on deploy. However, this won't preserve user-uploaded images.

## Recommended Action
Use **Option 1 (Railway Volume)** as it requires no code changes and provides persistent storage. Railway volumes are inexpensive (~$0.15/GB/month) and integrate seamlessly with your existing deployment.

## Files to Modify (for Option 2)
- `coalitions.py` lines 700-720
- `countries.py` lines 585-630
- New route needed in `app.py` to serve flags from DB
- Database migration script
