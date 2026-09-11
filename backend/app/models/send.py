from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Send(Base):
    __tablename__ = "sends"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))
    step_id = Column(Integer, ForeignKey("campaign_steps.id", ondelete="CASCADE"))
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"))
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True)
    
    status = Column(String, default="pending") # pending, sent, failed
    error_message = Column(String, nullable=True)
    
    opened = Column(Boolean, default=False)
    clicked = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    bounced = Column(Boolean, default=False)
    
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("Campaign", back_populates="sends")
    contact = relationship("Contact")
    mailbox = relationship("Mailbox")
