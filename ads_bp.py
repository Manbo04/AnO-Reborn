from flask import Blueprint, request, render_template, session, redirect, url_for, flash
from helpers import login_required
from database import get_request_cursor

bp = Blueprint("ads", __name__)

@bp.route("/ads", methods=["GET", "POST"])
@login_required
def upload_ad():
    """Allows players to submit an advertisement for admin approval."""
    user_id = session.get("user_id")
    
    if request.method == "POST":
        image_url = request.form.get("image_url")
        target_url = request.form.get("target_url")
        ad_type = request.form.get("ad_type")
        
        if not image_url or not target_url or not ad_type:
            flash("All fields are required.", "danger")
            return redirect(url_for("ads.upload_ad"))
            
        if ad_type not in ["top", "side"]:
            flash("Invalid ad type.", "danger")
            return redirect(url_for("ads.upload_ad"))
            
        with get_request_cursor() as db:
            db.execute(
                "INSERT INTO advertisements (user_id, image_url, target_url, ad_type) VALUES (%s, %s, %s, %s)",
                (user_id, image_url, target_url, ad_type)
            )
        
        flash("Advertisement submitted! It will appear once an admin approves it.", "success")
        return redirect(url_for("ads.upload_ad"))
        
    with get_request_cursor(read_only=True) as db:
        db.execute("SELECT image_url, target_url, ad_type, status FROM advertisements WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        my_ads = db.fetchall()
        
    return render_template("upload_ad.html", my_ads=my_ads)

@bp.route("/admin/ads", methods=["GET", "POST"])
@login_required
def admin_ads():
    """Admin panel to approve or reject ads."""
    # Note: Replace with actual admin check logic! Assuming user_id = 1 is admin for now.
    user_id = session.get("user_id")
    if user_id != 1:
        flash("Unauthorized access.", "danger")
        return redirect("/")
        
    if request.method == "POST":
        ad_id = request.form.get("ad_id")
        action = request.form.get("action") # 'approve' or 'reject'
        
        status = "approved" if action == "approve" else "rejected"
        
        with get_request_cursor() as db:
            db.execute("UPDATE advertisements SET status = %s WHERE id = %s", (status, ad_id))
        flash(f"Advertisement {status}!", "success")
        return redirect(url_for("ads.admin_ads"))

    with get_request_cursor(read_only=True) as db:
        db.execute("SELECT id, user_id, image_url, target_url, ad_type, status, created_at FROM advertisements WHERE status = 'pending' ORDER BY created_at ASC")
        pending_ads = db.fetchall()
        
    return render_template("admin_ads.html", pending_ads=pending_ads)
