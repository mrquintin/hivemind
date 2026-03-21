import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.text_chunk import TextChunk
from app.rag.chunking import chunk_text
from app.rag.embeddings import embed_texts
from app.rag.extraction import extract_text_from_bytes
from app.rag.vector_store import upsert_embeddings
from app.routers.settings import get_active_api_key
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    TestRetrievalRequest,
    UploadTextRequest,
)
from app.services.document_optimizer import classify_document, optimize_document
from app.services.rag import retrieve_chunks
from app.services.storage import store_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return db.query(KnowledgeBase).all()


@router.post("", response_model=KnowledgeBaseOut)
def create_knowledge_base(payload: KnowledgeBaseCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    kb = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        decision_types=payload.decision_types or [],
        embedding_model=settings.EMBEDDING_MODEL,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_knowledge_base(kb_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/{kb_id}")
def delete_knowledge_base(kb_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    db.delete(kb)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _process_and_embed(
    db: Session,
    kb_id: str,
    document: KnowledgeDocument,
    text_to_embed: str,
) -> int:
    """Chunk text, embed, store in DB + Qdrant.  Returns chunk count."""
    chunks = list(
        chunk_text(
            text_to_embed,
            settings.RAG_CHUNK_MIN_TOKENS,
            settings.RAG_CHUNK_MAX_TOKENS,
            settings.RAG_CHUNK_OVERLAP,
        )
    )

    embeddings = embed_texts([chunk for chunk, _ in chunks]) if chunks else []

    chunk_rows: list[TextChunk] = []
    for idx, (chunk_content, token_count) in enumerate(chunks):
        chunk_rows.append(
            TextChunk(
                document_id=document.id,
                knowledge_base_id=kb_id,
                content=chunk_content,
                token_count=token_count,
                chunk_index=idx,
            )
        )

    db.add_all(chunk_rows)
    db.commit()

    if embeddings:
        ids = [chunk.id for chunk in chunk_rows]
        payloads = [
            {
                "knowledge_base_id": kb_id,
                "document_id": document.id,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunk_rows
        ]
        upsert_embeddings(f"kb_{kb_id}", ids, embeddings, payloads)

    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if kb:
        kb.document_count += 1
        kb.chunk_count += len(chunk_rows)
        kb.total_tokens += sum(chunk.token_count for chunk in chunk_rows)
        db.commit()

    return len(chunk_rows)


# ---------------------------------------------------------------------------
# Upload: Framework document (TXT)
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload")
def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Upload a framework/algorithm TXT file.

    The document text is extracted, optimized for RAG precision via the LLM,
    then chunked and embedded for retrieval.
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    s3_path, _ = store_file(file.filename, data, document_type="framework")
    extracted_text = extract_text_from_bytes(content_type, data)

    # Optimize the document for RAG precision
    api_key = get_active_api_key()
    optimized_text = optimize_document(extracted_text, "framework", api_key)

    document = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=file.filename,
        content_type=content_type,
        s3_path=s3_path,
        extracted_text=extracted_text,
        optimized_text=optimized_text,
        document_type="framework",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Embed the optimized text (falls back to raw if optimization unavailable)
    text_for_rag = optimized_text if optimized_text else extracted_text
    chunk_count = _process_and_embed(db, kb_id, document, text_for_rag)

    return {
        "status": "processed",
        "document_id": document.id,
        "document_type": "framework",
        "chunks": chunk_count,
        "optimized": optimized_text != extracted_text,
    }


# ---------------------------------------------------------------------------
# Upload: Simulation program (.py) + companion description (.txt)
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload-simulation")
def upload_simulation(
    kb_id: str,
    program: UploadFile = File(..., description="The .py simulation program"),
    description: UploadFile = File(..., description="The companion .txt description"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Upload a simulation program (.py) paired with its companion description (.txt).

    The .py file is stored for execution.  The companion .txt describing how to
    use the simulation, its inputs/outputs, and interpretation is optimized and
    embedded into the knowledge base for RAG retrieval.
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Validate file types
    prog_name = program.filename or "simulation.py"
    desc_name = description.filename or "description.txt"

    if not prog_name.endswith(".py"):
        raise HTTPException(status_code=400, detail="Program file must be a .py file")
    accepted_desc = (".txt", ".pdf", ".docx", ".doc", ".html")
    if not any(desc_name.lower().endswith(ext) for ext in accepted_desc):
        raise HTTPException(
            status_code=400,
            detail=f"Description file must be one of: {', '.join(accepted_desc)}",
        )

    # Store the .py program file
    prog_data = program.file.read()
    prog_path, _ = store_file(prog_name, prog_data, document_type="simulation_program")

    prog_doc = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=prog_name,
        content_type="text/x-python",
        s3_path=prog_path,
        extracted_text=prog_data.decode("utf-8", errors="replace"),
        document_type="simulation_program",
    )
    db.add(prog_doc)
    db.commit()
    db.refresh(prog_doc)

    # Store and process the companion description
    desc_data = description.file.read()
    desc_content_type = description.content_type or "application/octet-stream"
    desc_path, _ = store_file(desc_name, desc_data, document_type="simulation_description")
    desc_text = extract_text_from_bytes(desc_content_type, desc_data)

    # Optimize the description for RAG precision
    api_key = get_active_api_key()
    optimized_desc = optimize_document(desc_text, "simulation_description", api_key)

    desc_doc = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=desc_name,
        content_type=desc_content_type,
        s3_path=desc_path,
        extracted_text=desc_text,
        optimized_text=optimized_desc,
        document_type="simulation_description",
        companion_document_id=prog_doc.id,
    )
    db.add(desc_doc)
    db.commit()
    db.refresh(desc_doc)

    # Embed the optimized description into the knowledge base
    text_for_rag = optimized_desc if optimized_desc else desc_text
    chunk_count = _process_and_embed(db, kb_id, desc_doc, text_for_rag)

    return {
        "status": "processed",
        "program_document_id": prog_doc.id,
        "description_document_id": desc_doc.id,
        "document_type": "simulation",
        "chunks": chunk_count,
        "optimized": optimized_desc != desc_text,
    }


# ---------------------------------------------------------------------------
# Upload: Practicality network document (TXT)
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload-practicality")
def upload_practicality_document(
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Upload a practicality network constraint/scoring TXT file.

    Practicality documents describe real-world constraints, scoring criteria,
    risk frameworks, and feasibility benchmarks used by the practicality
    network agents to evaluate theory-generated recommendations.
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    s3_path, _ = store_file(file.filename, data, document_type="practicality")
    extracted_text = extract_text_from_bytes(content_type, data)

    api_key = get_active_api_key()
    optimized_text = optimize_document(extracted_text, "practicality", api_key)

    document = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=file.filename,
        content_type=content_type,
        s3_path=s3_path,
        extracted_text=extracted_text,
        optimized_text=optimized_text,
        document_type="practicality",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    text_for_rag = optimized_text if optimized_text else extracted_text
    chunk_count = _process_and_embed(db, kb_id, document, text_for_rag)

    return {
        "status": "processed",
        "document_id": document.id,
        "document_type": "practicality",
        "chunks": chunk_count,
        "optimized": optimized_text != extracted_text,
    }


# ---------------------------------------------------------------------------
# Upload: Smart auto-classify (AI determines framework vs practicality)
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload-smart")
def upload_smart(
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Smart upload: AI classifies document as framework or practicality,
    then extracts, optimizes, and embeds accordingly.
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    extracted_text = extract_text_from_bytes(content_type, data)

    # AI classification
    api_key = get_active_api_key()
    doc_type = classify_document(extracted_text, api_key)

    # Store in the appropriate folder
    s3_path, _ = store_file(file.filename, data, document_type=doc_type)

    # Optimize with type-specific prompt
    optimized_text = optimize_document(extracted_text, doc_type, api_key)

    document = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=file.filename,
        content_type=content_type,
        s3_path=s3_path,
        extracted_text=extracted_text,
        optimized_text=optimized_text,
        document_type=doc_type,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    text_for_rag = optimized_text if optimized_text else extracted_text
    chunk_count = _process_and_embed(db, kb_id, document, text_for_rag)

    return {
        "status": "processed",
        "document_id": document.id,
        "document_type": doc_type,
        "classified_as": doc_type,
        "chunks": chunk_count,
        "optimized": optimized_text != extracted_text,
    }


# ---------------------------------------------------------------------------
# Upload: Paste text directly (no file upload)
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload-text")
def upload_text(
    kb_id: str,
    payload: UploadTextRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Create a knowledge document from pasted text (no file upload required).

    The text is optimized for RAG precision, chunked, and embedded.
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not payload.content or len(payload.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Content is too short")

    filename = f"{payload.title.strip() or 'Untitled'}.txt"

    # Store the raw text as a file
    raw_bytes = payload.content.encode("utf-8")
    s3_path, _ = store_file(filename, raw_bytes, document_type="framework")

    # Optimize for RAG
    api_key = get_active_api_key()
    optimized_text = optimize_document(payload.content, "framework", api_key)

    document = KnowledgeDocument(
        knowledge_base_id=kb_id,
        filename=filename,
        content_type="text/plain",
        s3_path=s3_path,
        extracted_text=payload.content,
        optimized_text=optimized_text,
        document_type="framework",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    text_for_rag = optimized_text if optimized_text else payload.content
    chunk_count = _process_and_embed(db, kb_id, document, text_for_rag)

    return {
        "status": "processed",
        "document_id": document.id,
        "document_type": "framework",
        "chunks": chunk_count,
        "optimized": optimized_text != payload.content,
    }


# ---------------------------------------------------------------------------
# Retrieval testing
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/test-retrieval")
def test_retrieval(kb_id: str, payload: TestRetrievalRequest, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    chunks = retrieve_chunks(db, payload.query, [kb_id])
    return {"results": chunks}


# ---------------------------------------------------------------------------
# Density bounds
# ---------------------------------------------------------------------------

@router.get("/density-bounds", response_model=dict[str, Any])
def get_density_bounds(
    kb_ids: str = Query(..., description="Comma-separated knowledge base IDs"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Return min and max token counts for density slider bounds."""
    id_list = [k.strip() for k in kb_ids.split(",") if k.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="kb_ids is required")

    rows = (
        db.query(
            TextChunk.document_id,
            func.sum(TextChunk.token_count).label("doc_tokens"),
        )
        .filter(TextChunk.knowledge_base_id.in_(id_list))
        .group_by(TextChunk.document_id)
        .all()
    )

    if not rows:
        return {"min_doc_tokens": 0, "sum_all_doc_tokens": 0}

    per_doc = [int(r.doc_tokens) for r in rows]
    return {
        "min_doc_tokens": min(per_doc),
        "sum_all_doc_tokens": sum(per_doc),
    }
