"""Saved lead views (Apollo-style dynamic lists).

A saved view is just a name plus the filter object the Lead Database page
already speaks (search / industry / has_email / verification state). One row
in this table = one clickable saved segment; the query runs live every time.
"""

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class SavedList(Base):
    __tablename__ = "saved_lists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    #: Filter JSON as sent by the dashboard, e.g.
    #: {"search": "Dentist", "industry": "Dental", "has_email": true}
    filters = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())