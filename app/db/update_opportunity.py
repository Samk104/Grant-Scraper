from sqlalchemy.orm import Session
from app.db.models import Opportunity
from app.db.database import SessionLocal
import logging

logger = logging.getLogger(__name__)

def update_opportunity(db: Session, unique_key: str, update_fields: dict) -> bool:
    try:
        row = db.query(Opportunity).filter(Opportunity.unique_key == unique_key).update(update_fields)
        logger.info(f"Updated opportunity {unique_key} with fields: {update_fields} (row={row})")
        return row > 0
    except Exception as e:
        logger.error(f"DB update failed for {unique_key}: {e}")
        return False
