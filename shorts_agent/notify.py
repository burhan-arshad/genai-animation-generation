"""E-mail alerts through SMTP (Gmail app password). Never raises: an alert problem must not break the pipeline."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send(subject: str, body: str) -> bool:
    user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_APP_PASSWORD")
    to = os.getenv("ALERT_TO") or user
    if not (user and pw and to):
        print("[notify] SMTP_USER / SMTP_APP_PASSWORD not set: alert skipped")
        return False
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = user, to, subject
        msg.set_content(body)
        host, port = os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587"))
        ctx = ssl.create_default_context()
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
        else:
            s = smtplib.SMTP(host, port, timeout=30)
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
        with s:
            s.login(user, pw.replace(" ", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[notify] failed: {type(e).__name__}: {e}")
        return False
if __name__ == "__main__":
    print("sent" if send("[shorts-agent] test", "If you can read this, alerts work.") else "not sent")