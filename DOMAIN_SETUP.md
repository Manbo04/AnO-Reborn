# Domain Setup Guide

## ✅ Domain Configured

Your game is now running on: **`affairsandorder.com`**

Previous host: `web-production-55d7b.up.railway.app` (still available as fallback)

---

## Step 1: Point Your Domain to Our Server

Go to your **domain registrar** (GoDaddy, Namecheap, Bluehost, Cloudflare, etc.) and find the DNS settings.

### Option A: Using an A Record (Recommended)
1. Find the DNS/A Record section
2. Create or modify the `A` record:
   - **Name:** `@` (or leave blank)
   - **Type:** `A`
   - **Value:** `34.120.112.142` (Railway's IP - ask if this changes)
   - **TTL:** 3600 (default)

### Option B: Using a CNAME Record
1. Find the DNS/CNAME Record section
2. Create a `CNAME` record:
   - **Name:** `www` (or your subdomain)
   - **Type:** `CNAME`
   - **Value:** `web-production-55d7b.up.railway.app`
   - **TTL:** 3600 (default)

---

## Step 2: Verify DNS Propagation

DNS changes take **24-48 hours** to fully propagate. Check if it's live:

### On Mac/Linux:
```bash
nslookup yourdomain.com
dig yourdomain.com
```

### On Windows:
```cmd
nslookup yourdomain.com
```

You should see your domain resolving to the server IP.

---

## Step 3: Tell Us Your Domain

Once DNS is set up, let us know your domain in Discord so we can:
1. Configure SSL/HTTPS certificates
2. Update the game server settings to accept your domain

**Message format:**
```
Domain: yourdomain.com
```

---

## Step 4: We'll Deploy

Once we receive your domain, we'll:
- Configure Railway to use your custom domain
- Set up HTTPS (SSL/TLS)
- Redeploy the server

You'll be able to visit: `https://yourdomain.com` ✅

---

## Troubleshooting

### Domain not resolving?
- Wait 24-48 hours for DNS to propagate
- Clear your browser cache (Ctrl+Shift+Delete or Cmd+Shift+Delete)
- Use a different DNS: Try `8.8.8.8` (Google) instead of your ISP's DNS

### Getting "ERR_NAME_NOT_RESOLVED"?
- DNS hasn't propagated yet, or the record is incorrect
- Double-check the A/CNAME record in your registrar

### Getting "SSL_ERROR_RX_RECORD_TOO_LONG"?
- Usually means the domain isn't fully configured on the server yet
- Wait for admin confirmation after providing domain

---

## Subdomain Support

You can also use subdomains:
- `game.yourdomain.com`
- `play.yourdomain.com`
- `server.yourdomain.com`

Just point the subdomain's DNS record the same way as above.

---

## Questions?

Ask in `#game-info` or contact an admin!
