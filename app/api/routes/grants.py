from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import BigInteger, case, cast, or_, select, func , Text, Numeric
from app.api.deps import get_db, get_role, Role
from app.api.schemas import GrantDetail, ListResponse, FeedbackPayload, FeedbackDryRun
from app.db.models import Opportunity
from app.feedback.save_feedback import save_feedback

router = APIRouter(prefix="/api/grants", tags=["grants"])

def _to_detail(o: Opportunity) -> GrantDetail:
    return GrantDetail(
        id=o.id,
        unique_key=o.unique_key,
        title=o.title,
        url=o.url,
        description=o.description,
        grant_amount=o.grant_amount,
        tags=o.tags,
        deadline=o.deadline,
        email=o.email,
        source=o.source,
        scraped_at=o.scraped_at.isoformat() if o.scraped_at else "",
        is_relevant=o.is_relevant,
        is_viewed=bool(o.is_viewed),
        user_feedback=o.user_feedback,
        user_feedback_info=o.user_feedback_info,
        llm_info=o.llm_info,
    )

@router.get("", response_model=ListResponse)
def list_grants(
    q: Optional[str] = Query(None),
    reviewed: Optional[str] = Query(None, pattern="^(reviewed|unreviewed)$"),
    relevance: Optional[str] = Query(None, pattern="^(relevant|not_relevant)$"),
    feedback: Optional[str] = Query(None, pattern="^(has_feedback|no_feedback)$"),
    source: Optional[str] = Query(None),
    min_amount: Optional[int] = Query(
        None, ge=0,
        description="Exclude only rows confidently <= this when a single numeric amount is present; keep ranges/unknown/ambiguous."
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
    
    stmt = select(Opportunity)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Opportunity.title.ilike(like),
            Opportunity.url.ilike(like),
            Opportunity.description.ilike(like),
            Opportunity.source.ilike(like),
        ))

    if reviewed == "reviewed":
        stmt = stmt.where(Opportunity.is_viewed.is_(True))
    elif reviewed == "unreviewed":
        stmt = stmt.where(Opportunity.is_viewed.is_(False))

    if relevance == "relevant":
        stmt = stmt.where(Opportunity.is_relevant.is_(True))
    elif relevance == "not_relevant":
        stmt = stmt.where(Opportunity.is_relevant.is_(False))

    if feedback == "has_feedback":
        stmt = stmt.where(Opportunity.user_feedback.is_(True))
    elif feedback == "no_feedback":
        stmt = stmt.where((Opportunity.user_feedback.is_(False)) | (Opportunity.user_feedback.is_(None)))

    if source:
        like = f"%{source.strip()}%"
        stmt = stmt.where(or_(
            Opportunity.source.ilike(like),
            Opportunity.url.ilike(like),
        ))

    
    
    # Filter by minimum amount if specified - based on concrete numeric values, does not apply to ranges, multiple numbers or unknowns.
    if min_amount is not None:
        range_regex = r'\d\s*[-–]\s*\d'
        multi_numbers_regex = r'(\d[\d,\.]*)\D+(\d[\d,\.]*)' 

        gm = Opportunity.grant_amount
        aw = cast(Opportunity.llm_info['award_amount'], Text)

    
        gm_multi = gm.op('~*')(multi_numbers_regex)
        aw_multi = aw.op('~*')(multi_numbers_regex)

       
        gm_unknown = or_(
            gm.is_(None),
            func.length(func.trim(gm)) == 0,
            func.lower(gm) == 'not available',
            gm.op('~*')(range_regex),
            gm_multi,
        )
        aw_unknown = or_(
            aw.is_(None),
            func.length(func.trim(aw)) == 0,
            func.lower(aw) == 'not available',
            aw.op('~*')(range_regex),
            aw_multi,
        )

        gm_has_k = func.strpos(func.lower(gm), 'k') > 0
        aw_has_k = func.strpos(func.lower(aw), 'k') > 0
        
        gm_digits = func.regexp_replace(func.lower(gm), '[^0-9]', '', 'g')
        aw_digits = func.regexp_replace(func.lower(aw), '[^0-9]', '', 'g')


        gm_value = case(
            (gm.op('~*')(range_regex), None),
            (gm.op('~*')(multi_numbers_regex), None),
            (func.length(gm_digits) > 0,
                case(
                    (gm_has_k, cast(gm_digits, Numeric) * 1000),
                    else_=cast(gm_digits, Numeric),
                )
            ),
            else_=None,
        )

        aw_value = case(
            (aw.op('~*')(range_regex), None),
            (aw.op('~*')(multi_numbers_regex), None),
            (func.length(aw_digits) > 0,
                case(
                    (aw_has_k, cast(aw_digits, Numeric) * 1000),
                    else_=cast(aw_digits, Numeric),
                )
            ),
            else_=None,
        )

        stmt = stmt.where(
            or_(
                gm_value > min_amount,
                aw_value > min_amount,
                gm_unknown,
                aw_unknown,
            )
        )

    
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    stmt_paged = stmt.order_by(Opportunity.scraped_at.desc()) \
                     .offset((page - 1) * per_page) \
                     .limit(per_page)

    rows = db.execute(stmt_paged).scalars().all()

    return ListResponse(items=[_to_detail(o) for o in rows], total=total or 0)

