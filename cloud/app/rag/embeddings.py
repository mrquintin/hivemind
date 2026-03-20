from functools import lru_cache
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    model = _model()
    embeddings = model.encode(list(texts), normalize_embeddings=True)
    if isinstance(embeddings, np.ndarray):
        return embeddings.tolist()
    return [emb.tolist() for emb in embeddings]
