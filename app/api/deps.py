import os
from enum import Enum
from typing import Generator, Optional
from fastapi import Header, HTTPException, status
from app.db.database import SessionLocal

USER_CODE = os.getenv("USER_CODE", "abc123")
ADMIN_CODE = os.getenv("ADMIN_CODE", "admin123")
GUEST_CODE = os.getenv("GUEST_CODE", "guest123")

class Role(str, Enum):
    user = "user"
    admin = "admin"
    guest = "guest"

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_role(x_access_code: Optional[str] = Header(None, alias="X-Access-Code")) -> Role:
    if x_access_code is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access code",
            headers={"WWW-Authenticate": "Bearer"},  # optional but recommended for 401
        )
    if x_access_code == ADMIN_CODE:
        return Role.admin
    if x_access_code == USER_CODE:
        return Role.user
    if x_access_code == GUEST_CODE:
        return Role.guest
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
