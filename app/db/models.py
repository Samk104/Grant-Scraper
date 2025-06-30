from sqlalchemy import Column, String, Text, Integer, Boolean
from db.database import Base

class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    unique_key = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    deadline = Column(String, nullable=True)
    email = Column(String, nullable=True)
    source = Column(String, nullable=False) 
    scraped_at = Column(String, nullable=False) 
    is_relevant = Column(Boolean, nullable=True)