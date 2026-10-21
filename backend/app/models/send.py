from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Send(Base):
    __tablename__ = "sends"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    step_id = Column(Integer, ForeignKey("campaign_steps.id", ondelete="CASCADE"), index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True, index=True)

    #: pending -> sending -> sent | failed | bounced. "sending" is committed
    #: *before* the SMTP call so a crash mid-flight leaves an auditable row
    #: instead of a delivered email with no record of it.
    status = Column(String, default="pending") # pending, sending, sent, failed, bounced
    error_message = Column(String, nullable=True)
    #: How many times this (campaign, contact, step) has been attempted. A soft
    #: bounce is only suppressed once the retry budget is exhausted - a single
    #: transient gateway blip must not delete a good lead for 30 days.
    attempt = Column(Integer, default=0)
    
    opened = Column(Boolean, default=False)
    clicked = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    bounced = Column(Boolean, default=False)

    #: Our generated Message-ID (RFC 5322) for this send. The reply poller
    #: matches inbound In-Reply-To/References headers against it, which is the
    #: only reliable way to attribute a reply to a send.
    message_id = Column(String, nullable=True, index=True)
    #: When an inbound reply was detected (IMAP poll or manual mark).
    replied_at = Column(DateTime(timezone=True), nullable=True)
    #: interested | not_interested | opt_out | out_of_office | other
    reply_category = Column(String, nullable=True)
    #: First ~500 chars of the inbound reply body, for the Inbox read view.
    reply_body = Column(Text, nullable=True)
    #: Which A/B subject variant this send used ("a"/"b"), NULL when the step
    #: is not an A/B test. Powers per-variant stats and winner selection.
    variant_used = Column(String, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("Campaign", back_populates="sends")
    contact = relationship("Contact")
    mailbox = relationship("Mailbox")
