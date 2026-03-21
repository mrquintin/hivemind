from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.client_data import ClientData
from app.schemas.client_data import ClientDataCreate, ClientDataOut

router = APIRouter(prefix="/clients/{client_id}/data", tags=["client-data"])


@router.get("", response_model=list[ClientDataOut])
def list_client_data(client_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return db.query(ClientData).filter(ClientData.client_id == client_id).all()


@router.post("", response_model=ClientDataOut)
def create_client_data(
    client_id: str,
    payload: ClientDataCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
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
def get_client_data(client_id: str, data_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    entry = (
        db.query(ClientData)
        .filter(ClientData.client_id == client_id, ClientData.id == data_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Client data not found")
    return entry


@router.delete("/{data_id}")
def delete_client_data(client_id: str, data_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
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


@router.post("/upload", response_model=ClientDataOut)
def upload_client_data(
    client_id: str,
    file: UploadFile = File(...),
    label: str = Form(""),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Upload a file, extract text, and store as a client data entry."""
    from app.rag.extraction import extract_text_from_bytes
    from app.services.storage import store_file

    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    extracted_text = extract_text_from_bytes(content_type, data)

    file_path, _ = store_file(filename, data, document_type="client_upload")

    effective_label = label.strip() or filename

    entry = ClientData(
        client_id=client_id,
        label=effective_label,
        content=extracted_text,
        metadata_={
            "filename": filename,
            "content_type": content_type,
            "file_path": file_path,
            "byte_size": len(data),
            "source": "file_upload",
        },
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
