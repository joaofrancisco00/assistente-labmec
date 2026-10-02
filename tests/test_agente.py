"""
Validação do modo agente (pipeline/agent.py e pipeline/agent_tools.py) — sem
LLM real, sem Chroma, sem g++ (`_compilar_codigo` é dublê).

O agente só compilava a resposta final: TPZElasticity2D(id) + SetElasticity
compila, roda e devolve tensões zeradas, e saía com selo ✅. Agora ferramenta
e resposta final passam pela mesma verificação do pipeline RAG.

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from pipeline import agent
from pipeline.agent_tools import obter_todas_ferramentas
from pipeline.context import PipelineContext

COMPILOU = {"status": "ok", "erros": [], "ignorados": 0}
ERRO_GPP = ["'class TPZElasticity2D' has no member named 'SetFoo'"]

CODIGO_SET_ELASTICITY = (
    "```cpp\n"
    '#include "Elasticity/TPZElasticity2D.h"\n'
    "TPZElasticity2D *mat = new TPZElasticity2D(1);\n"
    "mat->SetElasticity(2.e3, 0.3);\n```\n"
)
CODIGO_CORRETO = (
    "```cpp\n"
    '#include "Elasticity/TPZElasticity2D.h"\n'
    "TPZElasticity2D *mat = new TPZElasticity2D(1, 2.e3, 0.3, 0., 0., 1);\n```\n"
)


class _LLMComTools:
    def bind_tools(self, tools):
        return self


def _ctx():
    return PipelineContext(
        llm=_LLMComTools(), headers_db=None, examples_db=None, wiki_db=None,
        whitelist={"TPZElasticity2D"}, headers_whitelist={"TPZElasticity2D.h"},
        methods_whitelist={"SetElasticity", "SetFoo"},
        class_header_index={}, class_methods_index={}, collisions={},
        renames={}, legacy_classes=set(), system_base="sistema",
    )


def _ferramenta_de_compilacao(ctx):
    return next(t for t in obter_todas_ferramentas(ctx) if t.name == "test_compilation")


class TestFerramentaDeCompilacao(unittest.TestCase):
    def _rodar(self, codigo, compilacao=COMPILOU):
        with patch.object(pipeline, "_compilar_codigo", return_value=compilacao) as compilar, \
             redirect_stdout(io.StringIO()):
            saida = _ferramenta_de_compilacao(_ctx()).invoke({"cpp_code": codigo})
        return saida, compilar

    def test_regra_semantica_volta_para_o_agente(self):
        saida, compilar = self._rodar(CODIGO_SET_ELASTICITY)
        self.assertIn("VALIDATION FAILED", saida)
        self.assertIn("SetElasticity", saida)
        self.assertNotIn("SUCCESS", saida)
        compilar.assert_not_called()

    def test_codigo_sem_cercas_tambem_e_validado(self):
        saida, _ = self._rodar(CODIGO_SET_ELASTICITY.strip("`\ncp"))
        self.assertIn("VALIDATION FAILED", saida)

    def test_erro_do_compilador_volta_para_o_agente(self):
        saida, _ = self._rodar(CODIGO_CORRETO, {"status": "erros", "erros": ERRO_GPP, "ignorados": 0})
        self.assertIn("VALIDATION FAILED", saida)
        self.assertIn(ERRO_GPP[0], saida)

    def test_codigo_correto_e_sucesso(self):
        saida, compilar = self._rodar(CODIGO_CORRETO)
        self.assertTrue(saida.startswith("SUCCESS"), saida)
        compilar.assert_called_once()

    def test_compilacao_inconclusiva_nao_e_sucesso(self):
        saida, _ = self._rodar(CODIGO_CORRETO, {"status": "indisponivel", "erros": [], "ignorados": 0})
        self.assertNotIn("SUCCESS", saida)
        self.assertNotIn("VALIDATION FAILED", saida)


class _ExecutorFalso:
    saida = ""

    def __init__(self, **kw):
        pass

    def invoke(self, entrada):
        return {"output": self.saida}


class TestRespostaFinalDoAgente(unittest.TestCase):
    def _gerar(self, saida, compilacao=COMPILOU):
        executor = type("Executor", (_ExecutorFalso,), {"saida": saida})
        with patch.object(agent, "_recuperar_contexto", return_value=([], [], [], {"wiki/x.md"})), \
             patch.object(agent, "create_tool_calling_agent", return_value=None), \
             patch.object(agent, "AgentExecutor", executor), \
             patch.object(pipeline, "_compilar_codigo", return_value=compilacao), \
             redirect_stdout(io.StringIO()):
            return agent.gerar_codigo_agente("2D elasticity", _ctx())

    def test_regra_semantica_reprova_o_selo(self):
        r = self._gerar(CODIGO_SET_ELASTICITY)
        self.assertFalse(r["valido"])
        self.assertTrue(r["erros_semanticos"])
        self.assertEqual(r["compilacao"]["status"], "nao_executada")

    def test_classe_inventada_reprova_o_selo(self):
        r = self._gerar("```cpp\nTPZCoisaQueNaoExiste *x = nullptr;\n```\n")
        self.assertFalse(r["valido"])
        self.assertEqual(r["alucinacoes"], ["TPZCoisaQueNaoExiste"])

    def test_erro_do_compilador_reprova_o_selo(self):
        r = self._gerar(CODIGO_CORRETO, {"status": "erros", "erros": ERRO_GPP, "ignorados": 0})
        self.assertFalse(r["valido"])
        self.assertEqual(r["compilacao"]["erros"], ERRO_GPP)

    def test_codigo_correto_ganha_selo_de_compilado(self):
        r = self._gerar(CODIGO_CORRETO)
        self.assertTrue(r["valido"])
        self.assertEqual(r["compilacao"]["status"], "ok")
        self.assertEqual(r["fontes"], {"wiki/x.md"})

    def test_resultado_tem_as_chaves_do_pipeline_rag(self):
        r = self._gerar(CODIGO_CORRETO)
        esperadas = {"resposta", "valido", "alucinacoes", "erros_aridade", "erros_semanticos",
                     "includes", "includes_por_classe", "metodos_suspeitos", "compilacao",
                     "classes_legado", "classes_indisponiveis", "fontes_nao_api",
                     "correcoes_automaticas", "fontes", "tentativas"}
        self.assertEqual(set(r), esperadas)

    def test_saida_em_partes_do_gemini_vira_texto(self):
        r = self._gerar([{"type": "text", "text": CODIGO_CORRETO}])
        self.assertIsInstance(r["resposta"], str)
        self.assertTrue(r["valido"])


class TestModeloLocalUsaORag(unittest.TestCase):
    def test_ollama_cai_para_o_pipeline_rag(self):
        ctx = _ctx()
        ctx.llm = type("ChatOllama", (_LLMComTools,), {})()
        eventos = []
        esperado = {"resposta": "via RAG"}
        with patch.object(agent, "gerar_codigo", return_value=esperado) as rag, \
             patch.object(agent, "AgentExecutor") as executor, \
             redirect_stdout(io.StringIO()):
            r = agent.gerar_codigo_agente("2D elasticity", ctx, historico=[("a", "b")],
                                          on_evento=lambda t, x: eventos.append((t, x)))
        self.assertIs(r, esperado)
        rag.assert_called_once()
        self.assertEqual(rag.call_args.kwargs["historico"], [("a", "b")])
        executor.assert_not_called()
        self.assertTrue(any("Gemini" in x for _, x in eventos))

    def test_gemini_continua_no_agente(self):
        with patch.object(agent, "gerar_codigo") as rag:
            TestRespostaFinalDoAgente()._gerar(CODIGO_CORRETO)
        rag.assert_not_called()


if __name__ == "__main__":
    unittest.main()
