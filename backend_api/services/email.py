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


async def send_contact_email(name: str, email_from: str, subject: str, message_text: str) -> bool:
    subject_line = f"New Contact Request: {subject}"
    body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <h2 style="color: #4f46e5; margin-bottom: 16px;">New Contact Support Query</h2>
            <p><strong>Name:</strong> {name}</p>
            <p><strong>Email:</strong> {email_from}</p>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Message:</strong></p>
            <div style="padding: 16px; background-color: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0; white-space: pre-wrap;">
                {message_text}
            </div>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="font-size: 11px; color: #64748b; margin-top: 16px;">
                This message was sent via the Contact Us form on PaperlessBoss.
            </p>
        </div>
    </body>
    </html>
    """
    
    email_to = settings.EMAILS_FROM_EMAIL
    
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
        logger.warning(
            "SMTP credentials not fully configured. MOCK CONTACT EMAIL SENT."
        )
        print(f"\n=========================================================================")
        print(f"[EMAIL] [MOCK CONTACT EMAIL SENT] To: {email_to}")
        print(f"[EMAIL] From: {email_from} ({name})")
        print(f"[EMAIL] Subject: {subject_line}")
        print(f"[EMAIL] Message: {message_text}")
        print(f"=========================================================================\n")
        return True
        
    try:
        message = MIMEMultipart("alternative")
        message["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        message["To"] = email_to
        message["Reply-To"] = email_from
        message["Subject"] = subject_line
        
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
            
        logger.info(f"Contact email from {email_from} sent to support.")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to send contact email from {email_from} via SMTP: {e}")
        return False

