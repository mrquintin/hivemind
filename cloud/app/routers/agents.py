from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.agent import AgentDefinition
from app.schemas.agent import AgentCreate, AgentOut, AgentTestRequest, AgentUpdate
from app.services.agent_execution import execute_agent

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    status: str | None = Query(None, description="Filter by status, e.g. 'published'"),
    _user: dict = Depends(get_current_user),
):
    query = db.query(AgentDefinition)
    if status is not None:
        query = query.filter(AgentDefinition.status == status)
    return query.all()


@router.post("", response_model=AgentOut)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = AgentDefinition(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(agent, key, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"status": "deleted"}


@router.post("/{agent_id}/publish")
def publish_agent(agent_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "published"
    agent.version += 1
    db.commit()
    return {"status": "published", "version": agent.version}


@router.post("/{agent_id}/test")
def test_agent(agent_id: str, payload: AgentTestRequest, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    agent = db.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = execute_agent(db, agent, payload.problem_statement)
    return result
