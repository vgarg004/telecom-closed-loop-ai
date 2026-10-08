from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


KB_DIR = Path("data/knowledge_base")


def get_document_metadata(pdf_path: Path):
    """
    Add useful metadata based on folder and filename.
    """

    parent = pdf_path.parent.name.lower()
    filename = pdf_path.name.lower()

    metadata = {
        "source_type": parent,
        "document_name": pdf_path.stem,
        "file_path": str(pdf_path)
    }

    # ---------------------------
    # Technology classification
    # ---------------------------

    if "132425" in filename or "136214" in filename:
        metadata["technology"] = "LTE"

    elif "128552" in filename or "128554" in filename or "138215" in filename:
        metadata["technology"] = "5G"

    else:
        metadata["technology"] = "MULTI"

    # ---------------------------
    # Document category
    # ---------------------------

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


# ----------------------------------------------------
# Find PDFs
# ----------------------------------------------------

pdf_files = list(KB_DIR.rglob("*.pdf"))

print(f"\nPDF files found: {len(pdf_files)}")


# ----------------------------------------------------
# Load PDFs
# ----------------------------------------------------

documents = []

for pdf_path in pdf_files:

    print(f"Loading: {pdf_path.name}")

    loader = PyPDFLoader(str(pdf_path))

    pages = loader.load()

    custom_metadata = get_document_metadata(pdf_path)

    for page in pages:

        page.metadata.update(custom_metadata)

    documents.extend(pages)


print("\nTotal PDF pages loaded:", len(documents))


# ----------------------------------------------------
# Split documents
# ----------------------------------------------------

text_splitter = RecursiveCharacterTextSplitter(

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

chunks = text_splitter.split_documents(documents)


# ----------------------------------------------------
# Add chunk IDs
# ----------------------------------------------------

for index, chunk in enumerate(chunks):

    chunk.metadata["chunk_id"] = f"chunk_{index:06d}"


print("Total chunks created:", len(chunks))


# ----------------------------------------------------
# Inspect sample chunks
# ----------------------------------------------------

print("\n" + "=" * 80)
print("SAMPLE CHUNKS")
print("=" * 80)

for chunk in chunks[:5]:

    print("\nCHUNK ID:", chunk.metadata.get("chunk_id"))

    print(
        "DOCUMENT:",
        chunk.metadata.get("document_name")
    )

    print(
        "SOURCE TYPE:",
        chunk.metadata.get("source_type")
    )

    print(
        "TECHNOLOGY:",
        chunk.metadata.get("technology")
    )

    print(
        "CATEGORY:",
        chunk.metadata.get("category")
    )

    print(
        "PAGE:",
        chunk.metadata.get("page")
    )

    print("\nTEXT:")
    print(chunk.page_content[:700])

    print("\n" + "-" * 80)


# ----------------------------------------------------
# Final statistics
# ----------------------------------------------------

print("\nDOCUMENT PREPARATION SUMMARY")
print("--------------------------------")

print("PDF files :", len(pdf_files))
print("Pages     :", len(documents))
print("Chunks    :", len(chunks))

print("--------------------------------")