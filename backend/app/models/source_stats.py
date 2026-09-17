from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class SourceStats(Base):
    __tablename__ = "source_stats"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True, nullable=False)
    niche = Column(String, index=True, nullable=True)
    area = Column(String, index=True, nullable=True)
    leads_found = Column(Integer, default=0)
    enriched = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    hot_leads = Column(Integer, default=0)
    last_run = Column(DateTime(timezone=True), server_default=func.now())

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
