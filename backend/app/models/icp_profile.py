from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON, ForeignKey
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
    #: Structured criteria. Keywords say *what the business is called*;
    #: these say *what it looks like*, which is the part an operator can
    #: actually set from a sales conversation: "11-50 staff, over 10Cr
    #: turnover, tier-2 cities, decision makers only".
    min_employees = Column(Integer, nullable=True)
    max_employees = Column(Integer, nullable=True)
    revenue_bands = Column(JSON, nullable=True)     # list[str] e.g. ["10-50Cr", "50-100Cr"]
    size_buckets = Column(JSON, nullable=True)      # list[str] e.g. ["11-50", "51-200"]
    market_tiers = Column(JSON, nullable=True)      # list[str] e.g. ["metro", "tier_2"]
    states = Column(JSON, nullable=True)            # list[str] e.g. ["Maharashtra"]
    seniorities = Column(JSON, nullable=True)       # list[str] the roles to target
    decision_makers_only = Column(Boolean, default=False)
    require_email = Column(Boolean, default=False)
    signal_weights = Column(JSON, nullable=True)    # dict[str, float] overrides for scorer weights
    min_score = Column(Integer, default=45)         # gate below which leads are filtered out
    preset = Column(String, default="outreach_quality")
    source_stats = Column(JSON, nullable=True)      # {source_name: {leads, avg_score}} learned over time
    preferred_sources = Column(JSON, nullable=True) # list[str] manual priority override

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    businesses = relationship("Business", back_populates="icp_profile")
