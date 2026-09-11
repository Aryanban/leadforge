import dns.resolver
import smtplib
import socket
import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "throwawaymail.com", "trashmail.com", "sharklasers.com", "yopmail.com",
    "getairmail.com", "dispostable.com", "maildrop.cc", "fakemailgenerator.com"
}

def verify_email_smtp(email: str, sender_email: str = "verify@leadforge.dev") -> Tuple[bool, str]:
    """
    Verifies an email address using:
    1. Syntax regex verification
    2. Disposable domain blacklist
    3. DNS MX record resolution
    4. Safe SMTP handshake (with fallback if outbound port 25 is blocked)
    """
    if not email or not isinstance(email, str):
        return False, "empty"

    clean_email = email.strip().lower()

    # 1. Syntax check
    if not EMAIL_REGEX.match(clean_email):
        return False, "invalid_syntax"

    try:
        domain = clean_email.split('@')[1]
    except IndexError:
        return False, "invalid_syntax"

    # 2. Disposable domain check
    if domain in DISPOSABLE_DOMAINS:
        return False, "disposable_domain"

    # 3. DNS MX check
    mx_record = None
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3.0
        resolver.lifetime = 3.0
        records = resolver.resolve(domain, 'MX')
        if records:
            mx_record = str(records[0].exchange).rstrip('.')
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False, "invalid_domain"
    except Exception as e:
        logger.debug(f"DNS resolution warning for {domain}: {e}")
        # If DNS fails or times out, check A record fallback
        try:
            resolver.resolve(domain, 'A')
            return True, "valid_domain_a"
        except Exception:
            return False, "unresolvable_domain"

    if not mx_record:
        return False, "no_mx_records"

    # 4. SMTP Handshake (Best Effort)
    # Many cloud and residential ISPs block outbound port 25 to prevent spam.
    # If connection times out or is blocked, the presence of verified MX records proves the domain is legitimate.
    try:
        server = smtplib.SMTP(mx_record, port=25, timeout=4.0)
        server.set_debuglevel(0)
        server.helo("leadforge.dev")
        server.mail(sender_email)
        code, message = server.rcpt(clean_email)
        server.quit()

        if code == 250:
            return True, "valid"
        elif code == 550:
            return False, "mailbox_not_found"
        else:
            return True, f"server_response_{code}"
    except (socket.timeout, socket.error, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
        # Port 25 is blocked or rate-limited by remote mail server; MX record presence indicates valid domain
        return True, "valid_mx"
    except Exception as e:
        logger.debug(f"SMTP check notice for {clean_email}: {e}")
        return True, "valid_mx"


def check_catch_all_domain(domain: str) -> bool:
    """
    Apollo-grade Catch-All probe:
    Probes remote mail server with an intentional nonexistent address.
    If server returns 250 OK, domain is a catch-all (accepts all addresses).
    If server returns 550, domain strictly validates individual mailboxes.
    """
    if not domain or domain in DISPOSABLE_DOMAINS:
        return False

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3.0
        resolver.lifetime = 3.0
        records = resolver.resolve(domain, 'MX')
        if not records:
            return False
        mx_record = str(records[0].exchange).rstrip('.')
    except Exception:
        return False

    probe_address = f"probe_leadforge_chk{abs(hash(domain)) % 999999}@{domain}"
    try:
        server = smtplib.SMTP(mx_record, port=25, timeout=3.5)
        server.set_debuglevel(0)
        server.helo("leadforge.dev")
        server.mail("verify@leadforge.dev")
        code, _ = server.rcpt(probe_address)
        server.quit()
        return code == 250
    except Exception:
        return False
