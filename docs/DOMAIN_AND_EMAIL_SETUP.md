# Domain, SSL, and email setup — affairsandorder.com

One checklist for fixing browser SSL warnings and Resend email verification.

See also: [EMAIL_SETUP.md](EMAIL_SETUP.md) for Gmail SMTP details.

---

## Part A — Browser SSL warning (Cloudflare + Railway)

Players seeing **“connection not private”** or certificate errors are usually hitting a bad URL or Cloudflare SSL mode.

### Current status (check anytime)

```bash
./scripts/check_domain_ssl.sh
```

Apex `affairsandorder.com` should show a valid Cloudflare/Google Trust Services cert. `www` must also resolve after you add DNS below.

### 1. Cloudflare SSL/TLS (do this first)

[Cloudflare Dashboard](https://dash.cloudflare.com) → **affairsandorder.com**

| Setting | Location | Value |
|---------|----------|-------|
| Encryption mode | SSL/TLS → Overview | **Full (strict)** — not Flexible |
| Always Use HTTPS | SSL/TLS → Edge Certificates | **ON** |
| Automatic HTTPS Rewrites | SSL/TLS → Edge Certificates | **ON** |
| Minimum TLS Version | SSL/TLS → Edge Certificates | **1.2** |

**Why:** Flexible SSL terminates HTTPS at Cloudflare but talks HTTP to Railway, which often causes certificate mismatch warnings.

### 2. Add `www` DNS record

Railway **web** service already has `www.affairsandorder.com` registered. Add this in Cloudflare → **DNS → Records**:

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `www` | `8i1cpzl9.up.railway.app` | Proxied (orange cloud) |

(If Railway shows a different target after re-adding the domain, use `railway domain www.affairsandorder.com --service web`.)

Do **not** delete existing apex records (A/CNAME for the live site).

### 3. Railway custom domains

[Railway](https://railway.app) → project **natural-gratitude** → **web** service → **Settings → Networking / Domains**:

1. Confirm `affairsandorder.com` is **Active** with certificate issued.
2. Add `www.affairsandorder.com` if missing; wait until Railway shows verified.

```bash
cd AnO-Reborn
railway service web
railway domain   # lists domains; add www in dashboard if CLI has no add command
```

### 4. App redirect (deployed in code)

`app.py` redirects `www.affairsandorder.com` → `affairsandorder.com` (301). Bookmark the apex URL:

**https://affairsandorder.com**

### 5. Verify

```bash
curl -sI https://affairsandorder.com | head -5
curl -sI https://www.affairsandorder.com | head -5
```

Both should return `HTTP/2 200` or `301` to apex. Ask affected players to use the apex URL and hard-refresh.

---

## Part B — Resend domain verification (email from @affairsandorder.com)

Resend **Failed** means DNS records for sending are missing in Cloudflare. This does **not** block the website — only branded email delivery.

### 1. Add DNS records

[Resend → Domains](https://resend.com/domains) → `affairsandorder.com` → **Records**

**Easiest:** click **Auto configure** (Cloudflare) — Resend inserts SPF/DKIM records.

**Manual:** copy each TXT/CNAME Resend shows into Cloudflare DNS exactly. Do not remove site A/CNAME records.

### 2. Restart verification

After 5–30 minutes (up to 48h):

- Resend domain page → **Restart**
- Status should become **Verified**

### 3. Railway env var (after Verified)

```bash
railway service web
railway variables --set "RESEND_FROM=support@affairsandorder.com"
```

Sender logic: `email_utils.py` uses `RESEND_FROM` when set.

### 4. Test email

```bash
railway run --service web python3 scripts/test_email_send.py you@example.com
```

Or use **Forgot password** at https://affairsandorder.com/forgot_password

**Note:** If `EMAIL_HOST_USER` + `EMAIL_HOST_PASSWORD` (Gmail) are set on Railway, SMTP may already work while Resend domain is pending. Resend verification enables `@affairsandorder.com` From addresses for all recipients.

---

## Quick reference — Railway variables (web service)

| Variable | Purpose |
|----------|---------|
| `BASE_URL` | `https://affairsandorder.com` |
| `RESEND_API_KEY` | Resend API (already set) |
| `RESEND_FROM` | `support@affairsandorder.com` (after domain verified) |
| `EMAIL_HOST_USER` | Gmail sender (optional primary) |
| `EMAIL_HOST_PASSWORD` | Gmail app password |
