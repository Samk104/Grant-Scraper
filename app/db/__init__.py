from .database import Base, SessionLocal, get_engine

def init_db():
    import app.db.models  # noqa
    Base.metadata.create_all(bind=get_engine())
