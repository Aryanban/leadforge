from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, event
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True)
    website = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    #: Phone reduced to comparable digits (Indian +91 / leading-0 handled).
    #: Matching on the raw string never worked: the scraper stores whatever
    #: Google returned ("+91 98225 22560") while the dedupe matcher compared a
    #: normalised value ("9822522560") against it, so the phone branch of the
    #: dedupe was dead code. This column is populated automatically on every
    #: write (see the event listener below) and is indexed.
    phone_e164 = Column(String, nullable=True, index=True)
    #: Host-only form of ``website`` ("example.in"). A substring match on the
    #: raw website string made ``example.com`` match
    #: ``smileshop.example.com`` - a silent false merge.
    domain = Column(String, nullable=True, index=True)
    address = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)
    industry = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    maps_url = Column(String, nullable=True)
    extra_data = Column(JSON, nullable=True)

    source = Column(String, nullable=True, index=True)
    icp_profile_id = Column(Integer, ForeignKey("icp_profiles.id"), nullable=True, index=True)
    icp_fit = Column(JSON, nullable=True)

    #: Persisted lead-quality score (0-100). Kept in a column, not only inside
    #: extra_data, so the lead list can sort/filter on it in SQL.
    score = Column(Integer, nullable=True, index=True)

    #: When this lead was last enriched. Without it the "enrich everything"
    #: action had no way to tell a lead that had been enriched from one that
    #: had not, so it re-enriched the same newest rows on every run.
    enriched_at = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contacts = relationship("Contact", back_populates="business", cascade="all, delete-orphan")
    social_profiles = relationship("SocialProfile", back_populates="business", cascade="all, delete-orphan")
    icp_profile = relationship("ICPProfile", back_populates="businesses")


def normalize_phone_e164(raw):
    """Comparable digits for a phone string, handling Indian formats."""
    import re as _re
    if not raw:
        return None
    digits = _re.sub(r"\D", "", str(raw))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits or None


def canonical_domain_of(url):
    """Host-only form of a URL, without the ``www.`` prefix."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(str(url) if "://" in str(url) else f"http://{url}").netloc.lower()
    except Exception:
        return None
    host = host.split(":")[0]
    import re as _re
    host = _re.sub(r"^www\.", "", host).strip()
    return host or None


def _populate_identity(mapper, connection, target):
    """Keeps the derived identity columns in sync on every write.

    An event listener catches EVERY ORM write path - the scraper, the CSV
    importer, the enrichment worker and the API - without any of them having
    to remember. That matters because the dedupe matcher reads these
    columns; a path that forgot to set them would silently produce
    duplicate leads.
    """
    target.phone_e164 = normalize_phone_e164(target.phone)
    target.domain = canonical_domain_of(target.website)


event.listen(Business, "before_insert", _populate_identity)
event.listen(Business, "before_update", _populate_identity)
