"""
Cache de respostas do LLM (pipeline/llm_cache.py) — sem LLM real, sem Chroma.

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_core.globals import set_llm_cache
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import pipeline
from pipeline import llm_cache
from test_pipeline import _DBFalso, _LLMFalso


class _CacheIsolado(unittest.TestCase):
    """Cada teste usa um sqlite próprio e devolve o módulo ao estado desligado."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self._tmp.name) / "sub" / "cache.sqlite"
        self._conexoes = []
        llm_cache._cache = None

    def tearDown(self):
        for con in self._conexoes:
            con.close()
        llm_cache._cache = None
        set_llm_cache(None)
        self._tmp.cleanup()

    def _ativar(self):
        with patch.object(llm_cache, "LLM_CACHE_FILE", self.caminho), \
             patch.dict(os.environ, {"LLM_CACHE": "1"}), \
             redirect_stdout(io.StringIO()):
            cache = llm_cache.ativar_se_configurado()
        self._conexoes.append(cache._con)
        return cache


class TestAtivacao(_CacheIsolado):
    def test_desligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llm_cache.ativar_se_configurado())
        llm = _LLMFalso("x")
        llm_cache.salvar(llm, "p", "resposta")
        self.assertIsNone(llm_cache.buscar(llm, "p"))

    def test_ligado_com_variavel_de_ambiente(self):
        self.assertIsNotNone(self._ativar())
        self.assertTrue(self.caminho.exists())


class TestIdaEVolta(_CacheIsolado):
    def test_mesmo_prompt_e_modelo_acerta(self):
        self._ativar()
        llm = _LLMFalso("x")
        llm_cache.salvar(llm, "prompt", "resposta guardada")
        self.assertEqual(llm_cache.buscar(llm, "prompt"), "resposta guardada")

    def test_prompt_diferente_erra(self):
        self._ativar()
        llm = _LLMFalso("x")
        llm_cache.salvar(llm, "prompt", "r")
        self.assertIsNone(llm_cache.buscar(llm, "prompt com erro do compilador"))

    def test_modelo_diferente_erra(self):
        # Fallback Gemini → Ollama no meio do benchmark não pode reaproveitar
        # a resposta de outro modelo
        self._ativar()
        a, b = _LLMFalso("x"), _LLMFalso("x")
        a.model, b.model = "gemini-3.6-flash", "qwen2.5-coder:7b"
        llm_cache.salvar(a, "prompt", "do gemini")
        self.assertIsNone(llm_cache.buscar(b, "prompt"))

    def test_persiste_entre_execucoes(self):
        self._ativar()
        llm = _LLMFalso("x")
        llm_cache.salvar(llm, "prompt", "r")
        llm_cache._cache = None
        self._ativar()
        self.assertEqual(llm_cache.buscar(llm, "prompt"), "r")


class TestCaminhoDoAgente(_CacheIsolado):
    def test_invoke_de_chat_model_usa_o_cache_global(self):
        # O agente chama invoke() via AgentExecutor: coberto pelo cache global
        self._ativar()
        llm = FakeListChatModel(responses=["primeira", "segunda"])
        self.assertEqual(llm.invoke("oi").content, "primeira")
        self.assertEqual(llm.invoke("oi").content, "primeira")


class TestCaminhoDoRAG(_CacheIsolado):
    RESPOSTA = "Explicação sem código."

    def _gerar(self, llm):
        db = _DBFalso()
        with redirect_stdout(io.StringIO()), \
             patch.object(pipeline, "validar_semantica", return_value=[]):
            return pipeline.gerar_codigo(
                "o que é uma malha?",
                llm=llm, headers_db=db, examples_db=db,
                whitelist=set(), headers_whitelist=set(), system_base="sistema",
            )

    def test_segunda_chamada_nao_chega_ao_llm(self):
        # stream() não consulta o cache do LangChain — gerar_codigo consulta
        self._ativar()
        primeiro = _LLMFalso(self.RESPOSTA)
        r1 = self._gerar(primeiro)
        segundo = _LLMFalso("OUTRA resposta")
        r2 = self._gerar(segundo)
        self.assertEqual(len(primeiro.prompts), 1)
        self.assertEqual(segundo.prompts, [])
        self.assertEqual(r2["resposta"], r1["resposta"])

    def test_sem_cache_o_llm_e_chamado_sempre(self):
        with patch.dict(os.environ, {}, clear=True):
            llm_cache.ativar_se_configurado()
        self._gerar(_LLMFalso(self.RESPOSTA))
        segundo = _LLMFalso("OUTRA resposta")
        r = self._gerar(segundo)
        self.assertEqual(len(segundo.prompts), 1)
        self.assertEqual(r["resposta"], "OUTRA resposta")


if __name__ == "__main__":
    unittest.main()
