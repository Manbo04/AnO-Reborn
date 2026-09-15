from urllib.parse import urlsplit

from app_core.ads.repositories import AdRepository


def _is_safe_ad_url(url, allow_relative=False):
    """Reject any scheme except http/https (and, for image_url, a same-site
    relative path). Both `target_url` and `image_url` are rendered directly
    into `<a href=...>`/`<img src=...>` in templates/admin_ads.html and
    templates/partials/side_ads.html with no further sanitization -- Jinja's
    autoescaping only escapes HTML-special characters, it does not stop a
    `javascript:...` value from being placed verbatim as an href/src
    attribute. Found 2026-09-13: this let ANY logged-in player (the /ads
    submit form has no elevated-permission gate, just @login_required)
    submit a `javascript:` target_url that would execute in the browser of
    whichever admin opens /admin/ads to review the pending submission --
    admin_ads.html explicitly renders "URL: <a href=target_url>" inviting a
    click before approve/reject. A javascript: URI needs no HTML metachars
    to be dangerous, so this was never caught by output escaping alone.
    """
    if not url:
        return False
    if allow_relative and url.startswith("/") and not url.startswith("//"):
        return True
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return False
    return scheme in ("http", "https")


class AdService:
    def __init__(self):
        self.repo = AdRepository()

    def submit_ad(self, user_id, image_url, target_url, ad_type, image_data=None):
        if not image_url or not target_url or not ad_type:
            return False, "All fields are required."

        if not _is_safe_ad_url(target_url):
            return False, "Target URL must be a valid http:// or https:// link."

        if not _is_safe_ad_url(image_url, allow_relative=True):
            return False, "Image URL must be a valid http:// or https:// link."

        if ad_type not in ["top", "side"]:
            return False, "Invalid ad type."

        self.repo.create_ad(user_id, image_url, target_url, ad_type, image_data=image_data)
        return True, "Advertisement submitted! It will appear once an admin approves it."
        
    def get_user_ads(self, user_id):
        return self.repo.get_ads_by_user(user_id)
        
    def get_pending_ads(self):
        return self.repo.get_pending_ads()

    def get_ad_image(self, ad_id):
        return self.repo.get_ad_image(ad_id)
        
    def process_ad_action(self, ad_id, action):
        if action not in ["approve", "reject"]:
            return False, "Invalid action."
            
        status = "approved" if action == "approve" else "rejected"
        self.repo.update_ad_status(ad_id, status)
        from app_core.ads.helpers import reset_ad_cache

        reset_ad_cache()
        return True, f"Advertisement {status}!"
