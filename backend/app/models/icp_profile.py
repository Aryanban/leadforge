from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ICPProfile(Base):
    __tablename__ = "icp_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    niche = Column(String, index=True, nullable=False)
    area = Column(String, index=True, nullable=True)
    keywords = Column(JSON, nullable=True)          # list[str] — must-match tokens in name/category
    exclude_keywords = Column(JSON, nullable=True)  # list[str] — drop leads matching these
    signal_weights = Column(JSON, nullable=True)    # dict[str, float] overrides for scorer weights
    min_score = Column(Integer, default=45)         # gate below which leads are filtered out
    preset = Column(String, default="outreach_quality")
    source_stats = Column(JSON, nullable=True)      # {source_name: {leads, avg_score}} learned over time
    preferred_sources = Column(JSON, nullable=True) # list[str] manual priority override

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    businesses = relationship("Business", back_populates="icp_profile")
