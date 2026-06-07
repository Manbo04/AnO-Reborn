# Email setup — affairsandordersupport@gmail.com

## Gmail SMTP (recommended — sends from your support inbox)

### 1. Turn on 2-Step Verification

1. Sign in to [affairsandordersupport@gmail.com](https://mail.google.com) in a browser.
2. Open [Google Account → Security](https://myaccount.google.com/security).
3. Under **How you sign in to Google**, enable **2-Step Verification** and finish the prompts.

### 2. Create an App Password

1. Open [App passwords](https://myaccount.google.com/apppasswords) (only appears after 2-Step Verification is on).
2. App name: `Affairs and Order Railway`
3. Click **Create** and copy the **16-character password** (e.g. `abcd efgh ijkl mnop`).

### 3. Add to Railway (web service)

```bash
cd AnO-Reborn
railway service web
railway variables --set "EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx"
```

Spaces in the app password are optional.

### 4. Verify

```bash
railway run --service web python3 scripts/test_email_send.py dennis.sebalemba@gmail.com
```

Or use **Forgot password** on https://affairsandorder.com/forgot_password

---

## Resend (backup / until Gmail is set)

- API key is on Railway as `RESEND_API_KEY`.
- **Without a verified domain**, Resend only delivers to the Resend account owner (`mantasbonda2@gmail.com`).
- To email all players from `@affairsandorder.com`:
  1. [Resend → Domains](https://resend.com/domains) → Add `affairsandorder.com`
  2. Add the DNS records Resend shows (SPF, DKIM) at your domain registrar
  3. Set `RESEND_FROM=support@affairsandorder.com` on Railway web

---

## Railway variables (web service)

| Variable | Value |
|----------|--------|
| `EMAIL_HOST` | `smtp.gmail.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | `affairsandordersupport@gmail.com` |
| `EMAIL_HOST_PASSWORD` | *(Gmail app password — you add this)* |
| `EMAIL_FROM_NAME` | `Affairs and Order Support` |
| `RESEND_API_KEY` | *(already set)* |
| `BASE_URL` | `https://affairsandorder.com` |
