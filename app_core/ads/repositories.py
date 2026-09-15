from psycopg2.extras import RealDictCursor

from database import get_request_cursor

class AdRepository:
    def create_ad(self, user_id, image_url, target_url, ad_type, image_data=None):
        with get_request_cursor() as db:
            db.execute(
                "INSERT INTO advertisements (user_id, image_url, target_url, ad_type, image_data) VALUES (%s, %s, %s, %s, %s)",
                (user_id, image_url, target_url, ad_type, image_data)
            )

    def get_ad_image(self, ad_id):
        """Returns (image_data_b64, image_url) for the serving route, or None."""
        with get_request_cursor(read_only=True) as db:
            db.execute(
                "SELECT image_data, image_url FROM advertisements WHERE id = %s",
                (ad_id,)
            )
            return db.fetchone()
            
    def get_ads_by_user(self, user_id):
        with get_request_cursor(read_only=True) as db:
            db.execute(
                "SELECT image_url, target_url, ad_type, status FROM advertisements WHERE user_id = %s ORDER BY created_at DESC", 
                (user_id,)
            )
            return db.fetchall()
            
    def get_pending_ads(self):
        with get_request_cursor(cursor_factory=RealDictCursor, read_only=True) as db:
            db.execute(
                "SELECT id, user_id, image_url, target_url, ad_type, status, created_at FROM advertisements WHERE status = 'pending' ORDER BY created_at ASC"
            )
            return db.fetchall()
            
    def update_ad_status(self, ad_id, status):
        with get_request_cursor() as db:
            db.execute("UPDATE advertisements SET status = %s WHERE id = %s", (status, ad_id))
