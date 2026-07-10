# Affairs and Order — Gemini CLI (agy) project notes

## 📱 MOBILE-FIRST UI (non-negotiable)

The game UI **must be mobile-first**. Most players are on phones and tablets.
Design and verify every UI change at mobile width **first**, then enhance for
desktop — never the reverse.

Every mobile bug we've shipped came from building desktop-first:
- The signup / biome-selection page rendered completely unstyled on tablet
  (CSP blocked the cross-domain `.org` stylesheet loaded on a `.com` OAuth page).
- Desktop side-ad rails leaked full-width onto touch devices.
- Province building lists were cramped/clipped on phones.
- Banner and flag images were oversized and filled the screen.

**Rules when touching any template, CSS, or component:**
1. Check it at ~390px (phone) and ~820px (tablet) before it's "done". Desktop is
   the enhancement layer, not the baseline.
2. Cap all images: `max-width: 100%`, bounded heights, `object-fit`. Nothing may
   fill the screen on mobile.
3. Desktop-only chrome (side ad rails, wide multi-column layouts) must be gated
   behind BOTH `min-width` and `pointer: fine`, and must never affect mobile flow
   (use `position: fixed`/`display: none`, not inline blocks).
4. Overflowing lists/panels scroll — they do not shrink to fit
   (`flex-shrink: 0` on rows inside height-capped containers).
5. The app spans two apex domains behind Cloudflare: `.com` serves the OAuth
   signup/login pages (session cookie from `/callback`), `.org` is primary.
   Cross-domain assets during the OAuth flow require BOTH apex domains in the
   CSP `script-src`/`style-src`/`connect-src`. Do not tighten CSP to `'self'`
   only, or `.com` signup pages render unstyled on mobile.

CSS is bundled: edit `static/css/*.css` and run `python3 scripts/bundle_game_css.py`
(regenerates `static/style.css` and the minified `static/style.min.css` that
production serves). Do not hand-edit `style.min.css`.
