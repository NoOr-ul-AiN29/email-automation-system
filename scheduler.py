# scheduler.py
# -------------------------------------------------------
# PURPOSE:
#   Find all scheduled emails that are due and send them.
#
#   HOW SCHEDULING WORKS ON VERCEL:
#   There are no background threads on serverless platforms.
#   Instead, Vercel Cron Jobs call the /cron/send-scheduled
#   endpoint every minute (configured in vercel.json).
#   This function runs at that moment, checks for due emails,
#   sends them, and updates their status in the history file.
# -------------------------------------------------------

from datetime import datetime, timezone
from email_service import send_email
from logger        import get_pending, update_record


def process_scheduled_emails() -> dict:
    """
    Check for any scheduled emails whose time has passed, send them,
    and update their status in the history file.

    Returns:
        Summary dict: { sent, failed, total_checked }
    """
    pending = get_pending()

    if not pending:
        print("[scheduler] No pending emails right now.")
        return {"sent": 0, "failed": 0, "total_checked": 0}

    print(f"[scheduler] Found {len(pending)} email(s) to send.")

    sent_count   = 0
    failed_count = 0

    for record in pending:
        record_id = record.get("id")
        to        = record.get("to")
        subject   = record.get("subject")
        body      = record.get("body")

        print(f"[scheduler] Sending ID={record_id} to {to}...")

        success, message = send_email(to=to, subject=subject, body=body)

        if success:
            update_record(record_id, {
                "status":  "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "note":    message,
            })
            sent_count += 1
            print(f"[scheduler] ✅ Sent: {record_id}")
        else:
            update_record(record_id, {
                "status": "failed",
                "note":   message,
            })
            failed_count += 1
            print(f"[scheduler] ❌ Failed: {record_id} — {message}")

    return {
        "sent":          sent_count,
        "failed":        failed_count,
        "total_checked": len(pending),
    }