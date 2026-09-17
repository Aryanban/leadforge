from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SocialProfile(Base):
    __tablename__ = "social_profiles"
    __table_args__ = (
        UniqueConstraint("business_id", "platform", name="uq_business_platform"),
    )

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String, index=True, nullable=False)
    url = Column(String, nullable=False)
    handle = Column(String, nullable=True)
    followers = Column(Integer, nullable=True)
    posts_count = Column(Integer, nullable=True)
    last_post_at = Column(DateTime, nullable=True)
    verified = Column(Boolean, default=False)
    source = Column(String, default="website")  # website | direct

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    business = relationship("Business", back_populates="social_profiles")
