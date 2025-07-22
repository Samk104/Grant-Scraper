from .database import SessionLocal, engine, Base
from .models import Opportunity


def init_db():
    import app.db.models  
    Base.metadata.create_all(bind=engine)
