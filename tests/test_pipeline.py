"""
Testes das funções puras de validação/correção do pipeline (sem LLM/Chroma).

Rodar:  python3 -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
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

    def test_include_qualificado_para_material_da_api_nova(self):
        # Descoberto compilando as receitas: headers da API nova de materiais
        # ficam em subpastas (Material/Poisson/...) e o include precisa do
        # prefixo da família — o basename sozinho NÃO compila
        self.assertEqual(pipeline._include_para_header("Material/Poisson/TPZMatPoisson.h"),
                         "Poisson/TPZMatPoisson.h")
        self.assertEqual(pipeline._include_para_header("Material/DarcyFlow/TPZMixedDarcyFlow.h"),
                         "DarcyFlow/TPZMixedDarcyFlow.h")
        # Material raiz e demais diretórios de topo: basename continua certo
        self.assertEqual(pipeline._include_para_header("Material/TPZNullMaterial.h"),
                         "TPZNullMaterial.h")
        self.assertEqual(pipeline._include_para_header("Mesh/pzgmesh.h"), "pzgmesh.h")

    def test_injecao_usa_forma_compilavel(self):
        codigo = 'int main() { TPZMatPoisson<STATE> *m = new TPZMatPoisson<STATE>(1, 2); }\n'
        corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
            codigo,
            {"TPZMatPoisson": "Material/Poisson/TPZMatPoisson.h"},
            {},
            {"TPZMatPoisson.h"},
        )
        self.assertIn('#include "Poisson/TPZMatPoisson.h"', corrigido)
        self.assertNotIn('#include "TPZMatPoisson.h"', corrigido)

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


class TestRenomeacoes(unittest.TestCase):
    def test_renomeacao_conhecida_vence_o_difflib(self):
        # Regressão: difflib empurrou 'TPZMatLaplacian' (Poisson) para
        # 'TPZMatPlaca2' (material de placa) por semelhança de string.
        # Com o mapa curado, a renomeação vai direto para o destino certo.
        codigo = "TPZMatLaplacian *mat = new TPZMatLaplacian(1, 2);"
        whitelist = {"TPZMatPoisson", "TPZMatPlaca2", "TPZMat2dLin"}
        renames = {"TPZMatLaplacian": "TPZMatPoisson"}
        corrigido, correcoes = pipeline._corrigir_classes_automaticamente(
            codigo, whitelist, renames)
        self.assertIn("TPZMatPoisson", corrigido)
        self.assertNotIn("TPZMatLaplacian", corrigido)
        self.assertEqual(correcoes, ["TPZMatLaplacian → TPZMatPoisson [renomeação]"])

    def test_destino_fora_da_whitelist_nao_aplica(self):
        # Trava de segurança: entrada desatualizada no renames.json não pode
        # introduzir uma classe que não existe
        codigo = "TPZMatLaplacian *mat;"
        corrigido, correcoes = pipeline._corrigir_classes_automaticamente(
            codigo, {"TPZGeoMesh"}, {"TPZMatLaplacian": "TPZClasseQueNaoExiste"})
        self.assertIn("TPZMatLaplacian", corrigido)
        self.assertEqual(correcoes, [])

    def test_arquivo_renames_do_projeto_e_valido(self):
        # O renames.json versionado deve carregar e cada entrada deve fazer
        # sentido: a classe antiga foi removida (correção automática) OU só
        # existe no legado (dica no aviso "prefira a API atual"); o destino
        # sempre existe e não é ele próprio do legado.
        renames = pipeline._carregar_renames()
        self.assertIn("TPZMatLaplacian", renames)
        whitelist = set(
            Path("banco_chroma/whitelist.txt").read_text(encoding="utf-8").splitlines())
        legado = set(
            Path("banco_chroma/legacy_classes.txt").read_text(encoding="utf-8").splitlines())
        for antiga, nova in renames.items():
            self.assertTrue(antiga not in whitelist or antiga in legado,
                            f"'{antiga}' existe na API atual — entrada desnecessária")
            self.assertIn(nova, whitelist,
                          f"'{nova}' não existe na whitelist — entrada inválida")
            self.assertNotIn(nova, legado,
                             f"'{nova}' é do legado — destino de rename deve ser da API atual")


class TestDespriorizacaoDeLegado(unittest.TestCase):
    def test_legado_vai_para_o_fim(self):
        from langchain_core.documents import Document
        docs = [
            Document(page_content="a", metadata={"source": "Material/needrefactor/REAL/mixedpoisson.h"}),
            Document(page_content="b", metadata={"source": "Material/Poisson/TPZMatPoisson.h"}),
            Document(page_content="c", metadata={"source": "PerfTests/progs/hybridmesh/pzhybridpoisson.h"}),
            Document(page_content="d", metadata={"source": "Mesh/pzcmesh.h"}),
        ]
        ordenados = pipeline._despriorizar_legado(docs)
        self.assertEqual([d.page_content for d in ordenados], ["b", "d", "a", "c"])


class TestLogDeInteracoes(unittest.TestCase):
    RESULTADO = {
        "resposta": "TPZGeoMesh *g = new TPZGeoMesh();",
        "valido": True,
        "tentativas": 1,
        "correcoes_automaticas": [],
        "alucinacoes": [],
        "includes": {},
        "includes_por_classe": {},
        "metodos_suspeitos": [("TPZGeoMesh", "Foo")],
        "classes_legado": ["TPZMatVelha"],
        "fontes": {"b.h", "a.h"},
    }

    def test_linhas_jsonl_validas_e_acumulativas(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "logs" / "interacoes.jsonl"
            pipeline._registrar_interacao("primeira pergunta", self.RESULTADO, caminho)
            pipeline._registrar_interacao("segunda pergunta", self.RESULTADO, caminho)
            linhas = caminho.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(linhas), 2)
        registro = json.loads(linhas[0])
        self.assertEqual(registro["pergunta"], "primeira pergunta")
        self.assertTrue(registro["valido"])
        self.assertEqual(registro["metodos_suspeitos"], ["TPZGeoMesh::Foo"])
        self.assertEqual(registro["classes_legado"], ["TPZMatVelha"])
        self.assertEqual(registro["fontes"], ["a.h", "b.h"])

    def test_falha_de_log_nao_derruba_o_chat(self):
        # Caminho impossível (arquivo no lugar do diretório) — deve só avisar
        with tempfile.TemporaryDirectory() as tmp:
            bloqueio = Path(tmp) / "logs"
            bloqueio.write_text("sou um arquivo, não um diretório")
            caminho = bloqueio / "interacoes.jsonl"
            pipeline._registrar_interacao("pergunta", self.RESULTADO, caminho)  # não levanta


class TestHistoricoDeConversa(unittest.TestCase):
    def test_vazio_nao_adiciona_nada(self):
        self.assertEqual(pipeline._formatar_historico([]), "")
        self.assertEqual(pipeline._formatar_historico(None), "")

    def test_limita_trocas_e_trunca_respostas(self):
        historico = [(f"pergunta {i}", "x" * 5000) for i in range(5)]
        texto = pipeline._formatar_historico(historico, max_trocas=3, max_chars_resposta=100)
        # só as 3 últimas trocas entram
        self.assertNotIn("pergunta 0", texto)
        self.assertNotIn("pergunta 1", texto)
        self.assertIn("pergunta 2", texto)
        self.assertIn("pergunta 4", texto)
        # respostas longas são truncadas
        self.assertIn("[... resposta truncada ...]", texto)
        self.assertNotIn("x" * 200, texto)

    def test_historico_entra_no_prompt(self):
        prompt = pipeline._montar_prompt(
            "e como refino essa malha?", "CONTEXTO", "sistema", set(), set(),
            historico=[("como crio uma malha?", "Use TPZGeoMeshTools.")],
        )
        self.assertIn("HISTÓRICO DA CONVERSA", prompt)
        self.assertIn("como crio uma malha?", prompt)
        # a tarefa atual continua sendo a pergunta nova
        self.assertIn("Tarefa: e como refino essa malha?", prompt)


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
