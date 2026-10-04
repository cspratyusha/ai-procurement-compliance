"""Outgoing email, for password resets.

Off unless a mail server is configured, so a laptop install needs nothing:
without it, forgotten passwords are reset by an administrator, as before.

  SMTP_HOST       the mail server, e.g. smtp.example.gov.in (required to send)
  SMTP_PORT       587 by default
  SMTP_SECURITY   starttls (default), ssl (port 465), or none (a local relay)
  SMTP_USER       login, when the server asks for one
  SMTP_PASSWORD
  SMTP_FROM       the sender, e.g. "Standards engine <no-reply@example.gov.in>"
  PUBLIC_URL      the web address people open the site at, for links in mail,
                  e.g. https://standards.example.gov.in
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("standards-retrieval.mailer")


class MailError(Exception):
    pass


def available() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM") and os.environ.get("PUBLIC_URL"))


def public_url() -> str:
    return (os.environ.get("PUBLIC_URL") or "").rstrip("/")


def send(to: str, subject: str, body: str) -> None:
    """Send a plain-text message, or raise MailError."""
    if not available():
        raise MailError("Email is not set up on this installation.")
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    host = os.environ["SMTP_HOST"]
    security = (os.environ.get("SMTP_SECURITY") or "starttls").lower()
    port = int(os.environ.get("SMTP_PORT") or (465 if security == "ssl" else 587))
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if user:
                server.login(user, password or "")
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("[Mail] Could not send to %s: %s", to, exc)
        raise MailError("The email could not be sent. Try again later, or ask your administrator.") from exc
