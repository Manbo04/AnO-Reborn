from flask import Blueprint, request, render_template, session, redirect, url_for, flash
from helpers import login_required
from admin_tools import SUPER_ADMIN_USER_IDS
from app_core.ads.services import AdService

bp = Blueprint("ads", __name__)
ad_service = AdService()

@bp.route("/ads", methods=["GET", "POST"])
@login_required
def upload_ad():
    """Allows players to submit an advertisement for admin approval."""
    user_id = session.get("user_id")
    
    if request.method == "POST":
        image_url = request.form.get("image_url")
        target_url = request.form.get("target_url")
        ad_type = request.form.get("ad_type")
        
        success, message = ad_service.submit_ad(user_id, image_url, target_url, ad_type)
        if success:
            flash(message, "success")
        else:
            flash(message, "danger")
            
        return redirect(url_for("ads.upload_ad"))
        
    my_ads = ad_service.get_user_ads(user_id)
    return render_template("upload_ad.html", my_ads=my_ads)

@bp.route("/admin/ads", methods=["GET", "POST"])
@login_required
def admin_ads():
    """Admin panel to approve or reject ads."""
    user_id = session.get("user_id")
    if user_id not in SUPER_ADMIN_USER_IDS:
        flash("Unauthorized access.", "danger")
        return redirect("/")
        
    if request.method == "POST":
        ad_id = request.form.get("ad_id")
        action = request.form.get("action") # 'approve' or 'reject'
        
        success, message = ad_service.process_ad_action(ad_id, action)
        if success:
            flash(message, "success")
        else:
            flash(message, "danger")
            
        return redirect(url_for("ads.admin_ads"))

    pending_ads = ad_service.get_pending_ads()
    return render_template("admin_ads.html", pending_ads=pending_ads)
