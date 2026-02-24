"""
Email utility — sends an HTML digest of job listings via SMTP.

Works with Gmail (using App Passwords), Outlook, and most SMTP servers.

Gmail setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to myaccount.google.com/apppasswords
  3. Generate an App Password for "Mail" → "Windows Computer"
  4. Paste that 16-character password here (not your regular password).
"""

import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)

# Shared cell styles (module-level so they're defined before the HTML builder)
_TH = "padding:10px 12px;text-align:left;border-bottom:2px solid #d0d7e0;font-weight:600;white-space:nowrap;"
_TD = "padding:8px 12px;border-bottom:1px solid #e8e8e8;vertical-align:top;"


def send_job_digest(
    jobs: list,
    sender_email: str,
    sender_password: str,
    recipient_email: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> tuple:
    """
    Send an HTML email digest of the given job list.

    Returns:
        (success: bool, message: str)
    """
    if not jobs:
        return False, "No jobs to send — run a search first."

    missing = [
        label
        for label, val in [
            ("Sender email", sender_email),
            ("App password", sender_password),
            ("Recipient email", recipient_email),
        ]
        if not str(val).strip()
    ]
    if missing:
        return False, f"Missing email settings: {', '.join(missing)}."

    subject = (
        f"RoleRadar — {len(jobs)} jobs — "
        f"{datetime.now().strftime('%d %b %Y')}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email

    html = _build_html_table(jobs)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, int(smtp_port), timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

        logger.info(f"Email digest sent: {len(jobs)} jobs → {recipient_email}")
        return True, f"Email sent to {recipient_email} with {len(jobs)} job listings."

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Authentication failed. For Gmail, create an App Password at "
            "myaccount.google.com/apppasswords (not your regular password)."
        )
    except smtplib.SMTPConnectError as e:
        return False, (
            f"Could not connect to {smtp_server}:{smtp_port}. "
            f"Check server/port settings. ({e})"
        )
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient address refused: {recipient_email}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except OSError as e:
        return False, f"Network error: {e}"
    except Exception as e:
        logger.error(f"Email send error: {e}", exc_info=True)
        return False, f"Unexpected error: {e}"


def _build_html_table(jobs: list) -> str:
    """Build a styled HTML email with job data in a responsive table."""
    now_str = datetime.now().strftime("%d %b %Y %H:%M")
    total = len(jobs)

    rows = ""
    for i, job in enumerate(jobs):
        bg = "#ffffff" if i % 2 == 0 else "#f4f6fb"
        link = (
            f'<a href="{_esc(job.url)}" style="color:#0066cc;text-decoration:none;">View ↗</a>'
            if job.url
            else "—"
        )
        salary = _esc(job.salary) if job.salary else "—"
        date_p = _esc(job.date_posted) if job.date_posted else "—"

        rows += f"""
          <tr style="background:{bg};">
            <td style="{_TD}">{_esc(job.title)}</td>
            <td style="{_TD}">{_esc(job.company)}</td>
            <td style="{_TD}">{_esc(job.location)}</td>
            <td style="{_TD}">{salary}</td>
            <td style="{_TD}">{_esc(job.source)}</td>
            <td style="{_TD}">{date_p}</td>
            <td style="{_TD}">{link}</td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RoleRadar — Job Digest</title>
</head>
<body style="margin:0;padding:20px;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:1020px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.12);">

    <!-- Header -->
    <div style="background:#1f6feb;padding:28px 32px;">
      <h1 style="color:#ffffff;margin:0;font-size:22px;">📡 RoleRadar</h1>
      <p style="color:#9ecfff;margin:8px 0 0;font-size:14px;">
        {total} job listing{"s" if total != 1 else ""} &nbsp;·&nbsp; generated {now_str}
      </p>
    </div>

    <!-- Table -->
    <div style="padding:24px 32px;overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:13px;min-width:680px;">
        <thead>
          <tr style="background:#eaf1fb;">
            <th style="{_TH}">Title</th>
            <th style="{_TH}">Company</th>
            <th style="{_TH}">Location</th>
            <th style="{_TH}">Salary</th>
            <th style="{_TH}">Source</th>
            <th style="{_TH}">Posted</th>
            <th style="{_TH}">Link</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div style="background:#f8f9fa;padding:14px 32px;border-top:1px solid #e0e0e0;">
      <p style="margin:0;font-size:12px;color:#888888;">
        Sent by <strong>RoleRadar</strong> &nbsp;·&nbsp;
        Data sourced from Seek, Indeed, Jora, LinkedIn &amp; more.
      </p>
    </div>

  </div>
</body>
</html>"""


def _esc(text) -> str:
    """Minimal HTML escaping to prevent broken table output."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
