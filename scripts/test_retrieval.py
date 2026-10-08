from src.rag.retriever import TelecomRetriever


retriever = TelecomRetriever()

query = """
A cell is showing very high PRB utilization.
What could be the possible causes and what should the operator investigate?
"""

documents = retriever.retrieve(
    query=query,
    top_k=5,
    candidate_k=15
)

print("\nQUERY:")
print(query)

print("\nRetrieved documents:", len(documents))


for i, doc in enumerate(documents, start=1):

    print("\n" + "=" * 80)
    print(f"RESULT {i}")
    print("=" * 80)

    print("Technology:", doc.metadata.get("technology"))
    print("Category:", doc.metadata.get("category"))
    print("Document:", doc.metadata.get("document_name"))
    print("Page:", doc.metadata.get("page"))
    print("Chunk ID:", doc.metadata.get("chunk_id"))

    print("Retrieval Source:", doc.metadata.get("retrieval_source"))
    print("Vector Score:", doc.metadata.get("vector_score"))
    print("BM25 Score:", doc.metadata.get("bm25_score"))
    print("Reranker Score:", doc.metadata.get("reranker_score"))

    print("\nCONTENT:")
    print(doc.page_content[:500])