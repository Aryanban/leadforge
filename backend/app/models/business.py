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
    #: City and state, derived from ``address`` on every write. The
    #: free-text address is not filterable, so "all owners in Pune" was
    #: impossible without them.
    city = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True, index=True)
    #: ``metro`` / ``tier_2`` / ``tier_3`` - Indian SMB outreach costs and
    #: response rates differ sharply between them.
    market_tier = Column(String, nullable=True, index=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)
    industry = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    maps_url = Column(String, nullable=True)
    #: Company-size and revenue signals scraped from the company's own
    #: site. Apollo filters on these, so without them the ICP cannot be
    #: expressed as "11-50 employees, over 10Cr turnover".
    employee_count = Column(Integer, nullable=True, index=True)
    size_bucket = Column(String, nullable=True)
    revenue = Column(Float, nullable=True)
    revenue_band = Column(String, nullable=True, index=True)
    #: Technology names detected on the company's site.
    technologies = Column(JSON, nullable=True)
    #: The company's GSTIN and Udyam registration, read off its own site.
    #:
    #: These are the two identifiers an Indian business is registered under,
    #: and neither Apollo nor any Western directory knows what they are. The
    #: GSTIN's first two digits are the *registered* state, which is a
    #: stronger location signal than a free-text address.
    gstin = Column(String, nullable=True, index=True)
    udyam_number = Column(String, nullable=True, index=True)
    #: The state the GSTIN is registered in, kept apart from ``state`` (the
    #: address). A mismatch is a real signal - a branch office, a
    #: registered-elsewhere business - and silently preferring one over the
    #: other would hide it.
    gstin_state = Column(String, nullable=True)
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

    #: True for the sample rows a fresh database is seeded with.
    #:
    #: Nullable with no default on purpose: a row written before this column
    #: existed has NULL here, which is exactly what the one-time backfill
    #: looks for. A non-null default would silently mark every legacy row as
    #: "not demo" and the backfill would have nothing to find.
    #:
    #: The overview used to say "83 businesses in your database" when those
    #: 83 were sample rows the operator never found.
    is_demo = Column(Boolean, nullable=True, index=True)

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
    extra = target.extra_data if isinstance(target.extra_data, dict) else {}
    target.is_demo = bool(extra.get("seeded")) or target.source == "google_maps_seed"
    _populate_location(target)


def _populate_location(target):
    """Derives city / state / market tier from the free-text address.

    The People table's most valuable filter is geographic - "every owner in
    Pune" - and the only location the database had was an address blob.
    Deriving it on write means it works on rows that were scraped months
    ago, and it cannot drift from the address the way a hand-entered column
    does.
    """
    from app.locations.india import extract_city_state, market_tier

    city, state = extract_city_state(target.address)
    # These are derived, never operator-set, so they are always assigned -
    # including to None. A conditional assignment cannot *clear* a value
    # that a better parser has since disproved, and a stale city is worse
    # than no city: it puts the lead in a place that does not exist.
    target.city = city
    target.state = state
    target.market_tier = market_tier(city)


event.listen(Business, "before_insert", _populate_identity)
event.listen(Business, "before_update", _populate_identity)
