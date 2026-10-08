import os
import re
from typing import List, Dict

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi


load_dotenv()


class TelecomRetriever:

    def __init__(self):

        self.qdrant_url = os.getenv("QDRANT_URL")
        self.collection_name = os.getenv("QDRANT_COLLECTION")

        # ------------------------------------------------
        # Dense embedding model
        # ------------------------------------------------
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small"
        )

        # ------------------------------------------------
        # Qdrant
        # ------------------------------------------------
        self.client = QdrantClient(
            url=self.qdrant_url
        )

        # ------------------------------------------------
        # CrossEncoder reranker
        # ------------------------------------------------
        self.reranker = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )

        # ------------------------------------------------
        # Build BM25 index
        # ------------------------------------------------
        self.bm25_documents = self._load_documents_for_bm25()

        tokenized_corpus = [
            self._tokenize(doc.page_content)
            for doc in self.bm25_documents
        ]

        self.bm25 = BM25Okapi(
            tokenized_corpus
        )


    # ====================================================
    # TOKENIZATION FOR BM25
    # ====================================================

    def _tokenize(self, text: str) -> List[str]:

        return re.findall(
            r"\b\w[\w\-.]*\b",
            text.lower()
        )


    # ====================================================
    # LOAD ALL QDRANT CHUNKS FOR BM25
    # ====================================================

    def _load_documents_for_bm25(self) -> List[Document]:

        documents = []

        offset = None

        while True:

            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )

            for point in points:

                payload = point.payload or {}

                page_content = payload.get(
                    "page_content",
                    ""
                )

                metadata = payload.get(
                    "metadata",
                    {}
                ).copy()

                if not page_content.strip():
                    continue

                documents.append(
                    Document(
                        page_content=page_content,
                        metadata=metadata
                    )
                )

            if next_offset is None:
                break

            offset = next_offset

        print(
            f"BM25 index loaded with "
            f"{len(documents)} chunks"
        )

        return documents


    # ====================================================
    # NOISE FILTER
    # ====================================================

    def _is_noisy_chunk(
        self,
        text: str
    ) -> bool:

        if not text:
            return True

        text = text.strip()

        # Very short chunk
        if len(text) < 150:
            return True

        # Table of contents
        if text.count(".....") >= 2:
            return True

        # Bad PDF extraction artifacts
        garbage_tokens = re.findall(
            r"/g\d+",
            text
        )

        if len(garbage_tokens) > 20:
            return True

        return False


    # ====================================================
    # DENSE SEARCH
    # ====================================================

    def _dense_search(
        self,
        query: str,
        candidate_k: int
    ) -> List[Document]:

        query_vector = self.embeddings.embed_query(
            query
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=candidate_k
        ).points

        documents = []

        for result in results:

            payload = result.payload or {}

            page_content = payload.get(
                "page_content",
                ""
            )

            metadata = payload.get(
                "metadata",
                {}
            ).copy()

            if self._is_noisy_chunk(
                page_content
            ):
                continue

            metadata["vector_score"] = float(
                result.score
            )

            metadata["retrieval_source"] = "dense"

            documents.append(
                Document(
                    page_content=page_content,
                    metadata=metadata
                )
            )

        return documents


    # ====================================================
    # BM25 SEARCH
    # ====================================================

    def _bm25_search(
        self,
        query: str,
        candidate_k: int
    ) -> List[Document]:

        tokenized_query = self._tokenize(
            query
        )

        scores = self.bm25.get_scores(
            tokenized_query
        )

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:candidate_k]

        documents = []

        for index in ranked_indices:

            original_doc = (
                self.bm25_documents[index]
            )

            if self._is_noisy_chunk(
                original_doc.page_content
            ):
                continue

            metadata = (
                original_doc.metadata.copy()
            )

            metadata["bm25_score"] = float(
                scores[index]
            )

            metadata["retrieval_source"] = "bm25"

            documents.append(
                Document(
                    page_content=original_doc.page_content,
                    metadata=metadata
                )
            )

        return documents


    # ====================================================
    # MERGE DENSE + BM25 RESULTS
    # ====================================================

    def _merge_results(
        self,
        dense_documents: List[Document],
        bm25_documents: List[Document]
    ) -> List[Document]:

        merged: Dict[str, Document] = {}

        all_documents = (
            dense_documents +
            bm25_documents
        )

        for doc in all_documents:

            chunk_id = doc.metadata.get(
                "chunk_id"
            )

            # Fallback if chunk ID is missing
            if not chunk_id:
                chunk_id = doc.page_content[:100]

            if chunk_id not in merged:

                merged[chunk_id] = doc

            else:

                existing = merged[chunk_id]

                # If same chunk was found by both
                # dense and BM25, preserve both scores

                if "vector_score" in doc.metadata:

                    existing.metadata[
                        "vector_score"
                    ] = doc.metadata[
                        "vector_score"
                    ]

                if "bm25_score" in doc.metadata:

                    existing.metadata[
                        "bm25_score"
                    ] = doc.metadata[
                        "bm25_score"
                    ]

                existing.metadata[
                    "retrieval_source"
                ] = "hybrid"

        return list(
            merged.values()
        )


    # ====================================================
    # RERANK
    # ====================================================

    def _rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int
    ) -> List[Document]:

        if not documents:
            return []

        pairs = [
            [query, doc.page_content]
            for doc in documents
        ]

        scores = self.reranker.predict(
            pairs
        )

        for doc, score in zip(
            documents,
            scores
        ):

            doc.metadata[
                "reranker_score"
            ] = float(score)

        documents.sort(
        key=lambda doc: doc.metadata["reranker_score"],
        reverse=True
        )

        filtered_documents = [
        doc
        for doc in documents
        if doc.metadata["reranker_score"] > -3.0
        ]

        return filtered_documents[:top_k]


    # ====================================================
    # PUBLIC RETRIEVE METHOD
    # ====================================================

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 15
    ) -> List[Document]:

        # --------------------------------------------
        # Dense search
        # --------------------------------------------

        dense_documents = self._dense_search(
            query=query,
            candidate_k=candidate_k
        )

        # --------------------------------------------
        # BM25 search
        # --------------------------------------------

        bm25_documents = self._bm25_search(
            query=query,
            candidate_k=candidate_k
        )

        # --------------------------------------------
        # Merge + deduplicate
        # --------------------------------------------

        documents = self._merge_results(
            dense_documents,
            bm25_documents
        )

        # --------------------------------------------
        # Rerank merged candidates
        # --------------------------------------------

        documents = self._rerank(
            query=query,
            documents=documents,
            top_k=top_k
        )

        return documents