@router.get("/{unique_key}", response_model=GrantDetail)
def get_grant(
    unique_key: str,
    mark_viewed: bool = False,
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
   

    stmt = select(Opportunity).where(Opportunity.unique_key == unique_key)
    o = db.execute(stmt).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant with the unique key not found")

    if role == Role.user and mark_viewed and not o.is_viewed:
        o.is_viewed = True
        db.commit()
        db.refresh(o)

    return _to_detail(o)

def _simulate_feedback_changes(o: Opportunity, payload: FeedbackPayload) -> Dict[str, Any]:
    changes: Dict[str, Any] = {}
    changes["user_feedback"] = True

    info = dict(o.user_feedback_info or {})
    if payload.rationale is not None:
        info["rationale"] = payload.rationale
    if payload.corrections:
        prev = dict(info.get("corrections") or {})
        prev.update(payload.corrections)
        info["corrections"] = prev

    llm_rel = None
    try:
        llm_rel = (o.llm_info or {}).get("is_relevant")
    except Exception:
        llm_rel = None

    explicit_relevance: Optional[bool] = None
    if payload.user_is_relevant is not None:
        explicit_relevance = bool(payload.user_is_relevant)
        info["user_is_relevant"] = explicit_relevance
        info["agreed_with_llm"] = None if llm_rel is None else (explicit_relevance == bool(llm_rel))
    elif payload.corrections and "is_relevant" in payload.corrections:
        rv = str(payload.corrections.get("is_relevant")).strip().lower()
        if rv in {"true","t","yes","y","1"}:
            explicit_relevance = True
        elif rv in {"false","f","no","n","0"}:
            explicit_relevance = False
        if explicit_relevance is not None:
            info["user_is_relevant"] = explicit_relevance
            info["agreed_with_llm"] = None if llm_rel is None else (explicit_relevance == bool(llm_rel))

    info["timestamp"] = datetime.now(timezone.utc).isoformat()

    cols_changed: Dict[str, Any] = {}
    if payload.corrections:
        for k in ("url", "grant_amount", "tags", "deadline", "email"):
            if k in payload.corrections:
                new_val = payload.corrections[k]
                old_val = getattr(o, k)
                if new_val is not None and str(new_val).strip() != (str(old_val).strip() if old_val is not None else None):
                    cols_changed[k] = new_val

    if explicit_relevance is not None and explicit_relevance != o.is_relevant:
        changes["is_relevant"] = explicit_relevance

    changes["user_feedback_info"] = info
    if cols_changed:
        changes["columns_changed"] = cols_changed

    return changes

@router.post("/{unique_key}/feedback", response_model=GrantDetail | FeedbackDryRun)
def submit_feedback(
    unique_key: str,    
    payload: FeedbackPayload,
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
    stmt = select(Opportunity).where(Opportunity.unique_key == unique_key)
    o = db.execute(stmt).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")

    if role in (Role.admin, Role.guest):
        diff = _simulate_feedback_changes(o, payload)
        return FeedbackDryRun(dry_run=True, would_change=diff)

    if not o.is_viewed:
        o.is_viewed = True
        db.commit()
        db.refresh(o)

    updated = save_feedback(
        db=db,
        opportunity_unique_key=o.unique_key,
        rationale=payload.rationale,
        corrections=payload.corrections,
        user_is_relevant=payload.user_is_relevant,
    )
    return _to_detail(updated)


@router.get("/counts/unviewed")
def count_unviewed(
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
    total = db.scalar(select(func.count()).select_from(Opportunity)) or 0
    unviewed = db.scalar(
        select(func.count()).where(Opportunity.is_viewed.is_(False))
    ) or 0
    return {"unviewed": unviewed, "total": total}


@router.get("/counts/feedback")
def count_with_feedback(
    db: Session = Depends(get_db),
    role: Role = Depends(get_role),
):
    total = db.scalar(select(func.count()).select_from(Opportunity)) or 0
    with_feedback = db.scalar(
        select(func.count()).where(Opportunity.user_feedback.is_(True))
    ) or 0
    return {"with_feedback": with_feedback, "total": total}

