from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.update_opportunity import update_opportunity
from app.db.models import Opportunity
from app.db.database import SessionLocal
from app.utils.llm.llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)
llm_client = LLMClient()

context = {
    "mission": "Riyaaz Qawwali’s mission is to expose qawwali to new audiences, while still paying homage to traditional qawwali that has been in existence for 700+ years. The ensemble wants to expand the reach of the genre to new stages and people of other faiths and traditions. The founding members of Riyaaz Qawwali chose the qawwali genre of music because it houses unique musical elements in its repertoire that are not found in any other form of South Asian music. Riyaaz Qawwali combines this with poetry from famous South Asian poets of multiple linguistic and religious backgrounds to create a universal message of oneness along with filmmaking in same and similar generes for storytelling",
    "keywords": ["Arts", "Visual Arts", "Texas", "Film Making", "Music", "Houston", "Qawwali", "South Asian", "Cultural Heritage", "Community Engagement"],
    "feedback": "Prioritize grants that mention Houston or Texas or have no location restrictions."
}

def build_grant_text(opportunity: Opportunity) -> str:
    parts = [opportunity.title.strip()]

    if opportunity.description and opportunity.description.strip().lower() != "not available":
        parts.append(opportunity.description.strip())

    if opportunity.deadline and opportunity.deadline.strip().lower() != "not available":
        parts.append(f"Deadline: {opportunity.deadline.strip()}")

    if opportunity.tags and opportunity.tags.strip().lower() != "not available":
        parts.append(f"Tags: {opportunity.tags.strip()}")

    return "\n\n".join(parts)






def process_single_grant(opportunity: Opportunity) -> tuple | None:
    try:
        text = build_grant_text(opportunity)
        llm_info = llm_client.analyze_grant(text, context)
        update_opportunity(opportunity.unique_key, {
                "llm_info": llm_info,
                "is_relevant": llm_info.get("is_relevant"),
            })

        return (opportunity.unique_key, True)
    except Exception as e:
        logger.error(f"Error processing grant {opportunity.unique_key}: {e}")
        return None


def process_new_grants_with_llm(max_workers: int = 4):
    db: Session = SessionLocal()
    try:
        opportunities = db.query(Opportunity).filter(
            or_(
                Opportunity.llm_info == None,
                Opportunity.is_relevant == None
            )
        ).all()
        logger.info(f"Found {len(opportunities)} new grants to process with LLM.")
    finally:
        db.close()

    if not opportunities:
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_grant, opp) for opp in opportunities]
        for future in as_completed(futures):
            _ = future.result()