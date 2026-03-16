from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.client_data import ClientData
from app.schemas.client_data import ClientDataCreate, ClientDataOut

router = APIRouter(prefix="/clients/{client_id}/data", tags=["client-data"])


@router.get("", response_model=list[ClientDataOut])
def list_client_data(client_id: str, db: Session = Depends(get_db)):
    return db.query(ClientData).filter(ClientData.client_id == client_id).all()


@router.post("", response_model=ClientDataOut)
def create_client_data(
    client_id: str,
    payload: ClientDataCreate,
    db: Session = Depends(get_db),
):
    entry = ClientData(
        client_id=client_id,
        label=payload.label,
        content=payload.content,
        metadata_=payload.metadata,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{data_id}", response_model=ClientDataOut)
def get_client_data(client_id: str, data_id: str, db: Session = Depends(get_db)):
    entry = (
        db.query(ClientData)
        .filter(ClientData.client_id == client_id, ClientData.id == data_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Client data not found")
    return entry


@router.delete("/{data_id}")
def delete_client_data(client_id: str, data_id: str, db: Session = Depends(get_db)):
    entry = (
        db.query(ClientData)
        .filter(ClientData.client_id == client_id, ClientData.id == data_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Client data not found")
    db.delete(entry)
    db.commit()
    return {"status": "deleted"}
