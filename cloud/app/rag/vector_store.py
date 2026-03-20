from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import settings


def _client() -> QdrantClient:
    return QdrantClient(url=settings.VECTOR_DB_URL)


def ensure_collection(collection_name: str, vector_size: int) -> None:
    client = _client()
    collections = {c.name for c in client.get_collections().collections}
    if collection_name in collections:
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upsert_embeddings(
    collection_name: str,
    ids: list[str],
    embeddings: list[list[float]],
    payloads: list[dict],
) -> None:
    ensure_collection(collection_name, vector_size=len(embeddings[0]))
    points = [
        PointStruct(id=ids[idx], vector=embeddings[idx], payload=payloads[idx])
        for idx in range(len(ids))
    ]
    _client().upsert(collection_name=collection_name, points=points)


def query_embeddings(
    collection_name: str,
    embedding: list[float],
    top_k: int,
) -> list[tuple[str, float, dict]]:
    client = _client()
    results = client.search(collection_name=collection_name, query_vector=embedding, limit=top_k)
    return [(str(hit.id), float(hit.score), hit.payload or {}) for hit in results]
