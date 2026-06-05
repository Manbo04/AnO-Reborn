from app_core.ads.repositories import AdRepository

class AdService:
    def __init__(self):
        self.repo = AdRepository()
        
    def submit_ad(self, user_id, image_url, target_url, ad_type):
        if not image_url or not target_url or not ad_type:
            return False, "All fields are required."
            
        if ad_type not in ["top", "side"]:
            return False, "Invalid ad type."
            
        self.repo.create_ad(user_id, image_url, target_url, ad_type)
        return True, "Advertisement submitted! It will appear once an admin approves it."
        
    def get_user_ads(self, user_id):
        return self.repo.get_ads_by_user(user_id)
        
    def get_pending_ads(self):
        return self.repo.get_pending_ads()
        
    def process_ad_action(self, ad_id, action):
        if action not in ["approve", "reject"]:
            return False, "Invalid action."
            
        status = "approved" if action == "approve" else "rejected"
        self.repo.update_ad_status(ad_id, status)
        return True, f"Advertisement {status}!"
