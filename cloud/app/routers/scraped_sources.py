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


class ScrapedSourceDetailOut(ScrapedSourceOut):
    scraped_text: str | None = None


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


@router.get("/{source_id}", response_model=ScrapedSourceDetailOut)
def get_source(source_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    source = db.query(ScrapedSource).filter(ScrapedSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Scraped source not found")
    return ScrapedSourceDetailOut(
        id=source.id,
        url_or_query=source.url_or_query,
        source_type=source.source_type,
        status=source.status,
        error_message=source.error_message,
        created_at=source.created_at.isoformat() if source.created_at else "",
        scraped_text=source.scraped_text,
    )


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


@router.delete("/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    source = db.query(ScrapedSource).filter(ScrapedSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Scraped source not found")
    db.delete(source)
    db.commit()
    return {"status": "deleted"}


@router.post("/{source_id}/scrape")
def trigger_scrape(source_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Trigger scrape for a source using the scraping service."""
    from app.services.scraper import scrape_url_cached

    source = db.query(ScrapedSource).filter(ScrapedSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Scraped source not found")

    if source.source_type == "url":
        try:
            result = scrape_url_cached(source.url_or_query)
            source.scraped_text = result.text
            source.status = "completed"
            source.error_message = None
        except ValueError as e:
            source.status = "failed"
            source.error_message = f"Blocked: {e}"
        except Exception as e:
            source.status = "failed"
            source.error_message = str(e)[:500]
    elif source.source_type == "search_query":
        try:
            from app.services.scraper import search_and_scrape

            result = search_and_scrape(source.url_or_query)
            source.scraped_text = result.text
            source.status = "completed"
            source.error_message = None
        except Exception as e:
            source.status = "failed"
            source.error_message = str(e)[:500]
    else:
        source.status = "failed"
        source.error_message = f"Unknown source_type: {source.source_type}"

    db.commit()
    return {"status": source.status, "id": source_id}
