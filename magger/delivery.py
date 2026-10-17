"""SMTP delivery. Credentials are supplied only via environment/Actions secrets."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_to_kindle(document_path: str | Path) -> None:
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or "465")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("KINDLE_SENDER_EMAIL") or username
    recipient = os.environ.get("KINDLE_EMAIL")
    if not all((username, password, sender, recipient)):
        raise RuntimeError("Kindle delivery requires SMTP_USERNAME, SMTP_PASSWORD, and KINDLE_EMAIL secrets; configure them or use --no-email.")
    path = Path(document_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Kindle document is missing or empty: {path}")
    media = {".epub": ("application", "epub+zip"), ".pdf": ("application", "pdf")}
    if path.suffix.lower() not in media:
        raise RuntimeError(f"Unsupported Kindle document type: {path.suffix}")
    message = EmailMessage()
    message["Subject"] = f"Magger Weekly: {path.stem}"
    message["From"] = sender
    message["To"] = recipient
    document_type = "PDF" if path.suffix.lower() == ".pdf" else "EPUB"
    message.set_content(f"Your Magger magazine is attached as a {document_type}. Add the sender address to your Kindle approved personal document senders if required.")
    maintype, subtype = media[path.suffix.lower()]
    message.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)
