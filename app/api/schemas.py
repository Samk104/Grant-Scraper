from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel



class GrantDetail(BaseModel):
    id: int
    unique_key: str
    title: str
    url: str
    description: Optional[str] = None
    grant_amount: Optional[str] = None
    tags: Optional[str] = None
    deadline: Optional[str] = None
    email: Optional[str] = None
    source: str
    scraped_at: str
    is_relevant: Optional[bool] = None
    is_viewed: bool
    user_feedback: Optional[bool] = None
    user_feedback_info: Optional[Dict[str, Any]] = None
    llm_info: Optional[Dict[str, Any]] = None

class FeedbackPayload(BaseModel):
    rationale: str
    corrections: Optional[Dict[str, Any]] = None
    user_is_relevant: Optional[bool] = None

class FeedbackDryRun(BaseModel):
    dry_run: bool = True
    would_change: Dict[str, Any]

class ListResponse(BaseModel):
    items: List[GrantDetail]
    total: int

class ExportType(str, Enum):
    all = "all"
    viewed = "viewed"
    approved = "approved"
    disapproved = "disapproved"
    llm_not_relevant = "llm_not_relevant"
    approved_no_email_or_no_url = "approved_no_email_or_no_url"
