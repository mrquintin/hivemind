import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deps import get_any_authenticated, get_db
from app.models.client import Client
from app.models.client_data import ClientData
from app.schemas.client_data import ClientDataCreate, ClientDataOut

router = APIRouter(prefix="/clients/{client_id}/data", tags=["client-data"])


def _assert_client_scope(client_id: str, user: dict) -> None:
    """Allow operators full access; clients can only access their own client_id."""
    role = str(user.get("role") or "")
    subject = str(user.get("sub") or "")
    if role == "operator":
        return
    if role == "client" and subject == client_id:
        return
    raise HTTPException(status_code=403, detail="Forbidden for this client_id")


def _ensure_client_exists(db: Session, client_id: str) -> None:
    """Create a lightweight client row when data is stored for a new principal."""
    if len(client_id) > 36:
        raise HTTPException(status_code=400, detail="client_id is too long")

    existing = db.query(Client).filter(Client.id == client_id).first()
    if existing:
        return

    license_key = f"auto-{client_id}"
    if db.query(Client).filter(Client.license_key == license_key).first():
        license_key = f"auto-{client_id}-{uuid.uuid4().hex[:8]}"

    db.add(
        Client(
            id=client_id,
            name=client_id,
            license_key=license_key,
        )
    )
    db.flush()


@router.get("", response_model=list[ClientDataOut])
def list_client_data(client_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_any_authenticated)):
    _assert_client_scope(client_id, _user)
    return db.query(ClientData).filter(ClientData.client_id == client_id).all()


@router.post("", response_model=ClientDataOut)
def create_client_data(
    client_id: str,
    payload: ClientDataCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_any_authenticated),
):
    _assert_client_scope(client_id, _user)
    _ensure_client_exists(db, client_id)
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
def get_client_data(client_id: str, data_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_any_authenticated)):
    _assert_client_scope(client_id, _user)
    entry = (
        db.query(ClientData)
        .filter(ClientData.client_id == client_id, ClientData.id == data_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Client data not found")
    return entry


@router.delete("/{data_id}")
def delete_client_data(client_id: str, data_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_any_authenticated)):
    _assert_client_scope(client_id, _user)
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
    _user: dict = Depends(get_any_authenticated),
):
    """Upload a file, extract text, and store as a client data entry."""
    from app.rag.extraction import extract_text_from_bytes
    from app.services.storage import store_file

    _assert_client_scope(client_id, _user)
    _ensure_client_exists(db, client_id)

    MAX_UPLOAD_BYTES = 50_000_000  # 50 MB
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    try:
        extracted_text = extract_text_from_bytes(content_type, data)
    except Exception:
        extracted_text = ""

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
