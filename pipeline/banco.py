from __future__ import annotations

import numpy as np
from langchain_chroma.vectorstores import maximal_marginal_relevance
from langchain_core.documents import Document


class BancoExato:
    def __init__(self, documentos: list, metadados: list, embeddings: np.ndarray,
                 embeddings_fn, colecao=None):
        self._documentos = documentos
        self._metadados = [m or {} for m in metadados]
        self._embeddings = np.asarray(embeddings, dtype=np.float32)
        self._embedding_function = embeddings_fn
        self._collection = colecao

    @classmethod
    def de_chroma(cls, chroma) -> BancoExato:
        dados = chroma._collection.get(include=["documents", "metadatas", "embeddings"])
        embeddings = dados["embeddings"]
        if embeddings is None or len(embeddings) == 0:
            embeddings = np.zeros((0, 1), dtype=np.float32)
        return cls(dados["documents"], dados["metadatas"], embeddings,
                   chroma._embedding_function, colecao=chroma._collection)

    @classmethod
    def de_dados(cls, documentos, metadados, embeddings, embeddings_fn) -> BancoExato:
        return cls(documentos, metadados, embeddings, embeddings_fn)

    def _candidatos(self, filtro: dict | None) -> np.ndarray:
        if not filtro:
            return np.arange(len(self._documentos))
        return np.array([i for i, m in enumerate(self._metadados)
                         if all(m.get(k) == v for k, v in filtro.items())], dtype=int)

    def _ranquear(self, consulta: np.ndarray, k: int, filtro: dict | None) -> np.ndarray:
        indices = self._candidatos(filtro)
        if len(indices) == 0 or k <= 0:
            return np.array([], dtype=int)
        distancias = np.linalg.norm(self._embeddings[indices] - consulta, axis=1)
        ordem = np.lexsort((indices, np.round(distancias, 6)))
        return indices[ordem[:k]]

    def _documento(self, i: int) -> Document:
        return Document(page_content=self._documentos[i], metadata=dict(self._metadados[i]))

    def _vetor(self, consulta: str) -> np.ndarray:
        return np.asarray(self._embedding_function.embed_query(consulta), dtype=np.float32)

    def similarity_search(self, query: str, k: int = 4, filter: dict = None, **_) -> list:
        return [self._documento(i) for i in self._ranquear(self._vetor(query), k, filter)]

    def max_marginal_relevance_search(self, query: str, k: int = 4, fetch_k: int = 20,
                                      lambda_mult: float = 0.5, filter: dict = None, **_) -> list:
        vetor = self._vetor(query)
        pool = self._ranquear(vetor, fetch_k, filter)
        if len(pool) == 0:
            return []
        escolhidos = maximal_marginal_relevance(
            vetor, list(self._embeddings[pool]), k=min(k, len(pool)), lambda_mult=lambda_mult)
        return [self._documento(pool[j]) for j in escolhidos]
