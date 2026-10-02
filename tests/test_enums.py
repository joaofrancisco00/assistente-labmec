"""
Valores de enum: índice (cpp_parser), correção automática, validação e
retorno no prompt do retry.

Caso real do benchmark (poisson_3d_hexaedros): o modelo escreveu
MMeshType::EHexa nas 3 tentativas. EHexa existe, mas no enum aninhado
TPZAcademicGeoMesh::MMeshType, não no MMeshType usado por TPZGeoMeshTools.

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
from pipeline.cpp_parser import build_enum_values_index, extract_enum_values
from test_pipeline import _DBFalso, _LLMFalso

RAIZ = Path(__file__).resolve().parent.parent
MMESHTYPE_H = RAIZ / "base_de_dados" / "neopz" / "Pre" / "MMeshType.h"

HEADER = """
enum class MMeshType
{
    EQuadrilateral,/*For 2D meshes consisting of quadrilaterals*/
    ETriangular,/*For 2D meshes where each quadrilateral is split into two triangles*/
    EHexahedral,/*For 3D meshes consisting of hexahedra*/
    ETetrahedral,
    EHexaPyrMixed,
    ENoType
};

enum MElementType { EPoint = 0, EOned = 1, ETriangle = 2, ECube = 7 };

class TPZAcademicGeoMesh {
public:
    enum MMeshType {ENone, EHexa, EPrism };
};
"""

INDICE = {
    "MMeshType": [["EQuadrilateral", "For 2D meshes consisting of quadrilaterals"],
                  ["ETriangular", "For 2D meshes where each quadrilateral is split into two triangles"],
                  ["EHexahedral", "For 3D meshes consisting of hexahedra"],
                  ["ETetrahedral", ""], ["EHexaPyrMixed", ""], ["ENoType", ""]],
    "MElementType": [["EPoint", ""], ["EOned", ""], ["ETriangle", ""], ["ECube", ""]],
    "TPZAcademicGeoMesh::MMeshType": [["ENone", ""], ["EHexa", ""], ["EPrism", ""]],
}


class TestIndiceDeEnums(unittest.TestCase):
    def test_valores_e_comentarios(self):
        enums = extract_enum_values(HEADER)
        self.assertEqual([v for v, _ in enums["MMeshType"]],
                         ["EQuadrilateral", "ETriangular", "EHexahedral", "ETetrahedral",
                          "EHexaPyrMixed", "ENoType"])
        self.assertEqual(dict(enums["MMeshType"])["EHexahedral"],
                         "For 3D meshes consisting of hexahedra")

    def test_inicializadores_nao_viram_valores(self):
        self.assertEqual([v for v, _ in extract_enum_values(HEADER)["MElementType"]],
                         ["EPoint", "EOned", "ETriangle", "ECube"])

    def test_enum_aninhado_fica_qualificado(self):
        enums = extract_enum_values(HEADER)
        self.assertIn("TPZAcademicGeoMesh::MMeshType", enums)
        self.assertNotIn("EHexa", [v for v, _ in enums["MMeshType"]])

    def test_comentario_na_linha_de_cima_vai_para_o_valor_seguinte(self):
        enums = extract_enum_values("enum Cor {\n  /// cor quente\n  EVermelho,\n  EAzul // fria\n};")
        self.assertEqual(enums["Cor"], [("EVermelho", "cor quente"), ("EAzul", "fria")])

    @unittest.skipUnless(MMESHTYPE_H.exists(), "submodule do NeoPZ ausente")
    def test_indice_real_do_neopz(self):
        indice = build_enum_values_index(RAIZ / "base_de_dados")
        self.assertIn("EHexahedral", [v for v, _ in indice["MMeshType"]])
        self.assertIn("EHexa", [v for v, _ in indice["TPZAcademicGeoMesh::MMeshType"]])


class TestCorrecaoDeEnums(unittest.TestCase):
    def _corrigir(self, codigo):
        return pipeline._corrigir_enums_automaticamente(codigo, INDICE)

    def test_prefixo_unico_e_corrigido(self):
        codigo, correcoes = self._corrigir("auto t = MMeshType::ETetra;")
        self.assertEqual(codigo, "auto t = MMeshType::ETetrahedral;")
        self.assertEqual(correcoes, ["MMeshType::ETetra → MMeshType::ETetrahedral"])

    def test_nome_parecido_e_corrigido(self):
        codigo, _ = self._corrigir("auto t = MMeshType::ETriangle;")
        self.assertEqual(codigo, "auto t = MMeshType::ETriangular;")

    def test_prefixo_ambiguo_nao_e_corrigido(self):
        codigo, correcoes = self._corrigir("auto t = MMeshType::EHexa;")
        self.assertEqual(codigo, "auto t = MMeshType::EHexa;")
        self.assertEqual(correcoes, [])

    def test_valor_valido_e_enum_desconhecido_ficam(self):
        codigo = "auto a = MMeshType::EHexahedral; auto b = Outro::EHexa;"
        self.assertEqual(self._corrigir(codigo), (codigo, []))

    def test_enum_aninhado_qualificado_nao_e_mexido(self):
        codigo = "auto t = TPZAcademicGeoMesh::MMeshType::EHexa;"
        self.assertEqual(self._corrigir(codigo), (codigo, []))


class TestValidacaoDeEnums(unittest.TestCase):
    def test_valor_inexistente_aponta_o_enum_onde_ele_existe(self):
        invalidos = pipeline._validar_enums("```cpp\nauto t = MMeshType::EHexa;\n```", INDICE)
        self.assertEqual(list(invalidos), ["MMeshType::EHexa"])
        self.assertEqual(invalidos["MMeshType::EHexa"]["existe_em"], ["TPZAcademicGeoMesh::MMeshType"])
        texto = pipeline._descrever_enum_invalido("MMeshType::EHexa", invalidos["MMeshType::EHexa"])
        self.assertIn("EHexahedral (For 3D meshes consisting of hexahedra)", texto)
        self.assertIn("TPZAcademicGeoMesh::MMeshType::EHexa", texto)

    def test_comentario_e_prosa_fora_do_bloco_nao_contam(self):
        resposta = ("Do not write MMeshType::EHexa.\n\n```cpp\n"
                    "// MMeshType::EHexa is wrong\nauto t = MMeshType::EHexahedral;\n```")
        self.assertEqual(pipeline._validar_enums(resposta, INDICE), {})


class TestEnumNoLoop(unittest.TestCase):
    RESPOSTA = "```cpp\nint main() { auto t = MMeshType::EHexa; return 0; }\n```\n"

    def test_valor_invalido_reprova_sem_compilar_e_volta_com_a_lista(self):
        llm = _LLMFalso(self.RESPOSTA)
        with patch.object(pipeline, "_compilar_codigo") as compilar, \
             patch.object(pipeline, "validar_semantica", return_value=[]), \
             patch.object(pipeline.time, "sleep"), \
             redirect_stdout(io.StringIO()):
            r = pipeline.gerar_codigo("3D mesh", llm=llm, headers_db=_DBFalso(),
                                      examples_db=_DBFalso(), whitelist={"TPZGeoMesh"},
                                      headers_whitelist=set(), system_base="sistema",
                                      enum_values_index=INDICE)
        compilar.assert_not_called()
        self.assertFalse(r["valido"])
        self.assertEqual(list(r["enums_invalidos"]), ["MMeshType::EHexa"])
        self.assertNotIn("INVALID ENUM VALUES", llm.prompts[0])
        self.assertIn("INVALID ENUM VALUES", llm.prompts[1])
        self.assertIn("EHexahedral (For 3D meshes consisting of hexahedra)", llm.prompts[1])

    def test_valor_corrigido_segue_para_a_compilacao(self):
        llm = _LLMFalso(self.RESPOSTA.replace("EHexa", "ETetra"))
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "ok", "erros": [], "ignorados": 0}), \
             patch.object(pipeline, "validar_semantica", return_value=[]), \
             redirect_stdout(io.StringIO()):
            r = pipeline.gerar_codigo("3D mesh", llm=llm, headers_db=_DBFalso(),
                                      examples_db=_DBFalso(), whitelist={"TPZGeoMesh"},
                                      headers_whitelist=set(), system_base="sistema",
                                      enum_values_index=INDICE)
        self.assertTrue(r["valido"])
        self.assertIn("MMeshType::ETetrahedral", r["resposta"])
        self.assertIn("MMeshType::ETetra → MMeshType::ETetrahedral", r["correcoes_automaticas"])


if __name__ == "__main__":
    unittest.main()
