"""Gmail over IMAP (inbound) and SMTP (outbound), using an App Password.

The blocking imaplib/smtplib calls are run in worker threads by the callers.
"""
from __future__ import annotations

import email
import html
import imaplib
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formataddr, getaddresses, make_msgid, parseaddr

from .config import settings

log = logging.getLogger(__name__)


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class InboundEmail:
    uid: str
    message_id: str
    sender: str            # bare address, lower-case
    sender_name: str
    subject: str
    text: str
    in_reply_to: str = ""
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def is_reply(self) -> bool:
        return bool(self.in_reply_to) or self.subject.lower().startswith(("re:", "aw:"))

    @property
    def pdfs(self) -> list[Attachment]:
        return [a for a in self.attachments
                if a.content_type == "application/pdf" or a.filename.lower().endswith(".pdf")]


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    markup = re.sub(r"(?i)<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _body_and_attachments(msg: Message) -> tuple[str, list[Attachment]]:
    plain, rich, attachments = [], [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disposition = (part.get("Content-Disposition") or "").lower()
        filename = _decode(part.get_filename())
        payload = part.get_payload(decode=True) or b""
        if filename or "attachment" in disposition:
            attachments.append(Attachment(filename or "attachment", ctype, payload))
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if ctype == "text/plain":
            plain.append(text)
        elif ctype == "text/html":
            rich.append(text)
    body = "\n".join(plain).strip() or html_to_text("\n".join(rich))
    return body, attachments


_QUOTE_MARKERS = re.compile(
    r"^(On .+wrote:|-{2,} ?Original Message ?-{2,}|From: .+|Sent from my .+)$", re.IGNORECASE
)


def strip_quoted(text: str) -> str:
    """Keep only the new part of an email reply."""
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if _QUOTE_MARKERS.match(stripped):
            break
        if stripped.startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def parse_message(uid: str, raw: bytes) -> InboundEmail:
    msg = email.message_from_bytes(raw)
    name, addr = parseaddr(_decode(msg.get("From")))
    body, attachments = _body_and_attachments(msg)
    message_id = (msg.get("Message-ID") or "").strip() or f"<uid-{uid}@{settings.imap_host}>"
    return InboundEmail(
        uid=uid,
        message_id=message_id,
        sender=addr.lower(),
        sender_name=name,
        subject=_decode(msg.get("Subject")),
        text=body,
        in_reply_to=(msg.get("In-Reply-To") or "").strip(),
        attachments=attachments,
    )


def fetch_unseen(limit: int = 25) -> list[InboundEmail]:
    """Fetch UNSEEN mail without marking it; call mark_seen() once it is handled."""
    out: list[InboundEmail] = []
    with imaplib.IMAP4_SSL(settings.imap_host) as imap:
        imap.login(settings.gmail_address, settings.gmail_app_password)
        imap.select(settings.imap_folder)
        status, data = imap.uid("search", None, "UNSEEN")
        if status != "OK":
            return out
        for uid in data[0].split()[:limit]:
            status, parts = imap.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            try:
                out.append(parse_message(uid.decode(), parts[0][1]))
            except Exception:
                log.exception("Could not parse email uid %s", uid)
    return out


def mark_seen(uids: list[str]) -> None:
    if not uids:
        return
    with imaplib.IMAP4_SSL(settings.imap_host) as imap:
        imap.login(settings.gmail_address, settings.gmail_app_password)
        imap.select(settings.imap_folder)
        for uid in uids:
            imap.uid("store", uid, "+FLAGS", "(\\Seen)")


def send_email(to: list[str] | str, subject: str, body: str, reply_to: str | None = None) -> None:
    recipients = [to] if isinstance(to, str) else to
    recipients = [addr for _, addr in getaddresses(recipients) if addr]
    if not recipients:
        return
    msg = EmailMessage()
    msg["From"] = formataddr((settings.mail_from_name, settings.gmail_address))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as smtp:
            smtp.login(settings.gmail_address, settings.gmail_app_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.gmail_address, settings.gmail_app_password)
            smtp.send_message(msg)
