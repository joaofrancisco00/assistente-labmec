"""
Cache em disco das respostas do LLM — ferramenta de DESENVOLVIMENTO.

Ligado só com `LLM_CACHE=1` no ambiente (desligado no uso normal: para o
aluno, repetir a pergunta deve poder dar outra resposta). Serve para rodar de
novo o benchmark ou o compare_agente_rag.py depois de mexer só em código
determinístico (corretores, validação, selo) sem gastar a cota do Gemini.

A chave é o prompt exato + o modelo: mudar prompt, índice, receitas ou modelo
muda a chave e a chamada vai ao LLM de verdade.

Dois caminhos precisam do cache:
  - `invoke` (agente): coberto pelo cache global do LangChain (set_llm_cache).
  - `stream` (RAG): o langchain-core NÃO consulta o cache em stream(), por
    isso gerar_codigo chama buscar()/salvar() explicitamente.
"""
import os
import sqlite3
import warnings

from langchain_core._api import LangChainBetaWarning
from langchain_core.caches import BaseCache
from langchain_core.globals import set_llm_cache
from langchain_core.load import dumps, loads
from langchain_core.outputs import Generation

from .config import LLM_CACHE_FILE


class _SQLiteCache(BaseCache):
    def __init__(self, caminho):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(caminho), check_same_thread=False)
        with self._con:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS cache ("
                "prompt TEXT, llm TEXT, geracoes TEXT, PRIMARY KEY (prompt, llm))")

    def lookup(self, prompt, llm_string):
        linha = self._con.execute(
            "SELECT geracoes FROM cache WHERE prompt = ? AND llm = ?",
            (prompt, llm_string)).fetchone()
        if not linha:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LangChainBetaWarning)
            return loads(linha[0], allowed_objects="core")

    def update(self, prompt, llm_string, return_val):
        with self._con:
            self._con.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                              (prompt, llm_string, dumps(return_val)))

    def clear(self, **kwargs):
        with self._con:
            self._con.execute("DELETE FROM cache")


_cache = None


def ativar_se_configurado():
    global _cache
    if _cache is None and os.environ.get("LLM_CACHE") == "1":
        _cache = _SQLiteCache(LLM_CACHE_FILE)
        set_llm_cache(_cache)
        print(f"  💾 Cache do LLM ativo ({LLM_CACHE_FILE}) — modo de desenvolvimento")
    return _cache


def _chave_llm(llm) -> str:
    return ":".join(str(getattr(llm, a, "")) for a in ("model", "temperature", "num_ctx")) \
        + f":{type(llm).__name__}"


def buscar(llm, prompt: str):
    if _cache is None:
        return None
    geracoes = _cache.lookup(prompt, _chave_llm(llm))
    return geracoes[0].text if geracoes else None


def salvar(llm, prompt: str, texto: str):
    if _cache is not None and texto:
        _cache.update(prompt, _chave_llm(llm), [Generation(text=texto)])
