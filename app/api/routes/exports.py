from io import StringIO
import csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from app.api.deps import get_db, get_role, Role
from app.api.schemas import ExportType
from app.db.models import Opportunity

router = APIRouter(prefix="/api/exports", tags=["exports"])

@router.get("/grants.csv", response_class=PlainTextResponse)
def export_grants_csv(
    type: ExportType = Query(..., description="all|viewed|approved|disapproved|llm_not_relevant|approved_no_email_or_no_url"),
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
   
    stmt = select(Opportunity)

    if type == ExportType.viewed:
        stmt = stmt.where(Opportunity.is_viewed.is_(True))
    elif type == ExportType.approved:
        stmt = stmt.where(
            Opportunity.user_feedback.is_(True),
            Opportunity.user_feedback_info['user_is_relevant'].astext == 'true'
        )
    elif type == ExportType.disapproved:
        stmt = stmt.where(
            Opportunity.user_feedback.is_(True),
            Opportunity.user_feedback_info['user_is_relevant'].astext == 'false'
        )
    elif type == ExportType.llm_not_relevant:
        stmt = stmt.where(Opportunity.llm_info['is_relevant'].astext == 'false')
    elif type == ExportType.approved_no_email_or_no_url:
        stmt = stmt.where(
            Opportunity.user_feedback.is_(True),
            Opportunity.user_feedback_info['user_is_relevant'].astext == 'true',
            or_(
                    Opportunity.email.is_(None),
                    func.length(func.trim(Opportunity.email)) == 0,
                    Opportunity.email == 'Not Available',
                    func.length(func.trim(Opportunity.url)) == 0,
                    Opportunity.url == 'Not Available'
                )
        )

    stmt = stmt.order_by(Opportunity.scraped_at.desc())

    rows = db.execute(stmt).scalars().all()

    buf = StringIO()
    writer = csv.writer(buf)
    header = [
        "id","title","url","source","scraped_at",
        "is_relevant","grant_amount","deadline","tags",
        "user_feedback","user_feedback_info","email"
    ]
    writer.writerow(header)
    for o in rows:
        writer.writerow([
            o.id,
            o.title or "",
            o.url or "",
            o.source or "",
            o.scraped_at.isoformat() if o.scraped_at else "",
            "" if o.is_relevant is None else str(o.is_relevant).lower(),
            o.grant_amount or "",
            o.deadline or "",
            o.tags or "",
            "" if o.user_feedback is None else str(o.user_feedback).lower(),
            (str(o.user_feedback_info) if o.user_feedback_info else ""),
            o.email or "",
        ])

    content = buf.getvalue()
    filename = f"grants_{type.value}.csv"
    return PlainTextResponse(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
