"""Inbound reply detection over IMAP.

Closes the reply loop: every successful send now stores its ``message_id``
(see ``sender.py``), and this module matches inbound ``In-Reply-To`` /
``References`` headers against stored IDs. Only header matching is trusted —
bare subject sniffing misfires on forwards, digests, and unrelated mail.

Categorisation is rule-based:
  * opt_out      - "stop", "unsubscribe", "remove me", ... -> also adds
a full ``replied_stop`` suppression (compliance gate 4 of 4).
  * interested   - buy signals ("call me", "interested", "let's talk", ...)
  * not_interested - soft no's ("not interested", "no thanks", "later", ...)
  * out_of_office - auto-reply headers OR body phrases.
  * other        - everything else (humans triage it in the Inbox page).

Only the *authored* part of the reply (above our own unsubscribe footer) is
examined, so our own "To stop receiving these emails" footer never
mis-categorises a human reply as opt-out.
"""

import asyncio
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from app.database import async_session_maker
from app.models.mailbox import Mailbox
from app.models.send import Send
from app.models.contact import Contact
from app.campaigns.suppression import add_suppression
from app.campaigns.bounces import HARD

logger = logging.getLogger(__name__)

#: Anything above this line is our own footer (quoted back by the reply).
_FOOTER_CUT = "To stop receiving these emails"

#: Auto-reply headers that mean "nobody read this".
_AUTO_HEADERS = ("auto-submitted", "x-autoreply", "x-autorespond", "x-autoresponder")

_OPT_OUT = (
    "unsubscribe", "remove me", "do not contact", "take me off",
    "do not email", "stop emailing", "stop contacting", "opt out", "opt-out",
)
_INTERESTED = (
    "interested", "call me", "let's talk", "lets talk", "tell me more",
    "sounds good", "sounds interesting", "book a call", "schedule a call",
    "send me", "more info", "works for me", "yes please", "count me in",
    "let me know", "happy to", "when can we", "pricing", "how much",
)
_NOT_INTERESTED = (
    "not interested", "no interest", "no thanks", "not a priority",
    "not right now", "maybe later", "circle back", "wrong person",
    "already have", "we're all set", "we are all set", "not looking",
    "pass for now", "no need", "don't need",
)
_OOO_BODY = ("out of office", "out of the office", "on leave", "auto-reply",
              "autoreply", "automatic reply", "will be back")

_STOP_ALONE = re.compile(r"^\s*(?:please\s+)?stop\.?\s*$", re.IGNORECASE | re.MULTILINE)


def derive_imap_host(smtp_host: Optional[str]) -> Optional[str]:
    """``smtp`` -> ``imap`` host swap. Returns None when it can't tell."""
    host = (smtp_host or "").strip().lower()
    if not host:
        return None
    parts = host.split(".")
    if parts[0] in ("smtp", "smtp-mail", "mail"):
        return ".".join(["imap"] + parts[1:])
    return None


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    out: List[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(charset or "utf-8", "replace"))
            except Exception:
                out.append(chunk.decode("utf-8", "replace"))
        else:
            out.append(chunk)
    return " ".join(out)


def authored_text(raw_body: str) -> str:
    """Reply text ABOVE our own quoted unsubscribe footer."""
    head = raw_body.split(_FOOTER_CUT, 1)[0]
    # Strip common quoted-history separators too.
    head = re.split(r"(?im)^\s*(on\s.+wrote:|[-_]{3,}|from:.+sent:.+)\s*$", head)[0]
    return head.strip()


def categorize_reply(subject: str, body: str, headers: Optional[Dict[str, str]] = None
                     ) -> Tuple[str, bool]:
    """``(category, is_opt_out)`` for a human reply."""
    headers = {str(k).lower(): v for k, v in (headers or {}).items()}
    for h in _AUTO_HEADERS:
        if headers.get(h):
            return "out_of_office", False
    body_authored = authored_text(_decode(body)).strip().lower()
    full = authored_text(f"{_decode(subject)} {_decode(body)}").strip().lower()
    if not full:
        return "other", False
    # A bare "stop" must be judged on the BODY alone — the reply subject
    # ("Re: <our subject>") would otherwise break the standalone match.
    if _STOP_ALONE.search(body_authored) or any(p in full for p in _OPT_OUT):
        return "opt_out", True
    if any(p in full for p in _OOO_BODY):
        return "out_of_office", False
    # Negative BEFORE positive: "not interested" contains "interested" and
    # must not classify as a buy signal.
    if any(p in full for p in _NOT_INTERESTED):
        return "not_interested", False
    if any(p in full for p in _INTERESTED):
        return "interested", False
    return "other", False


def thread_references(msg) -> List[str]:
    """Every Message-ID the inbound mail claims to reply to."""
    refs: List[str] = []
    for header in ("In-Reply-To", "References"):
        raw = msg.get(header) or ""
        refs.extend(re.findall(r"<[^>\s]+>", raw))
    return refs


def extract_reply_body(msg) -> str:
    """Best-effort plain text of an inbound message (first 2000 chars)."""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = (part.get("Content-Disposition") or "").lower()
                if ctype == "text/plain" and "attachment" not in disp:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, "replace")[:2000]
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True) or b""
                    html = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return re.sub(r"<[^>]+>", " ", html)[:2000]
            return ""
        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload() or "")[:2000]
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, "replace")[:2000]
    except Exception:  # pragma: no cover - never break a poll
        return ""


