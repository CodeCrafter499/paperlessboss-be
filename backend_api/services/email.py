import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib
from core.config import settings

logger = logging.getLogger(__name__)

async def send_otp_email(email_to: str, otp: str) -> bool:
    subject = f"Your Verification Code: {otp}"
    body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <h2 style="color: #4f46e5; margin-bottom: 16px;">Welcome to PaperlessBoss!</h2>
            <p>Thank you for signing up. Please use the following 6-digit verification code to complete your registration:</p>
            <div style="font-size: 28px; font-weight: bold; letter-spacing: 6px; padding: 16px 24px; background-color: #f5f3ff; width: fit-content; border-radius: 6px; color: #4f46e5; margin: 24px 0; border: 1px solid #ddd6fe;">
                {otp}
            </div>
            <p>This code is valid for <strong>{settings.OTP_EXPIRY_MINUTES} minutes</strong>. If you did not request this, you can safely ignore this email.</p>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="font-size: 11px; color: #64748b; margin-top: 16px;">
                This is an automated security message from PaperlessBoss. Please do not reply.
            </p>
        </div>
    </body>
    </html>
    """
    
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
        logger.warning(
            "SMTP credentials not fully configured. MOCK EMAIL SENT. "
            "Verification OTP for %s: [%s]", email_to, otp
        )
        print(f"\n=========================================================================")
        print(f"[EMAIL] [MOCK EMAIL SENT] To: {email_to}")
        print(f"[EMAIL] Subject: {subject}")
        print(f"[EMAIL] OTP Code: {otp}")
        print(f"[EMAIL] Expiry: {settings.OTP_EXPIRY_MINUTES} Minutes")
        print(f"=========================================================================\n")
        return True
        
    try:
        message = MIMEMultipart("alternative")
        message["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        message["To"] = email_to
        message["Subject"] = subject
        
        message.attach(MIMEText(body, "html"))
        
        use_tls = False
        if settings.SMTP_PORT == 465:
            use_tls = True
            
        smtp_args = {
            "hostname": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "use_tls": use_tls,
        }
        
        async with aiosmtplib.SMTP(**smtp_args) as smtp:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            await smtp.send_message(message)
            
        logger.info(f"OTP successfully sent to {email_to} via SMTP.")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to send email to {email_to} via SMTP: {e}")
        return False
