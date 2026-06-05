from database import get_request_cursor

class AdRepository:
    def create_ad(self, user_id, image_url, target_url, ad_type):
        with get_request_cursor() as db:
            db.execute(
                "INSERT INTO advertisements (user_id, image_url, target_url, ad_type) VALUES (%s, %s, %s, %s)",
                (user_id, image_url, target_url, ad_type)
            )
            
    def get_ads_by_user(self, user_id):
        with get_request_cursor(read_only=True) as db:
            db.execute(
                "SELECT image_url, target_url, ad_type, status FROM advertisements WHERE user_id = %s ORDER BY created_at DESC", 
                (user_id,)
            )
            return db.fetchall()
            
    def get_pending_ads(self):
        with get_request_cursor(read_only=True) as db:
            db.execute(
                "SELECT id, user_id, image_url, target_url, ad_type, status, created_at FROM advertisements WHERE status = 'pending' ORDER BY created_at ASC"
            )
            return db.fetchall()
            
    def update_ad_status(self, ad_id, status):
        with get_request_cursor() as db:
            db.execute("UPDATE advertisements SET status = %s WHERE id = %s", (status, ad_id))
