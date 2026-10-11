from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class CampaignStep(Base):
    __tablename__ = "campaign_steps"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))
    step_number = Column(Integer)
    subject = Column(String)
    body_text = Column(Text)
    body_html = Column(Text, nullable=True)
    delay_days = Column(Integer, default=0) # Days to wait after previous step

    campaign = relationship("Campaign", back_populates="steps")


class CampaignTarget(Base):
    """Explicit campaign recipients — the Apollo "select leads → Add to Sequence" model.

    Without this, campaigns blast every eligible contact in the database.
    With it, a campaign is scoped to the leads the operator actually picked.
    An empty target set keeps the legacy all-eligible behaviour so existing
    campaigns are not stranded.
    """
    __tablename__ = "campaign_targets"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
