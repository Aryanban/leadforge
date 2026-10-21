from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, JSON
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    business = relationship("Business", back_populates="contacts")
