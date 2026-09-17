from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed
    total_found = Column(Integer, default=0)
    leads_saved = Column(Integer, default=0)
    error = Column(String, nullable=True)
    result = Column(JSON, nullable=True)        # ranked discovery output (best leads)
    icp_profile_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
