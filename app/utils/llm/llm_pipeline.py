from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.update_opportunity import update_opportunity
from app.db.models import Opportunity
from app.db.database import SessionLocal
from app.feedback.retrieval import retrieve_feedback_examples
from app.utils.llm.llm_client import LLMClient
import logging
from app.utils.rag.config import get_prompt_text, get_retrieval_knobs
from app.utils.rag.keyword_matcher import match_keywords
from app.org_kb.retrieval import retrieve_org_context


logger = logging.getLogger(__name__)
llm_client = LLMClient()


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
        
        mission = get_prompt_text()
        knobs = get_retrieval_knobs()
        feedback_k = int(knobs.get("feedback_k", 3))
        matched_keywords = match_keywords(text, max_terms=4)
        org_context = retrieve_org_context(text) 
        
        with SessionLocal() as db:
            examples = retrieve_feedback_examples(db, text, k=feedback_k)
        
        llm_info = llm_client.analyze_grant(
            grant_text=text,
            mission=mission,
            matched_keywords=matched_keywords,
            feedback_examples=examples,
            org_context=org_context,   
        )
        
        with SessionLocal() as db, db.begin():
            ok = update_opportunity(db, opportunity.unique_key, {
                    "llm_info": llm_info,
                    "is_relevant": llm_info.get("is_relevant"),
                })
            if not ok:
                raise RuntimeError("DB update failed")

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