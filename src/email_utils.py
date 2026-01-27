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

logger = logging.getLogger(__name__)


def get_email_config():
    """Get email configuration from environment variables"""
    return {
        'host': os.getenv('EMAIL_HOST', 'smtp.gmail.com'),
        'port': int(os.getenv('EMAIL_PORT', '587')),
        'user': os.getenv('EMAIL_HOST_USER'),
        'password': os.getenv('EMAIL_HOST_PASSWORD'),
        'from_name': os.getenv('EMAIL_FROM_NAME', 'Affairs and Order'),
        'base_url': os.getenv('BASE_URL', 'https://affairsandorder.com'),
    }


def is_email_configured():
    """Check if email sending is properly configured"""
    config = get_email_config()
    return bool(config['user'] and config['password'])


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
        cur.execute("""
            SELECT email, token_created_at 
            FROM users 
            WHERE verification_token = %s
        """, (token,))
        
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
    Send an email using SMTP.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML body of the email
        text_content: Plain text fallback (optional)
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    config = get_email_config()
    
    if not is_email_configured():
        logger.warning("Email not configured - EMAIL_HOST_USER and EMAIL_HOST_PASSWORD required")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{config['from_name']} <{config['user']}>"
        message["To"] = to_email
        
        # Add plain text version
        if text_content:
            part1 = MIMEText(text_content, "plain")
            message.attach(part1)
        
        # Add HTML version
        part2 = MIMEText(html_content, "html")
        message.attach(part2)
        
        # Connect and send
        context = ssl.create_default_context()
        
        with smtplib.SMTP(config['host'], config['port']) as server:
            server.starttls(context=context)
            server.login(config['user'], config['password'])
            server.sendmail(config['user'], to_email, message.as_string())
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending email: {e}")
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
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1a1a2e; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 30px; background: #f9f9f9; }}
            .button {{ 
                display: inline-block; 
                background: #4CAF50; 
                color: white; 
                padding: 12px 30px; 
                text-decoration: none; 
                border-radius: 5px;
                margin: 20px 0;
            }}
            .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
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
                <p>Please verify your email address by clicking the button below:</p>
                <p style="text-align: center;">
                    <a href="{verify_url}" class="button">Verify Email</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #666;">{verify_url}</p>
                <p><strong>This link expires in 24 hours.</strong></p>
                <p>If you didn't create this account, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>© 2026 Affairs and Order. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Welcome to Affairs and Order, {username}!
    
    Please verify your email address by visiting:
    {verify_url}
    
    This link expires in 24 hours.
    
    If you didn't create this account, you can safely ignore this email.
    """
    
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
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1a1a2e; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 30px; background: #f9f9f9; }}
            .button {{ 
                display: inline-block; 
                background: #2196F3; 
                color: white; 
                padding: 12px 30px; 
                text-decoration: none; 
                border-radius: 5px;
                margin: 20px 0;
            }}
            .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
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
                <p>We received a request to reset your password. Click the button below to create a new password:</p>
                <p style="text-align: center;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #666;">{reset_url}</p>
                <p><strong>This link expires in 1 hour.</strong></p>
                <p>If you didn't request this, you can safely ignore this email. Your password will remain unchanged.</p>
            </div>
            <div class="footer">
                <p>© 2026 Affairs and Order. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Password Reset Request
    
    Hello {username},
    
    We received a request to reset your password. Visit this link to create a new password:
    {reset_url}
    
    This link expires in 1 hour.
    
    If you didn't request this, you can safely ignore this email.
    """
    
    return send_email(to_email, subject, html_content, text_content)
