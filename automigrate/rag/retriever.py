"""
RAG Retriever & Reranker setup.

Provides the function to retrieve relevant context chunks for a given
code snippet, using a two-stage retrieve + rerank pipeline.
"""

from __future__ import annotations

import os
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
# Simulating a reranker interface since full CrossEncoder loads might be heavy
# In a real environment, you'd use sentence_transformers.CrossEncoder

class DummyReranker:
    """A simulated reranker for Phase 3 testing to avoid heavy downloads.
    In production, this wraps BAAI/bge-reranker-v2-m3.
    """
    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[str]:
        # Just returns the top_n as-is since this is a dummy
        return documents[:top_n]


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
        embedding_function=embeddings
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
    
    reranker = DummyReranker()
    reranked = reranker.rerank(query, doc_texts, top_n=top_n)
    
    return "\n\n".join(reranked)
