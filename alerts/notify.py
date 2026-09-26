import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


# ── Telegram ──

def send_telegram(message: str) -> bool:
    
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[Alert/Telegram] Not configured — set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to enable.")
        return False

    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("[Alert/Telegram] Message sent successfully.")
        return True
    except requests.RequestException as exc:
        print(f"[Alert/Telegram] Failed to send: {exc}")
        return False


# ── Email ──

def send_email(subject: str, body: str) -> bool:
    
    email_from = os.getenv("EMAIL_FROM")
    password   = os.getenv("EMAIL_PASSWORD")
    email_to   = os.getenv("EMAIL_TO")

    if not all([email_from, password, email_to]):
        print("[Alert/Email] Not configured — set EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO to enable.")
        return False

    # Build a proper MIME email message
    msg            = MIMEMultipart()
    msg["From"]    = email_from
    msg["To"]      = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # Port 465 = SSL from the start (safer than STARTTLS on 587)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(email_from, password)
            server.sendmail(email_from, email_to, msg.as_string())
        print("[Alert/Email] Email sent successfully.")
        return True
    except smtplib.SMTPException as exc:
        print(f"[Alert/Email] Failed to send: {exc}")
        return False


# ── Main dispatch function ──

def notify_anomalies(anomalies: list[dict], city: str) -> None:
   
    if not anomalies:
        print("[Alert] No anomalies to report — nothing sent.")
        return

    # Build the message content
    header = f"Weather Anomaly Alert — {city}"
    lines  = [header, "=" * len(header), ""]

    for row in anomalies:
        lines.append(f"Date:        {row['date']}")
        lines.append(f"Max temp:    {row['temp_max']}°C")
        lines.append(f"Reason:      {row['anomaly_reason']}")
        lines.append("")

    lines.append("View details: https://your-app.onrender.com/anomalies")

    plain_text = "\n".join(lines)

    # Telegram version uses markdown formatting
    telegram_msg = (
        f"*{header}*\n\n"
        + "\n".join(
            f"📅 *{r['date']}* — `{r['temp_max']}°C`\n_{r['anomaly_reason']}_"
            for r in anomalies
        )
        + "\n\n[View all anomalies](https://your-app.onrender.com/anomalies)"
    )

    # Try both channels — each logs its own success/failure message
    send_telegram(telegram_msg)
    send_email(
        subject=f"Weather Anomaly Alert — {city} ({len(anomalies)} day(s))",
        body=plain_text,
    )
