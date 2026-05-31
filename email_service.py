# email_service.py
# -------------------------------------------------------
# PURPOSE:
#   Send emails using the Resend API (https://resend.com).
#
#   WHY Resend instead of Gmail SMTP?
#   Vercel serverless functions cannot hold a persistent TCP
#   connection for SMTP. Resend uses a simple HTTPS API call
#   which works perfectly in serverless environments.
#
#   FREE TIER: 3,000 emails/month.
# -------------------------------------------------------

import os
import resend
from dotenv import load_dotenv

load_dotenv()

# Configure Resend with the API key from environment
resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL     = os.getenv("FROM_EMAIL", "onboarding@resend.dev")


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Send a plain text email via the Resend API.

    Args:
        to:      Recipient email address (e.g. "user@example.com").
        subject: Email subject line.
        body:    Plain text email body.

    Returns:
        Tuple of (success: bool, message: str).
        success=True  means the email was accepted by Resend.
        success=False means something went wrong; message explains why.
    """
    # Basic validation
    if not resend.api_key:
        return False, "RESEND_API_KEY is not set in environment variables."

    if not to or "@" not in to:
        return False, f"Invalid recipient email: '{to}'"

    if not subject or not subject.strip():
        return False, "Email subject cannot be empty."

    if not body or not body.strip():
        return False, "Email body cannot be empty."

    try:
        params: resend.Emails.SendParams = {
            "from":    FROM_EMAIL,
            "to":      [to.strip()],
            "subject": subject.strip(),
            "text":    body.strip(),
        }

        response = resend.Emails.send(params)

        if response and response.get("id"):
            print(f"[email_service] ✅ Sent to {to} | Resend ID: {response['id']}")
            return True, f"Email sent successfully. Resend ID: {response['id']}"
        else:
            return False, f"Unexpected response from Resend: {response}"

    except Exception as e:
        print(f"[email_service] ❌ Error: {e}")
        return False, f"Error sending email: {str(e)}"