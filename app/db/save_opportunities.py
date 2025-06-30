from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db.models import Opportunity
from db.deduplication import compute_opportunity_hash
import logging

logger = logging.getLogger(__name__)

def save_opportunities(opportunities: list[dict], db: Session, source: str) -> int:
    new_count = 0

    for opp in opportunities:
        title = opp.get("title", "").strip()
        url = opp.get("url", "").strip()
        description = opp.get("description", "")
        normalized_description = description.strip().lower()[:100]

        unique_key = compute_opportunity_hash(title, normalized_description, url)

        record = Opportunity(
            unique_key=unique_key,
            title=title or "Not Available",
            url=url or "Not Available",
            description=description or "Not Available",
            tags=opp.get("tags") or "Not Available",
            deadline=opp.get("deadline") or "Not Available",
            email=opp.get("email") or "Not Available",
            source=source,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            is_relevant=opp.get("is_relevant", None)
        )

        try:
            db.add(record)
            db.commit()
            new_count += 1
        except IntegrityError as e:
            db.rollback()
            logger.info(f"⏭️ Skipped duplicate: '{title}' from '{source}' due to integrity error.")
            continue

    return new_count
