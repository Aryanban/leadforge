from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, JSON, event
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    #: The seniority band the title falls into ("owner", "c_level", "vp",
    #: "director", "head", "manager", "senior", "staff", "other",
    #: "unknown"). Stored rather than computed on read because the People
    #: table filters on it in SQL, and an unindexed Python classification
    #: over every row is exactly the query that times out.
    seniority = Column(String, nullable=True, index=True)
    #: Whether this contact is a *person* as opposed to a business-level
    #: outreach target.
    #:
    #: Discovery finds businesses, not people. The row it creates carries the
    #: business's phone and WhatsApp number, but there is no human behind it -
    #: so its name and title were being *invented* ("Gurucity", "Owner /
    #: Decision Maker"). Classifying those inventions made 126 of 149 rows
    #: look like founders, and the decision-maker filter answered with a
    #: number that was fiction.
    #:
    #: Set to True only when a real human was identified - a name and a
    #: title found on the company's own site.
    person_identified = Column(Boolean, default=False, index=True)
    #: Whether this person can actually say yes. Derived from the band.
    is_decision_maker = Column(Boolean, nullable=True, index=True)
    linkedin_url = Column(String, nullable=True)
    email = Column(String, index=True, nullable=True)
    phone = Column(String, nullable=True)
    whatsapp_link = Column(String, nullable=True)
    social_links = Column(JSON, nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_status = Column(String, default="pending")  # valid, invalid, catch_all, unverified
    # Granular status from app.verifier.email_status.EmailStatus (e.g. "greylisted",
    # "role_account", "possible_typo"). "status" alone is too coarse to explain a
    # result or to re-verify cheaply, and "valid_mx" was previously overloaded.
    verification_sub_status = Column(String, nullable=True)
    # 0.0-1.0 deliverability confidence, and the raw SMTP/MX detail behind it.
    verification_confidence = Column(Float, nullable=True)
    verification_detail = Column(String, nullable=True)
    mx_host = Column(String, nullable=True)
    # Role addresses (info@/sales@) are valid leads on an SMB site but must never
    # be counted as "person found", which would inflate lead counts.
    is_role_account = Column(Boolean, default=False)
    # Free/webmail (gmail, zoho...). A quality signal for India SMBs, not a reject.
    is_free_email = Column(Boolean, default=False)
    # Outreach routing decided from the line type at discovery time.
    preferred_channel = Column(String, nullable=True)
    unsubscribed = Column(Boolean, default=False)
    source = Column(String, nullable=True)  # e.g., "website", "maps", "enricher"
    # Free-form per-contact facts (STD-derived city, line type, pattern used...).
    extra_data = Column(JSON, nullable=True)
    # Set when an email was actually verified, so stale verdicts can be re-checked.
    verified_at = Column(DateTime(timezone=True), nullable=True)
    # Unlike verified_at, this is recorded for both positive and negative
    # verifier results. It lets source quality use recent checked/verified
    # denominators instead of treating unchecked contacts as failures.
    verification_checked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    business = relationship("Business", back_populates="contacts")


#: The title the discovery path used to invent for every business it
#: found. It is not a person's title - it is a placeholder that was being
#: classified as "owner" and counted as a founder.
FABRICATED_TITLE = "Owner / Decision Maker"


def _populate_seniority(mapper, connection, target):
    """Derives the seniority band and the decision-maker flag from the title.

    The People table filters on seniority in SQL, so the band has to be a
    column rather than something computed per request. Deriving it on write
    means the crawler, the importer, the API and the backfill all agree -
    there is no second place where a title can be classified differently.
    """
    from app.enricher.seniority import classify_seniority, is_decision_maker

    title = (target.title or "").strip()
    if not title:
        # No title, so there is no band - but a human can be identified by
        # name alone, so whatever the caller decided about that is kept.
        target.seniority = None
        target.is_decision_maker = False
        return

    if title.lower() == FABRICATED_TITLE.lower():
        # The invented placeholder: not a person, no band.
        target.seniority = None
        target.is_decision_maker = False
        target.person_identified = False
        return

    band = classify_seniority(title)
    target.seniority = band
    target.is_decision_maker = is_decision_maker(band)
    target.person_identified = True


event.listen(Contact, "before_insert", _populate_seniority)
event.listen(Contact, "before_update", _populate_seniority)
