import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import grants as grants_routes
from app.api.routes import exports as exports_routes


from app.db import init_db, get_engine
from sqlalchemy import inspect

app = FastAPI(title="Grant Scraper API", version="1.0.0")

origins = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]
fo = os.getenv("FRONTEND_ORIGIN", "").strip()
if fo:
    origins.append(fo)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.on_event("startup")
def _startup():
    init_if_missing = os.getenv("API_INIT_DB_IF_MISSING", "false").lower() in {"1", "true", "yes"}
    if init_if_missing:
        insp = inspect(get_engine()) 
        if not insp.has_table("opportunities", schema="public"): 
            init_db()

app.include_router(grants_routes.router)
app.include_router(exports_routes.router)

@app.get("/healthz")
def healthz():
    return {"ok": True}
