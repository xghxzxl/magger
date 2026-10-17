"""SMTP delivery. Credentials are supplied only via environment/Actions secrets."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_to_kindle(epub_path: str | Path) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("KINDLE_SENDER_EMAIL") or username
    recipient = os.environ.get("KINDLE_EMAIL")
    if not all((username, password, sender, recipient)):
        raise RuntimeError("Kindle delivery requires SMTP_USERNAME, SMTP_PASSWORD, and KINDLE_EMAIL secrets; configure them or use --no-email.")
    path = Path(epub_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"EPUB file is missing or empty: {path}")
    message = EmailMessage()
    message["Subject"] = f"Magger Weekly: {path.stem}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("Your Magger magazine is attached as an EPUB. Add the sender address to your Kindle approved personal document senders if required.")
    message.add_attachment(path.read_bytes(), maintype="application", subtype="epub+zip", filename=path.name)
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)
