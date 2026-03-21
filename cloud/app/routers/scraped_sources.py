"""Scraped/external data sources (spec: data scraped from the internet). Admin configures URLs or queries; stored text is available for context."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.scraped_source import ScrapedSource

router = APIRouter(prefix="/scraped-sources", tags=["scraped-sources"])


class ScrapedSourceCreate(BaseModel):
    url_or_query: str = Field(..., max_length=2000)
    source_type: str = Field(default="url", pattern="^(url|search_query)$")


class ScrapedSourceOut(BaseModel):
    id: str
    url_or_query: str
    source_type: str
    status: str
    error_message: str | None
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ScrapedSourceOut])
def list_sources(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    sources = db.query(ScrapedSource).order_by(ScrapedSource.created_at.desc()).all()
    return [
        ScrapedSourceOut(
            id=s.id,
            url_or_query=s.url_or_query,
            source_type=s.source_type,
            status=s.status,
            error_message=s.error_message,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in sources
    ]


@router.post("", response_model=ScrapedSourceOut)
def create_source(payload: ScrapedSourceCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    source = ScrapedSource(
        url_or_query=payload.url_or_query,
        source_type=payload.source_type,
        status="pending",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return ScrapedSourceOut(
        id=source.id,
        url_or_query=source.url_or_query,
        source_type=source.source_type,
        status=source.status,
        error_message=source.error_message,
        created_at=source.created_at.isoformat() if source.created_at else "",
    )


@router.post("/{source_id}/scrape")
def trigger_scrape(source_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Trigger scrape for a source. Placeholder: in production would enqueue a background job."""
    source = db.query(ScrapedSource).filter(ScrapedSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Scraped source not found")
    if source.source_type == "url":
        try:
            import urllib.request
            req = urllib.request.Request(source.url_or_query, headers={"User-Agent": "HivemindScraper/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            source.scraped_text = raw[:100_000]
            source.status = "completed"
            source.error_message = None
        except Exception as e:
            source.status = "failed"
            source.error_message = str(e)[:500]
    else:
        source.status = "failed"
        source.error_message = "search_query scrape not implemented"
    db.commit()
    return {"status": source.status, "id": source_id}
