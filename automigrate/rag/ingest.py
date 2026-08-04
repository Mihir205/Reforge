"""
RAG Ingestion Pipeline.

Loads migration guides, chunks them, embeds them, and stores them in ChromaDB.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma


def ingest_docs(data_dir: str = "automigrate/rag/data", persist_dir: str = "./data/chroma_db"):
    """Load documents, split into chunks, and store in vector database."""
    path = Path(data_dir)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        
    loader = DirectoryLoader(
        str(path),
        glob="**/*.md",
        loader_cls=TextLoader,
        show_progress=True,
    )
    docs = loader.load()
    
    if not docs:
        print("No documents found to ingest.")
        return
        
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n## ", "\n\n", "\n", " ", ""],
    )
    splits = text_splitter.split_documents(docs)
    
    # Using local embeddings (sentence-transformers)
    embeddings = HuggingFaceEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )
    
    # Store in ChromaDB
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=persist_dir,
    )
    print(f"Ingested {len(splits)} chunks into {persist_dir}")
    
if __name__ == "__main__":
    ingest_docs()
