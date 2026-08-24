"""
RAG Retriever & Reranker setup.

Provides the function to retrieve relevant context chunks for a given
code snippet, using a two-stage retrieve + rerank pipeline.

The reranker uses BAAI/bge-reranker-v2-m3 (a CrossEncoder from
sentence_transformers). On first use, the model is downloaded automatically.
If the model is unavailable, the pipeline falls back to top-k order with
a warning log so the system keeps working.
"""

from __future__ import annotations

import logging
import os

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

# Lazy-loaded CrossEncoder — only downloaded on first rerank call.
_reranker_model = None


def _get_reranker():
    """Return a loaded CrossEncoder, or None if unavailable."""
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model

    model_name = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    try:
        from sentence_transformers import CrossEncoder
        _reranker_model = CrossEncoder(model_name)
        logger.info("Reranker loaded: %s", model_name)
        return _reranker_model
    except Exception as exc:
        logger.warning(
            "Reranker '%s' could not be loaded (%s). Falling back to top-k order.",
            model_name, exc,
        )
        return None


def get_retriever(persist_dir: str = "./data/chroma_db"):
    """Get the base ChromaDB retriever."""
    if not os.path.exists(persist_dir):
        # Fallback for when DB isn't built yet
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )
    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": 10})


def retrieve_and_rerank(query: str, top_n: int = 3) -> str:
    """Retrieve top-k documents and rerank them to top_n.

    Returns the concatenated context string.
    """
    retriever = get_retriever()
    if not retriever:
        # Fallback static context if DB not initialized (useful for tests)
        return "Context: @if (data$ | async; as data) { ... }"

    docs = retriever.invoke(query)
    doc_texts = [d.page_content for d in docs]

    reranker = _get_reranker()
    if reranker is not None and doc_texts:
        # CrossEncoder expects list of (query, passage) pairs
        pairs = [(query, t) for t in doc_texts]
        scores = reranker.predict(pairs)
        # Sort by score descending and take top_n
        ranked = sorted(zip(scores, doc_texts), key=lambda x: x[0], reverse=True)
        reranked_texts = [text for _, text in ranked[:top_n]]
    else:
        # Graceful fallback: return top_n by raw retrieval order
        reranked_texts = doc_texts[:top_n]

    return "\n\n".join(reranked_texts)

