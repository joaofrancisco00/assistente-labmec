import re
from pathlib import Path

from .config import (
    K_HEADERS,
    K_EXAMPLES,
    EXAMPLE_POOL_MULT,
    K_WIKI,
    K_WIKI_CONCEITOS,
    RERANKER_MODEL,
)
from .cpp_parser import find_tpz_classes_in_code
from sentence_transformers import CrossEncoder

_reranker_cache = None

def _get_reranker() -> CrossEncoder:
    global _reranker_cache
    if _reranker_cache is None:
        print(f"  [Reranker] Carregando modelo Cross-Encoder ({RERANKER_MODEL})...")
        import logging
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
        _reranker_cache = CrossEncoder(RERANKER_MODEL, max_length=512)
    return _reranker_cache

def _rerank_docs(pergunta: str, docs: list, top_k: int) -> list:
    if not docs:
        return []
    try:
        reranker = _get_reranker()
        pairs = [[pergunta, d.page_content] for d in docs]
        scores = reranker.predict(pairs)
        for i, doc in enumerate(docs):
            doc.metadata["rerank_score"] = float(scores[i])
            
        scored_docs = list(zip(scores, docs))
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored_docs[:top_k]]
    except Exception as e:
        print(f"  ⚠️ Erro no reranking: {e}. Usando ordem original.")
        return docs[:top_k]

_DIRS_LEGADO = ("needrefactor", "PerfTests")
_DIRS_NAO_API = ("UnitTest_PZ", "Publications", "PerfUtil")

_PERGUNTA_EXPLICATIVA_RE = re.compile(
    r'\b(what(\'s| is| are| does| do)|purpose of|explain|describe|how does|how do .+ work|'
    r'difference between|'
    r'o que (é|e|faz|são|sao)|para que serve|explique|explica|como funciona|'
    r'qual (a |é a |e a )?diferen[çc]a)\b', re.IGNORECASE)
_PEDIDO_DE_CODIGO_RE = re.compile(
    r'\b(code|program|write|implement|create|generate|solve|build|'
    r'(complete|full) example|'
    r'c[óo]digo|programa|escreva|implemente|crie|criar|gere|gerar|resolva|resolver|'
    r'monte|montar|exemplo completo)\b', re.IGNORECASE)

def _fora_da_api(source: str) -> str:
    partes = Path(source).parts
    if any(d in partes for d in _DIRS_LEGADO):
        return "legado"
    if any(d in partes for d in _DIRS_NAO_API):
        return "teste/benchmark"
    return ""

def _despriorizar_legado(docs: list) -> list:
    atuais, fora = [], []
    for doc in docs:
        (fora if _fora_da_api(doc.metadata.get("source", "") or "") else atuais).append(doc)
    return atuais + fora

def _pergunta_e_explicativa(pergunta: str) -> bool:
    return (bool(_PERGUNTA_EXPLICATIVA_RE.search(pergunta))
            and not _PEDIDO_DE_CODIGO_RE.search(pergunta))

def _pede_snippet_curto(pergunta: str) -> bool:
    return bool(re.search(r'\bsnippet\b', pergunta, re.IGNORECASE))

def _reservar_vagas_conceitos(docs: list, k: int, reservadas: int) -> list:
    alta = [d for d in docs if d.metadata.get("prioridade") == "alta"]
    media = [d for d in docs if d.metadata.get("prioridade") != "alta"]
    docs_priorizados = alta + media

    if reservadas <= 0:
        return docs_priorizados[:k]

    nao_receitas = [d for d in docs_priorizados if d.metadata.get("tipo") != "doc_fluxo"]
    escolhidos = nao_receitas[:reservadas]
    vistos = {d.page_content for d in escolhidos}
    for doc in docs_priorizados:
        if len(escolhidos) >= k:
            break
        if doc.page_content not in vistos:
            vistos.add(doc.page_content)
            escolhidos.append(doc)
    return escolhidos[:k]

