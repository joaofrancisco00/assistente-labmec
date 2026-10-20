"""
Classes que vivem em namespace (pzgeom::TPZGeoQuad, pzshape::TPZShapeQuad,
pztopology::TPZQuadrilateral, ...): índice (cpp_parser), correção automática
e validação do uso sem qualificação.

Caso real do benchmark: o modelo escreve `TPZGeoQuad` e o g++ responde
"'TPZGeoQuad' was not declared; did you mean 'pzgeom::TPZGeoQuad'".

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from pipeline.cpp_parser import build_class_namespace_index
from pipeline.correction import _corrigir_namespaces_automaticamente
from pipeline.validation import _validar_namespaces


class TestIndiceDeNamespaces(unittest.TestCase):
    def test_classe_em_namespace_e_registrada(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a.h").write_text(
                "namespace pzgeom {\nclass TPZGeoQuad { public: void Foo(); };\n}\n"
                "class TPZGeoMesh { public: void Bar(); };\n",
                encoding="utf-8")
            (base / "b.h").write_text(
                "namespace pzinternal {\nclass TPZGeoMesh;\n}\n",
                encoding="utf-8")
            indice = build_class_namespace_index(base)
        # TPZGeoMesh tem declarações no global E em pzinternal → ambígua, fora
        self.assertEqual(indice, {"TPZGeoQuad": "pzgeom"})


class TestValidarNamespaces(unittest.TestCase):
    INDICE = {"TPZGeoQuad": "pzgeom"}

    def test_uso_sem_qualificacao_e_flagado(self):
        codigo = "```cpp\nTPZGeoElRefPattern<TPZGeoQuad> ref;\n```\n"
        self.assertEqual(_validar_namespaces(codigo, self.INDICE),
                         {"TPZGeoQuad": "pzgeom"})

    def test_uso_qualificado_passa(self):
        codigo = "```cpp\npzgeom::TPZGeoQuad *q = nullptr;\n```\n"
        self.assertEqual(_validar_namespaces(codigo, self.INDICE), {})

    def test_using_namespace_resolve(self):
        codigo = "```cpp\nusing namespace pzgeom;\nTPZGeoQuad *q = nullptr;\n```\n"
        self.assertEqual(_validar_namespaces(codigo, self.INDICE), {})

    def test_classe_so_em_comentario_nao_conta(self):
        codigo = "```cpp\n// use TPZGeoQuad aqui\nint x = 0;\n```\n"
        self.assertEqual(_validar_namespaces(codigo, self.INDICE), {})

    def test_indice_vazio_nao_flaga(self):
        codigo = "```cpp\nTPZGeoQuad *q = nullptr;\n```\n"
        self.assertEqual(_validar_namespaces(codigo, {}), {})


class TestCorrigirNamespaces(unittest.TestCase):
    INDICE = {"TPZGeoQuad": "pzgeom"}
    RESPOSTA = (
        "A célula padrão é a TPZGeoQuad, veja:\n\n"
        "```cpp\n"
        "TPZGeoElRefPattern<TPZGeoQuad> ref;\n"
        "auto *q = new TPZGeoQuad(1);\n"
        "```\n"
    )

    def test_so_o_bloco_de_codigo_e_qualificado(self):
        corrigido, correcoes = _corrigir_namespaces_automaticamente(
            self.RESPOSTA, self.INDICE)
        self.assertIn("TPZGeoElRefPattern<pzgeom::TPZGeoQuad>", corrigido)
        self.assertIn("new pzgeom::TPZGeoQuad(1)", corrigido)
        # a prosa fica intacta — o nome pelado fora do ``` continua
        self.assertIn("a TPZGeoQuad, veja", corrigido)
        self.assertEqual(correcoes, ["TPZGeoQuad → pzgeom::TPZGeoQuad"])

    def test_codigo_ja_qualificado_nao_muda(self):
        codigo = "```cpp\npzgeom::TPZGeoQuad *q = nullptr;\n```\n"
        corrigido, correcoes = _corrigir_namespaces_automaticamente(
            codigo, self.INDICE)
        self.assertEqual(corrigido, codigo)
        self.assertEqual(correcoes, [])


class TestNamespacesNoVerificarResposta(unittest.TestCase):
    def test_qualificacao_automatica_limpa_o_problema(self):
        resposta = ("Segue o padrão de refinamento:\n\n```cpp\n"
                    "TPZGeoElRefPattern<TPZGeoQuad> ref;\n```\n")
        with redirect_stdout(io.StringIO()), \
             patch.object(pipeline, "validar_semantica", return_value=[]), \
             patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "ok", "erros": [], "ignorados": 0}):
            v = pipeline._verificar_resposta(
                resposta,
                whitelist={"TPZGeoQuad", "TPZGeoElRefPattern"},
                headers_whitelist=set(),
                methods_whitelist={"Print"},
                class_header_index={},
                class_methods_index={},
                collisions={}, renames={}, legacy_classes=set(),
                destinos={"TPZGeoQuad", "TPZGeoElRefPattern"},
                class_namespace_index={"TPZGeoQuad": "pzgeom"},
            )
        self.assertIn("TPZGeoQuad → pzgeom::TPZGeoQuad", v["correcoes_automaticas"])
        self.assertEqual(v["namespaces_faltando"], {})
        self.assertTrue(v["nomes_ok"])
        self.assertIn("pzgeom::TPZGeoQuad", v["resposta"])


if __name__ == "__main__":
    unittest.main()