def _fetch_since(imap: imaplib.IMAP4_SSL, since_days: int = 14):
    cutoff = (datetime.utcnow() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    typ, data = imap.search(None, "SINCE", cutoff)
    if typ != "OK":
        return []
    return [n for n in (data[0] or b"").split() if n]


def _poll_one_mailbox_sync(mailbox_id: int, email: str, password: str,
                            imap_host: str, imap_port: int) -> Dict[str, int]:
    """Blocking IMAP sweep for one mailbox. Runs in a worker thread."""
    stats = {"seen": 0, "matched": 0, "replies": 0, "opt_outs": 0}
    imap = imaplib.IMAP4_SSL(imap_host, imap_port)
    try:
        imap.login(email, password)
        imap.select("INBOX", readonly=False)
        nums = _fetch_since(imap)
        stats["seen"] = len(nums)
        if not nums:
            return stats
        typ, fetched = imap.fetch(b",".join(nums), "(RFC822)")
        if typ != "OK":
            return stats
        inbound = []
        for i in range(0, len(fetched), 2):
            part = fetched[i]
            if not isinstance(part, tuple) or len(part) < 2:
                continue
            num = part[0].split()[0]
            msg = message_from_bytes(part[1])
            refs = thread_references(msg)
            if not refs:
                continue
            body = extract_reply_body(msg)
            subject = _decode(msg.get("Subject"))
            auto = any(msg.get(h) for h in _AUTO_HEADERS)
            # Carry the headers through. They were collected and then
            # discarded, which made the ``Auto-Submitted`` branch of
            # ``categorize_reply`` dead code at runtime: an out-of-office
            # auto-responder was classified from body text alone, and often
            # not at all. That mattered twice over - it ended the follow-up
            # chain on every lead whose owner travels, and an auto-responder
            # could be counted as a "reply" and pick the A/B winning subject.
            headers = {str(k): v for k, v in msg.items()}
            inbound.append((num, refs, subject, body, auto, headers))
        stats["matched"] = len(inbound)
        if not inbound:
            return stats
        # Match against our stored message-ids OUTSIDE the IMAP loop, in the
        # event loop's thread, via a callback the caller wires up.
        stats["inbound"] = inbound  # type: ignore[assignment]
        return stats
    finally:
        try:
            imap.close()
        except Exception:
            pass
        try:
            imap.logout()
        except Exception:
            pass


async def poll_mailbox(mailbox_id: int) -> Dict[str, int]:
    """Polls one mailbox for replies. Never raises; reports per-stage counts."""
    out: Dict[str, int] = {"seen": 0, "matched": 0, "replies": 0, "opt_outs": 0}
    async with async_session_maker() as db:
        mb = await db.get(Mailbox, mailbox_id)
        if not mb or not mb.is_active:
            return {**out, "error": "mailbox not found or inactive"}
        host = mb.imap_host or derive_imap_host(mb.smtp_host)
        if not host:
            return {**out, "error": "no IMAP host configured"}
        port = mb.imap_port or 993
        known_ids = {
            row[0] for row in (
                await db.execute(
                    select(Send.message_id).where(
                        Send.mailbox_id == mb.id,
                        Send.message_id.isnot(None),
                        Send.replied == False,
                    )
                )
            ).all()
        }
        email, password = mb.email, mb.password
    if not known_ids:
        return out
    try:
        fetch = await asyncio.to_thread(
            _poll_one_mailbox_sync, mailbox_id, email, password, host, port)
    except Exception as exc:
        logger.warning("reply poll failed for %s: %s", email, exc)
        return {**out, "error": str(exc)}
    inbound = fetch.pop("inbound", [])
    out.update({k: int(fetch.get(k, 0)) for k in ("seen", "matched")})
    if not inbound:
        return out
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        for _num, refs, subject, body, _auto, headers in inbound:
            target_id = next((r for r in refs if r in known_ids), None)
            if not target_id:
                continue
            send = (await db.execute(
                select(Send).where(Send.message_id == target_id)
            )).scalars().first()
            if not send or send.replied:
                continue
            # Pass the headers so ``Auto-Submitted`` / ``X-Auto-Reply`` are
            # honoured. Without them an out-of-office auto-responder is
            # indistinguishable from a real reply.
            category, is_opt_out = categorize_reply(subject, body, headers)
            send.replied = True
            send.replied_at = now
            send.reply_category = category
            send.reply_body = authored_text(body)[:500]
            known_ids.discard(target_id)
            if is_opt_out:
                contact = await db.get(Contact, send.contact_id)
                if contact is not None and contact.email:
                    await add_suppression(db, contact.email, "replied_stop",
                                          detail=f"campaign {send.campaign_id}")
                    contact.unsubscribed = True
            out["replies"] += 1
            if is_opt_out:
                out["opt_outs"] += 1
        mb2 = await db.get(Mailbox, mailbox_id)
        if mb2 is not None:
            mb2.imap_last_polled_at = now
        await db.commit()
    return out


async def poll_all_mailboxes() -> Dict[str, int]:
    """Polls every active mailbox that resolves to an IMAP host."""
    totals = {"seen": 0, "matched": 0, "replies": 0, "opt_outs": 0, "errors": 0}
    async with async_session_maker() as db:
        mbs = (await db.execute(
            select(Mailbox.id).where(Mailbox.is_active == True)
        )).scalars().all()
    for mid in mbs:
        res = await poll_mailbox(mid)
        for k in ("seen", "matched", "replies", "opt_outs"):
            totals[k] += int(res.get(k, 0) or 0)
        if res.get("error"):
            totals["errors"] += 1
    return totals
