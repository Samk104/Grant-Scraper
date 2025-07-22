from sqlalchemy.orm import Session
from app.db.models import Opportunity
from app.db.database import SessionLocal
import logging

logger = logging.getLogger(__name__)

def update_opportunity(unique_key: str, update_fields: dict) -> bool:
    db: Session = SessionLocal()
    try:
        db.query(Opportunity).filter(Opportunity.unique_key == unique_key).update(update_fields)
        db.commit()
        logger.info(f"Updated opportunity {unique_key} with fields: {update_fields}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"DB update failed for {unique_key}: {e}")
        return False
    finally:
        db.close()
