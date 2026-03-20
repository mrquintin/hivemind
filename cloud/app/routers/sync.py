from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.agent import AgentDefinition
from app.schemas.agent import AgentOut

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/agents", response_model=list[AgentOut])
def sync_agents(db: Session = Depends(get_db)):
    return db.query(AgentDefinition).filter(AgentDefinition.status == "published").all()


@router.get("/updates")
def sync_updates():
    return {"updates": []}
