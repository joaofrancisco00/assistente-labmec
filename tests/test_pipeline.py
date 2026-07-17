"""
Testes das funções puras de validação/correção do pipeline (sem LLM/Chroma).

Rodar:  python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline


class TestValidacaoDeIncludes(unittest.TestCase):
    WHITELIST = {"pzgmesh.h", "pzcmesh.h"}

    def test_stdlib_em_angulo_nao_e_alucinacao(self):
        # Regressão: <math.h> era validado contra a whitelist do NeoPZ e
        # marcado como header inexistente, disparando retries à toa
        codigo = '#include <math.h>\n#include <iostream>\n#include "pzgmesh.h"\n'
        self.assertEqual(pipeline._validar_includes(codigo, self.WHITELIST), {})

    def test_header_inventado_entre_aspas_e_flagado(self):
        problemas = pipeline._validar_includes('#include "pzfake.h"\n', self.WHITELIST)
        self.assertIn("pzfake.h", problemas)

    def test_presenca_conta_as_duas_formas(self):
        # Para PRESENÇA (correção automática), <...> e "..." contam ambos;
        # para VALIDAÇÃO, só "..."
        codigo = '#include <pzgmesh.h>\n#include "pzcmesh.h"\n'
        self.assertEqual(pipeline._extrair_includes(codigo),
                         ["pzgmesh.h", "pzcmesh.h"])
        self.assertEqual(pipeline._extrair_includes(codigo, apenas_aspas=True),
                         ["pzcmesh.h"])


class TestCorrecaoAutomatica(unittest.TestCase):
    def test_classe_quase_certa_e_corrigida(self):
        # Regressão: TPZGeomMeshTools (inventado) repetido em 3 tentativas
        # mesmo com a sugestão certa no prompt
        codigo = "TPZGeomMeshTools::CreateGeoMeshOnGrid(2);"
        corrigido, correcoes = pipeline._corrigir_classes_automaticamente(
            codigo, {"TPZGeoMeshTools", "TPZGeoMesh"})
        self.assertIn("TPZGeoMeshTools::CreateGeoMeshOnGrid", corrigido)
        self.assertEqual(correcoes, ["TPZGeomMeshTools → TPZGeoMeshTools"])

    def test_metodo_sem_candidato_bom_nao_e_reescrito(self):
        # Regressão CreateRectMesh→CreateMesh: sem candidato de alta
        # confiança NA PRÓPRIA classe, a chamada fica intacta (continua
        # marcada como suspeita) em vez de ser trocada por engano
        codigo = "TPZGeoMeshTools::CreateRectMesh(2);"
        indice = {"TPZGeoMeshTools": ["CreateGeoMeshOnGrid", "CreateRefPattern"]}
        corrigido, correcoes = pipeline._corrigir_metodos_automaticamente(
            codigo, [("TPZGeoMeshTools", "CreateRectMesh")], indice)
        self.assertEqual(corrigido, codigo)
        self.assertEqual(correcoes, [])

    def test_metodo_quase_certo_e_corrigido(self):
        codigo = "gmesh->Prnt();"
        indice = {"TPZGeoMesh": ["Print", "NNodes"]}
        corrigido, correcoes = pipeline._corrigir_metodos_automaticamente(
            codigo, [("TPZGeoMesh", "Prnt")], indice)
        self.assertIn("gmesh->Print()", corrigido)
        self.assertEqual(correcoes, ["TPZGeoMesh::Prnt → TPZGeoMesh::Print"])

    def test_include_lixo_removido_e_certo_injetado(self):
        codigo = ('#include "pz.h"\n#include <iostream>\n\n'
                  'int main() { TPZGeoMesh *g = new TPZGeoMesh(); }\n')
        corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
            codigo,
            {"TPZGeoMesh": "Mesh/pzgmesh.h"},
            {},
            {"pzgmesh.h"},
        )
        self.assertNotIn('"pz.h"', corrigido)
        self.assertIn('#include "pzgmesh.h"', corrigido)
        self.assertTrue(correcoes)


class TestDeteccaoDeCodigo(unittest.TestCase):
    def test_prosa_nao_e_codigo(self):
        prosa = ("A classe TPZGeoMesh representa a malha geométrica do NeoPZ. "
                 "Ela armazena os nós e elementos da geometria do problema.")
        self.assertFalse(pipeline._resposta_contem_codigo(prosa))

    def test_codigo_e_detectado(self):
        self.assertTrue(pipeline._resposta_contem_codigo("```cpp\nint main() {}\n```"))
        self.assertTrue(pipeline._resposta_contem_codigo(
            "TPZGeoMesh *gmesh = new TPZGeoMesh();"))


if __name__ == "__main__":
    unittest.main()