def _dedup_docs(docs: list) -> list:
    vistos, unicos = set(), []
    for doc in docs:
        if doc.page_content not in vistos:
            vistos.add(doc.page_content)
            unicos.append(doc)
    return unicos

def _boost_por_classe(docs: list, classes_citadas: set, metadata_key: str) -> list:
    if not classes_citadas:
        return docs
    boost, resto = [], []
    for doc in docs:
        valor = doc.metadata.get(metadata_key, "") or ""
        partes = {c.strip() for c in valor.split(",") if c.strip()}
        if partes & classes_citadas:
            boost.append(doc)
        else:
            resto.append(doc)
    return boost + resto

def _buscar_declaracoes_por_classe(headers_db, pergunta: str, classes: set, limite: int) -> list:
    docs = []
    for classe in sorted(classes)[:limite]:
        try:
            hits = headers_db.similarity_search(pergunta, k=1, filter={"classe": classe})
        except Exception:
            hits = []
        docs.extend(hits)
    return docs

def _buscar_declaracoes_por_nome(headers_db, nomes: set, limite: int) -> list:
    docs = []
    for nome in sorted(nomes):
        if len(docs) >= limite:
            break
        declaracao = re.compile(
            rf"\b(?:enum(?:\s+class)?|class|struct|namespace|typedef[^;]*|using)\s+{re.escape(nome)}\b")
        try:
            hits = headers_db.similarity_search(nome, k=5)
        except Exception:
            hits = []
        docs.extend(next(([d] for d in hits if declaracao.search(d.page_content)), []))
    return docs

def _recuperar_contexto(pergunta: str, headers_db, examples_db, wiki_db=None,
                        explicativa: bool = None) -> tuple:
    classes_citadas = find_tpz_classes_in_code(pergunta)

    garantidos = _buscar_declaracoes_por_classe(headers_db, pergunta, classes_citadas, limite=K_HEADERS)

    pool_headers = max(K_HEADERS * EXAMPLE_POOL_MULT, K_HEADERS)
    h_pool = headers_db.max_marginal_relevance_search(
        pergunta, k=pool_headers, fetch_k=pool_headers * 2
    )
    h_candidates = _boost_por_classe(_despriorizar_legado(h_pool), classes_citadas, "classe")
    h_reranked = _rerank_docs(pergunta, h_candidates, K_HEADERS)
    h_docs = _dedup_docs(garantidos + h_reranked)[:K_HEADERS]

    pool_examples = max(K_EXAMPLES * EXAMPLE_POOL_MULT, K_EXAMPLES)
    e_pool = examples_db.max_marginal_relevance_search(
        pergunta, k=pool_examples, fetch_k=pool_examples * 2
    )
    e_candidates = _boost_por_classe(_despriorizar_legado(e_pool), classes_citadas, "classes_usadas")
    e_docs = _rerank_docs(pergunta, e_candidates, K_EXAMPLES)

    w_docs = []
    if wiki_db is not None:
        if explicativa is None:
            explicativa = _pergunta_e_explicativa(pergunta)
        w_pool = wiki_db.max_marginal_relevance_search(
            pergunta, k=K_WIKI * EXAMPLE_POOL_MULT, fetch_k=K_WIKI * EXAMPLE_POOL_MULT * 2
        )
        if explicativa or _pede_snippet_curto(pergunta):
            w_pool = [d for d in w_pool if d.metadata.get("tipo") != "doc_fluxo"]
        w_boosted = _boost_por_classe(w_pool, classes_citadas, "classes_usadas")
        w_reranked = _rerank_docs(pergunta, w_boosted, K_WIKI * 3) # Mais folga para reserva de conceitos
        w_docs = _reservar_vagas_conceitos(w_reranked, K_WIKI, K_WIKI_CONCEITOS)

    all_docs = h_docs + e_docs + w_docs
    fontes = {doc.metadata.get("source", "?") for doc in all_docs}

    return h_docs, e_docs, w_docs, fontes
