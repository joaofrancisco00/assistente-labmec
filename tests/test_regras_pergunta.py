"""
Regras semânticas que comparam o código com o PEDIDO (campo `pergunta` em
pipeline/rules/semantic.yaml).

Caso real do benchmark (espaco_hdiv): pedido de espaço H(div), resposta com a
receita da projeção L2 (TPZL2Projection + SetAllCreateFunctionsContinuous).
Compila e é coerente em si mesma — só a comparação com o pedido revela o erro.

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline
from pipeline.semantic_check import validar_semantica
from test_pipeline import _DBFalso, _LLMFalso

PEDIDO_HDIV = ("Write C++ code with NeoPZ that creates a computational mesh with an H(div) "
               "approximation space of order 2 on a 2D quadrilateral geometric mesh.")
CODIGO_CONTINUO = ("```cpp\nauto *cmesh = new TPZCompMesh(gmesh);\ncmesh->SetDefaultOrder(2);\n"
                   "cmesh->SetAllCreateFunctionsContinuous();\n"
                   "auto *mat = new TPZL2Projection<STATE>(1, 2);\n```\n")
CODIGO_HDIV = CODIGO_CONTINUO.replace("SetAllCreateFunctionsContinuous", "SetAllCreateFunctionsHDiv")


def _avisos(codigo, pergunta):
    return validar_semantica(codigo, pergunta)


class TestPedidoHDiv(unittest.TestCase):
    def test_espaco_continuo_para_pedido_hdiv_e_reprovado(self):
        avisos = _avisos(CODIGO_CONTINUO, PEDIDO_HDIV)
        self.assertEqual(len(avisos), 1)
        self.assertIn("H(div)", avisos[0])

    def test_codigo_hdiv_passa(self):
        self.assertEqual(_avisos(CODIGO_HDIV, PEDIDO_HDIV), [])

    def test_variantes_de_escrita_do_pedido(self):
        for pedido in ("Create an HDiv space", "create a hdiv mesh", "use an H-div space"):
            with self.subTest(pedido=pedido):
                self.assertTrue(_avisos(CODIGO_CONTINUO, pedido))

    def test_pergunta_explicativa_nao_dispara(self):
        self.assertEqual(_avisos(CODIGO_CONTINUO, "What is the H(div) space in NeoPZ?"), [])

    def test_sem_pergunta_regras_de_pedido_nao_valem(self):
        self.assertEqual(_avisos(CODIGO_CONTINUO, None), [])


class TestPedido3D(unittest.TestCase):
    PEDIDO = "Write complete C++ code with NeoPZ to solve a 3D Poisson problem."

    def test_dim_2_em_pedido_3d_e_reprovado(self):
        for decl in ("constexpr int dim{2};", "const int dim = 2;"):
            with self.subTest(decl=decl):
                self.assertTrue(_avisos(f"```cpp\n{decl}\n```", self.PEDIDO))

    def test_dim_3_e_dimensao_de_contorno_passam(self):
        codigo = "```cpp\nconstexpr int dim{3};\nconst int dimBC = 2;\n```"
        self.assertEqual(_avisos(codigo, self.PEDIDO), [])

    def test_pedido_2d_nao_dispara(self):
        self.assertEqual(_avisos("```cpp\nconstexpr int dim{2};\n```", "Solve a 2D Poisson problem"), [])


class TestPedidoMisto(unittest.TestCase):
    def test_formulacao_mista_sem_malha_multifisica_e_reprovada(self):
        codigo = "```cpp\nauto *cmesh = new TPZCompMesh(gmesh);\ncmesh->AutoBuild();\n```"
        avisos = _avisos(codigo, "Solve the Poisson problem with a mixed formulation")
        self.assertTrue(any("TPZMultiphysicsCompMesh" in a for a in avisos), avisos)

    def test_pergunta_comparativa_nao_dispara(self):
        codigo = "```cpp\nauto *cmesh = new TPZCompMesh(gmesh);\ncmesh->AutoBuild();\n```"
        for pergunta in ("Qual a diferença entre resolver Darcy em H1 (TPZDarcyFlow) e na "
                         "formulação mista (TPZMixedDarcyFlow)?",
                         "Compare solving Darcy in H1 vs the mixed formulation"):
            with self.subTest(pergunta=pergunta):
                self.assertEqual(_avisos(codigo, pergunta), [])

    def test_condicoes_de_contorno_mistas_nao_sao_formulacao_mista(self):
        codigo = "```cpp\nauto *cmesh = new TPZCompMesh(gmesh);\ncmesh->AutoBuild();\n```"
        self.assertEqual(_avisos(codigo, "Solve Poisson with mixed boundary conditions"), [])


class TestPedidoNoLoop(unittest.TestCase):
    def test_retry_recebe_a_divergencia_com_o_pedido(self):
        llm = _LLMFalso(CODIGO_CONTINUO, CODIGO_HDIV)
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "ok", "erros": [], "ignorados": 0}), \
             patch.object(pipeline.time, "sleep"), \
             redirect_stdout(io.StringIO()):
            r = pipeline.gerar_codigo(PEDIDO_HDIV, llm=llm, headers_db=_DBFalso(),
                                      examples_db=_DBFalso(), whitelist=set(),
                                      headers_whitelist=set(), system_base="sistema")
        self.assertIn("SEMANTIC ERROR", llm.prompts[1])
        self.assertIn("H(div)", llm.prompts[1])
        self.assertTrue(r["valido"])
        self.assertEqual(r["tentativas"], 2)


if __name__ == "__main__":
    unittest.main()
