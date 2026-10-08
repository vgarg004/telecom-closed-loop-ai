import os
from pathlib import Path

from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from langchain_qdrant import (
    QdrantVectorStore,
    FastEmbedSparse,
    RetrievalMode,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

KB_DIR = Path("data/knowledge_base")

QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://localhost:6333"
)

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION",
    "telecom_knowledge_base"
)


# ---------------------------------------------------------
# Metadata helper
# ---------------------------------------------------------

def get_document_metadata(pdf_path: Path):

    parent = pdf_path.parent.name.lower()
    filename = pdf_path.name.lower()

    metadata = {
        "source_type": parent,
        "document_name": pdf_path.stem,
        "file_path": str(pdf_path),
    }

    if "132425" in filename or "136214" in filename:
        metadata["technology"] = "LTE"

    elif (
        "128552" in filename
        or "128554" in filename
        or "138215" in filename
    ):
        metadata["technology"] = "5G"

    else:
        metadata["technology"] = "MULTI"

    if "136214" in filename or "138215" in filename:
        metadata["category"] = "radio_measurements"

    elif "132425" in filename or "128552" in filename:
        metadata["category"] = "performance_measurements"

    elif "128554" in filename:
        metadata["category"] = "kpi_definitions"

    elif "assurance" in filename:
        metadata["category"] = "service_assurance"

    elif "troubleshooting" in filename:
        metadata["category"] = "troubleshooting"

    elif "statistics" in filename:
        metadata["category"] = "statistics"

    elif "collection" in filename:
        metadata["category"] = "data_collection"

    else:
        metadata["category"] = "general"

    return metadata


# ---------------------------------------------------------
# Load PDFs
# ---------------------------------------------------------

pdf_files = list(KB_DIR.rglob("*.pdf"))

print(f"PDFs found: {len(pdf_files)}")

documents = []

for pdf_path in pdf_files:

    print(f"Loading: {pdf_path.name}")

    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()

    metadata = get_document_metadata(pdf_path)

    for page in pages:
        page.metadata.update(metadata)

    documents.extend(pages)


print(f"Pages loaded: {len(documents)}")


# ---------------------------------------------------------
# Chunking
# ---------------------------------------------------------

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    separators=[
        "\n\n",
        "\n",
        ". ",
        " ",
        ""
    ]
)

chunks = splitter.split_documents(documents)

for i, chunk in enumerate(chunks):
    chunk.metadata["chunk_id"] = f"chunk_{i:06d}"


print(f"Chunks created: {len(chunks)}")


# ---------------------------------------------------------
# Dense embeddings
# ---------------------------------------------------------

dense_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)


# ---------------------------------------------------------
# Sparse / BM25 embeddings
# ---------------------------------------------------------

sparse_embeddings = FastEmbedSparse(
    model_name="Qdrant/bm25"
)


# ---------------------------------------------------------
# Store in Qdrant
# ---------------------------------------------------------

print("\nStarting Qdrant ingestion...")


vector_store = QdrantVectorStore.from_documents(

    documents=chunks,

    embedding=dense_embeddings,

    sparse_embedding=sparse_embeddings,

    url=QDRANT_URL,

    collection_name=COLLECTION_NAME,

    retrieval_mode=RetrievalMode.HYBRID,

    force_recreate=True,
)


print("\n--------------------------------")
print("INGESTION COMPLETE")
print("--------------------------------")

print("Collection:", COLLECTION_NAME)
print("Documents :", len(pdf_files))
print("Pages     :", len(documents))
print("Chunks    :", len(chunks))

print("--------------------------------")