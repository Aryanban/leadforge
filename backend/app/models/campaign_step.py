from sqlalchemy import Column, Integer, String, Text, ForeignKey
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
