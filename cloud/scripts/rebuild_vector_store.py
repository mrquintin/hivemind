#!/usr/bin/env python3
"""
Rebuild Qdrant collections from TextChunk rows in PostgreSQL.

Use after migrating Postgres to RDS: the new Qdrant (on EC2) starts empty.
This script re-embeds all chunks from the DB and upserts them into Qdrant.

Run from cloud/:
  cd cloud && python scripts/rebuild_vector_store.py

Requires DATABASE_URL and VECTOR_DB_URL (from .env or environment).
"""
from __future__ import annotations

import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

# Load config before importing app modules that use it
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_env = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env)

from app.config import settings
from app.models.text_chunk import TextChunk
from app.rag.embeddings import embed_texts
from app.rag.vector_store import ensure_collection, upsert_embeddings

BATCH_SIZE = 64


def main() -> None:
    db_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    vec_url = os.environ.get("VECTOR_DB_URL") or settings.VECTOR_DB_URL
    if not db_url:
        print("ERROR: DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)
    if not vec_url:
        print("ERROR: VECTOR_DB_URL is required", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    try:
        chunks = db.query(TextChunk).order_by(TextChunk.knowledge_base_id, TextChunk.chunk_index).all()
    finally:
        db.close()

    if not chunks:
        print("No text chunks found in the database. Nothing to rebuild.")
        return

    kb_ids = sorted({c.knowledge_base_id for c in chunks})
    print(f"Found {len(chunks)} chunks across {len(kb_ids)} knowledge base(s).")

    for kb_id in kb_ids:
        kb_chunks = [c for c in chunks if c.knowledge_base_id == kb_id]
        collection = f"kb_{kb_id}"
        print(f"  Rebuilding {collection} ({len(kb_chunks)} chunks) ...")

        for i in range(0, len(kb_chunks), BATCH_SIZE):
            batch = kb_chunks[i : i + BATCH_SIZE]
            contents = [c.content for c in batch]
            embeddings = embed_texts(contents)
            ids = [c.id for c in batch]
            payloads = [
                {
                    "knowledge_base_id": kb_id,
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                }
                for c in batch
            ]
            ensure_collection(collection, vector_size=len(embeddings[0]))
            upsert_embeddings(collection, ids, embeddings, payloads)

        print(f"  Done: {collection}")

    print("Rebuild complete.")


if __name__ == "__main__":
    main()
