"""
Email utility module for sending verification and notification emails.

Required environment variables:
- EMAIL_HOST: SMTP server (default: smtp.gmail.com)
- EMAIL_PORT: SMTP port (default: 587)
- EMAIL_HOST_USER: Email address to send from
- EMAIL_HOST_PASSWORD: App password (for Gmail) or API key
- EMAIL_FROM_NAME: Display name (default: Affairs and Order)
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import uuid
from datetime import datetime
import textwrap

logger = logging.getLogger(__name__)


def get_email_config():
    """Get email configuration from environment variables"""
    return {
        "host": os.getenv("EMAIL_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("EMAIL_PORT", "587")),
        "user": os.getenv("EMAIL_HOST_USER"),
        "password": os.getenv("EMAIL_HOST_PASSWORD"),
        "from_name": os.getenv("EMAIL_FROM_NAME", "Affairs and Order"),
        "base_url": os.getenv("BASE_URL", "https://affairsandorder.com"),
    }


def is_email_configured():
    """Check if email sending is properly configured (SMTP or Resend)"""
    import os
    config = get_email_config()
    # Check for SMTP config
    if config["user"] and config["password"]:
        return True
    # Check for Resend config
    if os.getenv("RESEND_API_KEY"):
        return True
    return False


def generate_verification_token(email):
    """Generate a unique verification token that encodes the email"""
    import hashlib
    import time

    # Create a token that includes email hash and timestamp for uniqueness
    token_base = f"{email}:{time.time()}:{uuid.uuid4()}"
    return hashlib.sha256(token_base.encode()).hexdigest()


def verify_email_token(token):
    """
    Verify a token and return the associated email if valid.
    This looks up the token in the database to find the associated user.

    Args:
        token: The verification token from the email link

    Returns:
        str: The email address if valid, None otherwise
    """
    from database import get_connection
    from datetime import timedelta

    if not token:
        return None

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Find user with this token, check it's not expired (24 hour validity)
        cur.execute(
            """
            SELECT email, token_created_at
            FROM users
            WHERE verification_token = %s
        """,
            (token,),
        )

        result = cur.fetchone()
        cur.close()
        conn.close()

        if not result:
            return None

        email, token_created_at = result

        # Check if token is expired (24 hours)
        if token_created_at:
            expiry_time = token_created_at + timedelta(hours=24)
            if datetime.now() > expiry_time:
                logger.warning(f"Verification token expired for {email}")
                return None

        return email

    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return None




def send_email(to_email, subject, html_content, text_content=None):
    """
    Send an email. Tries Resend API first, falls back to SMTP.
    """
    import os
    import logging

    logger = logging.getLogger(__name__)
    config = get_email_config()
    
    # --- Try Resend ---
    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        try:
            import resend
            resend.api_key = resend_api_key
            
            from_email = config.get('user', 'onboarding@resend.dev')
            if not from_email or '@' not in from_email:
                from_email = 'onboarding@resend.dev'
                
            params = {
                "from": f"{config.get('from_name', 'Affairs and Order')} <{from_email}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            if text_content:
                params["text"] = text_content

            resend.Emails.send(params)
            logger.info(f"Email sent successfully to {to_email} via Resend")
            return True
        except ImportError:
            logger.debug("Resend library not installed, falling back to SMTP")
        except Exception as e:
            logger.error(f"Error sending email via Resend: {e}")
            # Fall through to SMTP

    # --- Try SMTP ---
    if config["user"] and config["password"]:
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{config['from_name']} <{config['user']}>"
            message["To"] = to_email

            if text_content:
                message.attach(MIMEText(text_content, "plain"))
            message.attach(MIMEText(html_content, "html"))

            # Connect and send
            context = ssl.create_default_context()
            with smtplib.SMTP(config["host"], config["port"]) as server:
                server.starttls(context=context)
                server.login(config["user"], config["password"])
                server.sendmail(config["user"], to_email, message.as_string())

            logger.info(f"Email sent successfully to {to_email} via SMTP")
            return True
        except Exception as e:
            logger.error(f"Error sending email via SMTP: {e}")

    logger.error(f"Failed to send email to {to_email}: No provider configured or all failed")
    return False

def send_verification_email(to_email, username, token):
    """
    Send a verification email to a new user.

    Args:
        to_email: User's email address
        username: User's username/nation name
        token: Verification token

    Returns:
        bool: True if sent successfully
    """
    config = get_email_config()
    verify_url = f"{config['base_url']}/verify?token={token}"

    subject = "Verify your Affairs and Order account"

    html_content = textwrap.dedent(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: #1a1a2e;
                color: white;
                padding: 20px;
                text-align: center;
            }}
            .content {{
                padding: 30px;
                background: #f9f9f9;
            }}
            .button {{
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 12px 30px;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .footer {{
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Affairs and Order</h1>
            </div>
            <div class="content">
                <h2>Welcome, {username}!</h2>
                <p>Thank you for creating your nation in Affairs and Order.</p>
                <p>
                    Please verify your email address by clicking the button below:
                </p>
                <p style="text-align: center;">
                    <a href="{verify_url}" class="button">Verify Email</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #666;">
                    {verify_url}
                </p>
                <p><strong>This link expires in 24 hours.</strong></p>
                <p>If you didn't create this account, you can safely ignore this
                email.</p>
            </div>
            <div class="footer">
                <p>© 2026 Affairs and Order. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    )

    text_content = textwrap.dedent(
        f"""
    Welcome to Affairs and Order, {username}!

    Please verify your email address by visiting:
    {verify_url}

    This link expires in 24 hours.

    If you didn't create this account, you can safely ignore this email.
    """
    )
    return send_email(to_email, subject, html_content, text_content)


def send_password_reset_email(to_email, username, token):
    """
    Send a password reset email.

    Args:
        to_email: User's email address
        username: User's username
        token: Password reset token

    Returns:
        bool: True if sent successfully
    """
    config = get_email_config()
    reset_url = f"{config['base_url']}/reset_password?token={token}"

    subject = "Reset your Affairs and Order password"

    html_content = textwrap.dedent(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: #1a1a2e;
                color: white;
                padding: 20px;
                text-align: center;
            }}
            .content {{
                padding: 30px;
                background: #f9f9f9;
            }}
            .button {{
                display: inline-block;
                background: #2196F3;
                color: white;
                padding: 12px 30px;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .footer {{
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Affairs and Order</h1>
            </div>
            <div class="content">
                <h2>Password Reset Request</h2>
                <p>Hello {username},</p>
                <p>
                    We received a request to reset your password. Click the button
                    below to create a new password:
                </p>
                <p style="text-align: center;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #666;">
                    {reset_url}
                </p>
                <p><strong>This link expires in 1 hour.</strong></p>
                <p>If you didn't request this, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>© 2026 Affairs and Order. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    )

    text_content = textwrap.dedent(
        f"""
    Password Reset Request

    Hello {username},

    We received a request to reset your password. Visit this link to
    create a new password:
    {reset_url}

    This link expires in 1 hour.

    If you didn't request this, you can safely ignore this email.
    """
    )
    return send_email(to_email, subject, html_content, text_content)
