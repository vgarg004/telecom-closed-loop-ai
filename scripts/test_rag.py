from src.rag.rag_pipeline import TelecomRAGPipeline


rag = TelecomRAGPipeline()


query = """
A cell is showing very high PRB utilization.
What could be the possible causes and what should
the operator investigate?
"""


result = rag.ask(
    query=query,
    top_k=5,
    candidate_k=15
)


print("\n" + "=" * 100)
print("QUESTION")
print("=" * 100)

print(result["query"])


answer = result["answer"]


print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

print(answer["summary"])


print("\n" + "=" * 100)
print("OBSERVATIONS")
print("=" * 100)

for i, item in enumerate(
    answer["observations"],
    start=1
):
    print(f"{i}. {item}")


print("\n" + "=" * 100)
print("POSSIBLE CAUSES")
print("=" * 100)

for i, item in enumerate(
    answer["possible_causes"],
    start=1
):
    print(f"{i}. {item}")


print("\n" + "=" * 100)
print("RECOMMENDED INVESTIGATION")
print("=" * 100)

for i, item in enumerate(
    answer["recommended_investigation"],
    start=1
):
    print(f"{i}. {item}")


print("\n" + "=" * 100)
print("SOURCES USED")
print("=" * 100)


for i, source in enumerate(
    result["sources"],
    start=1
):

    print(f"\nSOURCE {i}")

    print(
        "Document:",
        source["document"]
    )

    print(
        "Page:",
        source["page"]
    )

    print(
        "Technology:",
        source["technology"]
    )

    print(
        "Chunk ID:",
        source["chunk_id"]
    )

    print(
        "Vector Score:",
        source["vector_score"]
    )

    print(
        "Reranker Score:",
        source["reranker_score"]
    )