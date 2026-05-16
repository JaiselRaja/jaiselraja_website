from sqlalchemy import Column, Integer, String, DateTime
from database import Base
import datetime

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, index=True)
    lesson_topic = Column(String, index=True)
    file_name = Column(String)
    file_path = Column(String)
    upload_date = Column(DateTime, default=datetime.datetime.utcnow)
