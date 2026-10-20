"""
Testes das funções puras de validação/correção do pipeline (sem LLM/Chroma).

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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


class TestValidacaoDeIncludesPorClasse(unittest.TestCase):
    # Regressão do bug achado pela checagem de compilação (05/08/2026):
    # _validar_includes_por_classe comparava presença pelo BASENAME, então
    # "TPZMatPoisson.h" contava como igual a "Poisson/TPZMatPoisson.h" — a
    # forma sem prefixo de família passava validada e não compilava.
    # Atingia 187 das 847 classes do índice (Poisson, DarcyFlow, Elasticity,
    # Plasticity, Projection, ConsLaw, Electromagnetics, needrefactor).
    INDICE = {"TPZMatPoisson": "Material/Poisson/TPZMatPoisson.h",
              "TPZGeoMesh": "Mesh/pzgmesh.h"}

    def test_include_sem_prefixo_de_familia_e_flagado(self):
        codigo = '#include "TPZMatPoisson.h"\nTPZMatPoisson<> *m = nullptr;'
        problemas = pipeline._validar_includes_por_classe(codigo, self.INDICE, {})
        self.assertEqual(problemas, {"TPZMatPoisson": "Poisson/TPZMatPoisson.h"})

    def test_include_com_prefixo_de_familia_passa(self):
        codigo = '#include "Poisson/TPZMatPoisson.h"\nTPZMatPoisson<> *m = nullptr;'
        self.assertEqual(pipeline._validar_includes_por_classe(codigo, self.INDICE, {}), {})

    def test_classe_sem_prefixo_necessario_nao_e_afetada(self):
        # TPZGeoMesh não precisa de prefixo — basename continua a forma certa,
        # não pode virar falso positivo
        codigo = '#include "pzgmesh.h"\nTPZGeoMesh *g = nullptr;'
        self.assertEqual(pipeline._validar_includes_por_classe(codigo, self.INDICE, {}), {})


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
        codigo = '```cpp\nint main() { TPZMatPoisson<STATE> *m = new TPZMatPoisson<STATE>(1, 2); }\n```\n'
        corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
            codigo,
            {"TPZMatPoisson": "Material/Poisson/TPZMatPoisson.h"},
            {},
            {"TPZMatPoisson.h"},
        )
        self.assertIn('#include "Poisson/TPZMatPoisson.h"', corrigido)
        self.assertNotIn('#include "TPZMatPoisson.h"', corrigido)

    def test_injecao_cai_dentro_do_bloco_de_codigo(self):
        # Resposta SEM include nenhum: o header injetado ia para o topo do
        # texto, antes da cerca ```cpp. Ficava visível na prosa e — o que
        # importa — _extrair_blocos_codigo não o via, então o g++ compilava
        # sem include e acusava "não declarado" numa classe que existe
        resposta = ("Segue o material:\n\n```cpp\n"
                    "TPZMatPoisson<STATE> *m = new TPZMatPoisson<STATE>(1, 2);\n"
                    "```\n")
        corrigido, _ = pipeline._corrigir_includes_automaticamente(
            resposta,
            {"TPZMatPoisson": "Material/Poisson/TPZMatPoisson.h"},
            {},
            {"TPZMatPoisson.h"},
        )
        self.assertIn('#include "Poisson/TPZMatPoisson.h"',
                      pipeline._extrair_blocos_codigo(corrigido))
        self.assertNotIn("#include", corrigido.split("```")[0])

    def test_include_sem_prefixo_e_reescrito_no_lugar(self):
        # Regressão do bug de basename (ver TestValidacaoDeIncludesPorClasse):
        # quando o include ERRADO já está presente, a correção precisa
        # REESCREVER a linha, não só injetar uma segunda — duas linhas com o
        # mesmo basename ainda dariam "No such file or directory" na errada
        codigo = ('#include "TPZMatPoisson.h"\n'
                  'TPZMatPoisson<STATE> *m = new TPZMatPoisson<STATE>(1, 2);\n')
        corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
            codigo,
            {"TPZMatPoisson": "Material/Poisson/TPZMatPoisson.h"},
            {},
            {"TPZMatPoisson.h"},
        )
        self.assertEqual(corrigido.count("#include"), 1)
        self.assertIn('#include "Poisson/TPZMatPoisson.h"', corrigido)
        self.assertEqual(correcoes,
                         ['TPZMatPoisson: #include "TPZMatPoisson.h" → "Poisson/TPZMatPoisson.h"'])

    def test_chute_estilo_pz_e_removido(self):
        # Regressão real (capturada pelo eval): ao explicar TPZInt1d o modelo
        # escrevia #include "pzint1d.h" — header inexistente, imitando a
        # convenção pzgmesh.h/pzquad.h. O certo é pzquad.h.
        codigo = '```cpp\n#include "pzint1d.h"\n\nTPZInt1d regra(2, 0);\n```\n'
        corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
            codigo,
            {"TPZInt1d": "Integral/pzquad.h"},
            {},
            {"pzquad.h"},   # whitelist real: pzint1d.h NÃO existe
        )
        self.assertNotIn("pzint1d.h", corrigido)
        self.assertIn('#include "pzquad.h"', corrigido)

    def test_chute_nao_remove_header_que_existe(self):
        # Trava de segurança: se o include "chutado" for um header REAL,
        # ele não pode ser removido
        codigo = '#include "pzgmesh.h"\n\nTPZGeoMesh *g = new TPZGeoMesh();\n'
        corrigido, _ = pipeline._corrigir_includes_automaticamente(
            codigo, {"TPZGeoMesh": "Mesh/pzgmesh.h"}, {}, {"pzgmesh.h"})
        self.assertIn('#include "pzgmesh.h"', corrigido)

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
        self.assertEqual(correcoes, ["TPZMatLaplacian → TPZMatPoisson [rename]"])

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
        # Índice desta branch (banco_chroma_develop/) — não o da main
        if not pipeline.WHITELIST_FILE.exists():
            self.skipTest(f"{pipeline.WHITELIST_FILE} ausente — rode indexer.py")
        whitelist = set(
            pipeline.WHITELIST_FILE.read_text(encoding="utf-8").splitlines())
        legado = set(
            pipeline.LEGACY_CLASSES_FILE.read_text(encoding="utf-8").splitlines())
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

    def test_teste_e_benchmark_tambem_vao_para_o_fim(self):
        # UnitTest_PZ/Publications/PerfUtil compilam e são código vivo, mas o
        # CMake os monta com add_executable() — nunca entram na libpz. Como
        # exemplo de uso ensinariam a montar um teste unitário, não um problema
        # de FEM, e são 852 dos 5984 chunks da coleção de exemplos
        from langchain_core.documents import Document
        docs = [
            Document(page_content="a", metadata={"source": "UnitTest_PZ/TestDeRham/TPZMatDeRhamH1.cpp"}),
            Document(page_content="b", metadata={"source": "Material/Poisson/TPZMatPoisson.h"}),
            Document(page_content="c", metadata={"source": "Publications/hdiv3dpaper201504.h"}),
            Document(page_content="d", metadata={"source": "Mesh/pzcmesh.h"}),
        ]
        ordenados = pipeline._despriorizar_legado(docs)
        self.assertEqual([d.page_content for d in ordenados], ["b", "d", "a", "c"])

    def test_etiqueta_casa_por_componente_do_caminho(self):
        # A versão anterior casava por SUBSTRING: 'PerfUtil' dentro da string
        # marcaria como benchmark um 'Util/PerfUtilTimer.h', que é API real
        self.assertEqual(pipeline._fora_da_api("Util/PerfUtilTimer.h"), "")
        self.assertEqual(pipeline._fora_da_api("PerfUtil/pzcpudetect.h"), "teste/benchmark")
        self.assertEqual(pipeline._fora_da_api("Material/needrefactor/REAL/pzburger.h"), "legado")
        self.assertEqual(pipeline._fora_da_api("Mesh/pzcmesh.h"), "")


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


class MockDB:
    def __init__(self, docs_sim=None, docs_mmr=None):
        self.docs_sim = docs_sim or []
        self.docs_mmr = docs_mmr or []

    def similarity_search(self, query, k=1, filter=None):
        return self.docs_sim

    def max_marginal_relevance_search(self, query, k=4, fetch_k=8):
        return self.docs_mmr


class TestRecuperarContexto(unittest.TestCase):
    def test_fluxo_completo_ordena_corretamente(self):
        from langchain_core.documents import Document
        pergunta = "Como uso a TPZGeoMesh?"
        
        doc_header = Document(page_content="class TPZGeoMesh {};", metadata={"classe": "TPZGeoMesh", "source": "Mesh/pzgmesh.h"})
        doc_header_irrelevante = Document(page_content="class TPZOutra {};", metadata={"classe": "TPZOutra", "source": "Outra.h"})
        headers_db = MockDB(
            docs_sim=[doc_header],
            docs_mmr=[doc_header, doc_header_irrelevante]
        )

        doc_ex_bom = Document(page_content="TPZGeoMesh mesh;", metadata={"classes_usadas": "TPZGeoMesh", "source": "Examples/bom.cpp"})
        doc_ex_legado = Document(page_content="TPZGeoMesh mesh2;", metadata={"classes_usadas": "TPZGeoMesh", "source": "Material/needrefactor/velho.cpp"})
        examples_db = MockDB(docs_mmr=[doc_ex_legado, doc_ex_bom])

        doc_wiki_teoria = Document(page_content="A malha é...", metadata={"tipo": "conceito", "classes_usadas": "TPZGeoMesh", "source": "wiki.md"})
        doc_wiki_fluxo = Document(page_content="Tutorial enorme...", metadata={"tipo": "doc_fluxo", "classes_usadas": "TPZGeoMesh", "source": "tutorial.md"})
        wiki_db = MockDB(docs_mmr=[doc_wiki_fluxo, doc_wiki_teoria])

        with patch("pipeline.retrieval._get_reranker",
                   return_value=_RerankerFalso([10.0] * 10)):
            h_docs, e_docs, w_docs, fontes = pipeline._recuperar_contexto(
                pergunta, headers_db, examples_db, wiki_db, explicativa=True
            )

        # Headers: garante dedup
        self.assertEqual(len(h_docs), 2)
        self.assertEqual(h_docs[0].metadata["classe"], "TPZGeoMesh")
        
        # Exemplos: legado desce pro fim
        self.assertEqual(len(e_docs), 2)
        self.assertEqual(e_docs[0].metadata["source"], "Examples/bom.cpp")
        self.assertEqual(e_docs[1].metadata["source"], "Material/needrefactor/velho.cpp")

        # Wiki: doc_fluxo é banido na pergunta explicativa
        self.assertEqual(len(w_docs), 1)
        self.assertEqual(w_docs[0].metadata["tipo"], "conceito")


class _RerankerFalso:
    """Devolve scores fixos na ordem dos pares recebidos — o que interessa é
    o corte por min_score, não o modelo."""
    def __init__(self, scores):
        self.scores = scores

    def predict(self, pairs):
        return self.scores


class TestRerankMinScore(unittest.TestCase):
    def _doc(self, nome, meta=None):
        from langchain_core.documents import Document
        m = {"source": f"{nome}.h"}
        m.update(meta or {})
        return Document(page_content=nome, metadata=m)

    def test_score_abaixo_do_minimo_e_descartado(self):
        docs = [self._doc("a"), self._doc("b"), self._doc("c")]
        with patch("pipeline.retrieval._get_reranker",
                   return_value=_RerankerFalso([5.0, -3.0, 2.0])):
            out = pipeline.retrieval._rerank_docs("pergunta", docs, top_k=3, min_score=-2.0)
        self.assertEqual([d.page_content for d in out], ["a", "c"])
        self.assertEqual(out[0].metadata["rerank_score"], 5.0)

    def test_sem_min_score_ordena_e_corta_no_top_k(self):
        docs = [self._doc("a"), self._doc("b"), self._doc("c")]
        with patch("pipeline.retrieval._get_reranker",
                   return_value=_RerankerFalso([5.0, -3.0, 2.0])):
            out = pipeline.retrieval._rerank_docs("pergunta", docs, top_k=2)
        self.assertEqual([d.page_content for d in out], ["a", "c"])

    def test_garantido_sobrevive_sem_passar_pelo_reranker(self):
        # garantidos entram via filter={"classe": ...} e nunca são reranqueados:
        # mesmo com o MMR devolvendo só lixo de score baixo, eles ficam
        garantido = self._doc("class TPZGeoMesh {};", {"classe": "TPZGeoMesh"})
        ruido = self._doc("header irrelevante")
        headers_db = MockDB(docs_sim=[garantido], docs_mmr=[ruido])
        vazio = MockDB()
        with patch("pipeline.retrieval._get_reranker",
                   return_value=_RerankerFalso([-9.0])):
            h_docs, e_docs, w_docs, _ = pipeline._recuperar_contexto(
                "TPZGeoMesh malha", headers_db, vazio, vazio)
        self.assertIn(garantido, h_docs)
        self.assertNotIn(ruido, h_docs)


class TestReservaDeVagasNaWiki(unittest.TestCase):
    def _doc(self, nome, tipo):
        from langchain_core.documents import Document
        return Document(page_content=nome, metadata={"tipo": tipo})

    def test_catalogo_entra_mesmo_perdendo_em_relevancia(self):
        # Regressão real: numa pergunta sobre Darcy em H1, as 3 vagas foram
        # ocupadas pelas receitas e o catálogo problema→material — único
        # documento que aponta TPZDarcyFlow — ficou de fora.
        pool = [self._doc("receita1", "doc_fluxo"),
                self._doc("receita2", "doc_fluxo"),
                self._doc("receita3", "doc_fluxo"),
                self._doc("catalogo", "doc_conceito")]
        escolhidos = [d.page_content for d in
                      pipeline._reservar_vagas_conceitos(pool, k=3, reservadas=1)]
        self.assertIn("catalogo", escolhidos)
        self.assertEqual(len(escolhidos), 3)

    def test_sem_conceito_disponivel_nao_perde_vaga(self):
        pool = [self._doc(f"receita{i}", "doc_fluxo") for i in range(4)]
        escolhidos = pipeline._reservar_vagas_conceitos(pool, k=3, reservadas=1)
        self.assertEqual(len(escolhidos), 3)

    def test_reserva_zero_preserva_ordem_original(self):
        pool = [self._doc("a", "doc_fluxo"), self._doc("b", "doc_conceito")]
        escolhidos = [d.page_content for d in
                      pipeline._reservar_vagas_conceitos(pool, k=2, reservadas=0)]
        self.assertEqual(escolhidos, ["a", "b"])


class TestPerguntaExplicativa(unittest.TestCase):
    def test_explicativas(self):
        for p in ("O que é a classe TPZGeoMesh e para que ela serve?",
                  "Explique a classe TPZInt1d do NeoPZ",
                  "como funciona o AutoBuild?",
                  "qual a diferença entre TPZGeoMesh e TPZCompMesh?"):
            self.assertTrue(pipeline._pergunta_e_explicativa(p), p)

    def test_pedidos_de_codigo(self):
        for p in ("Crie uma malha geométrica 2D com TPZGeoMeshTools",
                  "Escreva um código completo de elasticidade",
                  "Explique como criar um código de Poisson",   # pede código
                  "resolva um problema de Darcy misto"):
            self.assertFalse(pipeline._pergunta_e_explicativa(p), p)

    def test_explicativas_em_ingles(self):
        for p in ("What is the TPZGeoMesh class and what is it for?",
                  "Explain the TPZInt1d class in NeoPZ",
                  "How does AutoBuild work?",
                  "What does AutoBuild do?",
                  "What's the difference between TPZGeoMesh and TPZCompMesh?"):
            self.assertTrue(pipeline._pergunta_e_explicativa(p), p)

    def test_pedidos_de_codigo_em_ingles(self):
        for p in ("Create a 2D geometric mesh with TPZGeoMeshTools",
                  "Write complete code for linear elasticity",
                  "Explain how to create a Poisson program",   # asks for code
                  "Solve a mixed Darcy problem"):
            self.assertFalse(pipeline._pergunta_e_explicativa(p), p)


class TestRegrasSemanticas(unittest.TestCase):
    MISTO = ('Here is the code:\n\n```cpp\n'
             '#include "DarcyFlow/TPZMixedDarcyFlow.h"\n'
             'auto *mat = new TPZMixedDarcyFlow(1, 2);\n'
             'cmesh->BuildMultiphysicsSpace(active, meshes);\n'
             '{solver}\n```\n')

    def test_solver_errado_no_misto_e_pego(self):
        r = pipeline.validar_semantica(self.MISTO.format(solver="solver.SetDirect(ECholesky);"))
        self.assertTrue(any("ELDLt" in e for e in r), r)

    def test_comentario_que_cita_o_solver_errado_nao_dispara(self):
        # Regressão real: a receita do Darcy misto tem o comentário
        # "saddle point: ELDLt, NEVER ECholesky"; o modelo o copiava junto e a
        # regra reprovava as 3 tentativas de um código correto
        codigo = self.MISTO.format(
            solver="// saddle point: ELDLt, NEVER ECholesky\nsolver.SetDirect(ELDLt);")
        self.assertEqual(pipeline.validar_semantica(codigo), [])

    def test_prosa_que_cita_o_solver_errado_nao_dispara(self):
        codigo = (self.MISTO.format(solver="solver.SetDirect(ELDLt);")
                  + "\nNote: ECholesky would fail here, because the system is indefinite.")
        self.assertEqual(pipeline.validar_semantica(codigo), [])


class TestRegrasElasticidade3D(unittest.TestCase):
    ELAST3D = ('```cpp\n'
               '#include "Elasticity/TPZElasticity3D.h"\n'
               '// in 3D it is TPZElasticity3D — the 2D class is ONLY for 2D\n'
               'TPZManVector<STATE, 3> force = {0., 0., -1.};\n'
               'auto *mat = new TPZElasticity3D(1, E, nu, force);\n'
               '```\n')

    def test_comentario_sobre_o_material_2d_nao_dispara(self):
        # Regressão real do benchmark elasticidade_3d: o comentário citava a
        # classe 2D e planeStress; o auto-include adicionava o header dela e a
        # regra do construtor 2D reprovava as 3 tentativas de um código correto
        self.assertEqual(pipeline.validar_semantica(self.ELAST3D), [])

    def test_construtor_2d_transplantado_para_3d_e_pego(self):
        codigo = ('```cpp\n'
                  '#include "Elasticity/TPZElasticity3D.h"\n'
                  'constexpr int planeStress{1};\n'
                  'auto *mat = new TPZElasticity3D(id, E, nu, planeStress);\n'
                  '```\n')
        r = pipeline.validar_semantica(codigo)
        self.assertTrue(any("TPZElasticity3D" in e for e in r), r)


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
        self.assertIn("[... answer truncated ...]", texto)
        self.assertNotIn("x" * 200, texto)

    def test_historico_entra_no_prompt(self):
        prompt = pipeline._montar_prompt(
            "e como refino essa malha?", "CONTEXTO", "sistema", set(), set(),
            historico=[("como crio uma malha?", "Use TPZGeoMeshTools.")],
        )
        self.assertIn("CONVERSATION HISTORY", prompt)
        self.assertIn("como crio uma malha?", prompt)
        # a tarefa atual continua sendo a pergunta nova
        self.assertIn("Task: e como refino essa malha?", prompt)


class TestDeteccaoDeCodigo(unittest.TestCase):
    def test_prosa_nao_e_codigo(self):
        prosa = ("A classe TPZGeoMesh representa a malha geométrica do NeoPZ. "
                 "Ela armazena os nós e elementos da geometria do problema.")
        self.assertFalse(pipeline._resposta_contem_codigo(prosa))

    def test_codigo_e_detectado(self):
        self.assertTrue(pipeline._resposta_contem_codigo("```cpp\nint main() {}\n```"))
        self.assertTrue(pipeline._resposta_contem_codigo(
            "TPZGeoMesh *gmesh = new TPZGeoMesh();"))


class _DBFalso:
    """Banco vetorial que não devolve nada — o que interessa nestes testes é o
    LOOP (validação → compilação → retry), não a recuperação."""
    def max_marginal_relevance_search(self, *a, **kw):
        return []

    def similarity_search(self, *a, **kw):
        return []


class _LLMFalso:
    """Devolve respostas pré-programadas, uma por tentativa (repete a última se
    acabarem), e guarda os prompts recebidos para inspeção."""
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.prompts = []

    def stream(self, prompt):
        self.prompts.append(prompt)
        yield self.respostas[min(len(self.prompts) - 1, len(self.respostas) - 1)]


class TestCompilacaoNoLoop(unittest.TestCase):
    """
    A compilação plugada em gerar_codigo — a confirmação POR CLASSE que a
    whitelist global de métodos não dá.

    Cenário-base (real, de tests/test_compilacao.py): SetElasticity existe no
    NeoPZ — em TPZElasticity2D. Chamado num TPZDarcyFlow, passa por todas as
    checagens de NOME e ia embora carimbado "✅ Nomes verificados". Aqui
    `_compilar_codigo` é dublê: o loop é o objeto do teste, não o g++ (a
    compilação de verdade tem cobertura em tests/test_compilacao.py e exige
    NeoPZ instalado).
    """
    RESPOSTA_QUE_NAO_COMPILA = (
        "Segue o material de Darcy:\n\n```cpp\n"
        '#include "DarcyFlow/TPZDarcyFlow.h"\n'
        "TPZDarcyFlow *mat = new TPZDarcyFlow(1, 2);\n"
        "mat->SetElasticity(2.e3, 0.3);\n```\n"
    )
    RESPOSTA_COM_CLASSE_INVENTADA = (
        "Agora vai:\n\n```cpp\n"
        '#include "DarcyFlow/TPZDarcyFlow.h"\n'
        "TPZCoisaQueNaoExiste *mat = nullptr;\n```\n"
    )
    ERRO_GPP = ["'class TPZDarcyFlow' has no member named 'SetElasticity'"]

    def _gerar(self, llm):
        """gerar_codigo com o mínimo para o loop rodar. methods_whitelist
        contém SetElasticity de propósito: é o ponto do teste que a validação
        de nomes APROVA a chamada."""
        db = _DBFalso()
        with redirect_stdout(io.StringIO()), \
             patch.object(pipeline, "validar_semantica", return_value=[]):
            return pipeline.gerar_codigo(
                "material de darcy",
                llm=llm, headers_db=db, examples_db=db,
                whitelist={"TPZDarcyFlow"},
                headers_whitelist={"TPZDarcyFlow.h"},
                system_base="sistema",
                methods_whitelist={"SetElasticity"},
            )

    def test_nomes_aprovam_o_que_o_compilador_reprova(self):
        llm = _LLMFalso(self.RESPOSTA_QUE_NAO_COMPILA)
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "erros", "erros": self.ERRO_GPP, "ignorados": 0}):
            r = self._gerar(llm)
        # A validação de nomes não achou nada — era exatamente assim que o
        # selo saía em cima de código que não compila
        self.assertEqual(r["alucinacoes"], [])
        self.assertEqual(r["metodos_suspeitos"], [])
        # ...e agora o resultado NÃO é válido, com o erro do compilador junto
        self.assertFalse(r["valido"])
        self.assertEqual(r["compilacao"]["erros"], self.ERRO_GPP)
        # 2ª tentativa dá diagnóstico idêntico → parada antecipada aborta o retry
        self.assertEqual(r["tentativas"], 2)

    def test_erro_do_compilador_volta_no_prompt_do_retry(self):
        llm = _LLMFalso(self.RESPOSTA_QUE_NAO_COMPILA)
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "erros", "erros": self.ERRO_GPP, "ignorados": 0}):
            self._gerar(llm)
        self.assertNotIn("COMPILER", llm.prompts[0])       # 1ª tentativa: nada a corrigir
        self.assertIn("COMPILER", llm.prompts[1])
        self.assertIn("has no member named 'SetElasticity'", llm.prompts[1])

    def test_erro_de_aridade_volta_no_prompt_do_retry(self):
        # Regressão real do benchmark refinamento_uniforme: a chamada com
        # aridade errada reprovava a resposta (via v["erros_aridade"]) mas o
        # prompt do retry nunca mencionava o erro — gerar_codigo não passava
        # erros_aridade ao _montar_prompt, e o modelo repetiu
        # UniformRefinement(1, gmesh) nas 3 tentativas.
        errada = ("```cpp\nTPZDarcyFlow *mat = new TPZDarcyFlow(1, 2);\n"
                  "mat->SetConstantPermeability(1.0, 2.0);\n```\n")
        certa = ("```cpp\nTPZDarcyFlow *mat = new TPZDarcyFlow(1, 2);\n"
                 "mat->SetConstantPermeability(1.0);\n```\n")
        llm = _LLMFalso(errada, certa)
        db = _DBFalso()
        with redirect_stdout(io.StringIO()), \
             patch.object(pipeline, "validar_semantica", return_value=[]), \
             patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "ok", "erros": [], "ignorados": 0}):
            r = pipeline.gerar_codigo(
                "material de darcy",
                llm=llm, headers_db=db, examples_db=db,
                whitelist={"TPZDarcyFlow"},
                headers_whitelist={"TPZDarcyFlow.h"},
                system_base="sistema",
                methods_whitelist={"SetConstantPermeability"},
                class_methods_index={"TPZDarcyFlow": {
                    "SetConstantPermeability": {"min_args": 1, "max_args": 1}}},
            )
        self.assertNotIn("ARITY ERROR", llm.prompts[0])   # 1ª tentativa: nada a corrigir
        self.assertIn("ARITY ERROR", llm.prompts[1])
        self.assertIn("SetConstantPermeability", llm.prompts[1])
        self.assertTrue(r["valido"])
        self.assertEqual(r["tentativas"], 2)
        self.assertTrue(r["diagnosticos"][0]["erros_aridade"])
        self.assertIn("SetConstantPermeability", r["diagnosticos"][0]["erros_aridade"][0])

    def test_erro_de_aridade_de_construtor_entra_no_resultado(self):
        # Caso real do benchmark: TPZManVector<REAL,3> v(1., 2., 3.) — o
        # construtor mora no índice sob o nome da própria classe, e a
        # verificação tem de reprovar a resposta SEM precisar do g++
        resposta = ("Segue:\n\n```cpp\nTPZManVector<REAL,3> v(1., 2., 3.);\n```\n")
        with redirect_stdout(io.StringIO()), \
             patch.object(pipeline, "validar_semantica", return_value=[]):
            v = pipeline._verificar_resposta(
                resposta,
                whitelist={"TPZManVector"},
                headers_whitelist=set(),
                methods_whitelist={"Print"},
                class_header_index={},
                class_methods_index={"TPZManVector": {"TPZManVector": {
                    "min_args": 0, "max_args": 2,
                    "sigs": ["TPZManVector(const int64_t size = 0)",
                             "TPZManVector(const int64_t size, const T& copy)"]}}},
                collisions={}, renames={}, legacy_classes=set(),
                destinos={"TPZManVector"},
            )
        self.assertEqual(len(v["erros_aridade"]), 1)
        self.assertIn("TPZManVector::TPZManVector", v["erros_aridade"][0])
        self.assertIn("got 3", v["erros_aridade"][0])
        self.assertFalse(v["nomes_ok"])
        self.assertFalse(v["valido"])

    def test_compilacao_ok_vira_selo_mais_forte(self):
        llm = _LLMFalso(self.RESPOSTA_QUE_NAO_COMPILA)
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "ok", "erros": [], "ignorados": 0}):
            r = self._gerar(llm)
        self.assertTrue(r["valido"])
        self.assertEqual(r["compilacao"]["status"], "ok")
        self.assertEqual(r["tentativas"], 1)

    def test_sem_neopz_instalado_nada_muda(self):
        # O caso de quem instalou pelo Caminho A do README: sem compilador, a
        # checagem some em silêncio. Se este teste falhar, plugar a compilação
        # virou REGRESSÃO para a maioria dos usuários.
        for status in ("indisponivel", "inconclusivo", "timeout"):
            with self.subTest(status=status):
                llm = _LLMFalso(self.RESPOSTA_QUE_NAO_COMPILA)
                with patch.object(pipeline, "_compilar_codigo",
                                  return_value={"status": status, "erros": [], "ignorados": 2}):
                    r = self._gerar(llm)
                self.assertTrue(r["valido"])
                self.assertEqual(r["tentativas"], 1)

    def test_prosa_nao_e_compilada(self):
        llm = _LLMFalso("A classe TPZDarcyFlow representa o escoamento em meio poroso.")
        with patch.object(pipeline, "_compilar_codigo") as compilar:
            r = self._gerar(llm)
        compilar.assert_not_called()
        self.assertTrue(r["valido"])

    def test_retry_pior_nao_apaga_a_melhor_tentativa(self):
        # A regressão que plugar a compilação poderia criar: antes, a tentativa
        # com nomes limpos era devolvida na hora; agora ela vira insumo de
        # retry. Se as seguintes alucinarem, é ELA que tem de voltar.
        llm = _LLMFalso(self.RESPOSTA_QUE_NAO_COMPILA, self.RESPOSTA_COM_CLASSE_INVENTADA)
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "erros", "erros": self.ERRO_GPP, "ignorados": 0}):
            r = self._gerar(llm)
        self.assertIn("TPZDarcyFlow", r["resposta"])
        self.assertNotIn("TPZCoisaQueNaoExiste", r["resposta"])
        self.assertEqual(r["alucinacoes"], [])
        self.assertEqual(r["compilacao"]["erros"], self.ERRO_GPP)


class TestClasseForaDaInstalacao(unittest.TestCase):
    """
    Classe que EXISTE no NeoPZ mas cujo header a instalação não tem.

    O índice classe→header é montado a partir da pasta do CÓDIGO-FONTE; a
    compilação roda contra a BIBLIOTECA INSTALADA. 238 das 847 classes do
    índice estão numa e não na outra, e o pipeline tratava a diferença como
    culpa do modelo: injetava o include certo-no-source, o g++ respondia
    "No such file or directory", _erro_denuncia_alucinacao lia isso como
    alucinação — dois retries queimados e resposta sem selo, por uma classe
    que existe de verdade.
    """
    BURGER = {"TPZBurger": "Material/needrefactor/REAL/pzburger.h"}
    CODIGO = "int main() { TPZBurger *m = new TPZBurger(1, 2); }\n"

    def setUp(self):
        pipeline.validation._INDISPONIVEL_CACHE.clear()
        self.maxDiff = None

    tearDown = setUp

    def test_dir_fora_do_build_dispensa_instalacao(self):
        # needrefactor/ não é citado em nenhum CMakeLists do NeoPZ (develop e
        # 2022): é fato da revisão, não da máquina — vale mesmo sem NeoPZ
        # instalado, que é o Caminho A do README
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None):
            self.assertEqual(pipeline._motivo_indisponivel(self.BURGER["TPZBurger"]),
                             "not part of the NeoPZ build")
            self.assertIsNone(pipeline._motivo_indisponivel("Mesh/pzgmesh.h"))

    def test_sonda_responde_pela_instalacao_desta_maquina(self):
        # Plasticidade é opção de build (BUILD_PLASTICITY_MATERIALS): as MESMAS
        # classes existem na instalação de quem ligou a flag e faltam na de quem
        # não ligou. Por isso a resposta vem de sondar a instalação — uma lista
        # gravada no repo mentiria em metade das máquinas.
        caminho = "Material/Plasticity/TPZMatElastoPlastic.h"
        with tempfile.TemporaryDirectory() as tmp:
            inc = Path(tmp) / "include" / "Material"
            (inc / "Plasticity").mkdir(parents=True)
            with patch.object(pipeline.validation, "_neopz_prefix", return_value=Path(tmp)), \
                 patch.object(pipeline.validation, "_include_flags", return_value=[f"-I{inc}"]):
                self.assertEqual(pipeline._motivo_indisponivel(caminho),
                                 "não está nesta instalação do NeoPZ")
                pipeline.validation._INDISPONIVEL_CACHE.clear()
                (inc / "Plasticity" / "TPZMatElastoPlastic.h").write_text("")
                self.assertIsNone(pipeline._motivo_indisponivel(caminho))

    def test_include_impossivel_nao_e_injetado(self):
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None):
            corrigido, correcoes = pipeline._corrigir_includes_automaticamente(
                self.CODIGO, self.BURGER, {}, {"pzburger.h"})
        self.assertNotIn("#include", corrigido)
        self.assertEqual(correcoes, [])

    def test_include_impossivel_nao_e_exigido(self):
        # Exigir dispararia retry a cada tentativa, sem nunca poder ser atendido
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None):
            self.assertEqual(
                pipeline._validar_includes_por_classe(self.CODIGO, self.BURGER, {}), {})

    def test_classe_inutilizavel_nao_e_destino_de_correcao(self):
        # A whitelist responde "existe no NeoPZ" e por isso mantém TPZBurger —
        # mas ela também é a lista de DESTINOS da correção determinística, e o
        # chute 'TPZBurguer' era reescrito para uma classe que não compila em
        # máquina nenhuma, com selo de "corrigido automaticamente" junto
        codigo = "int main() { TPZBurguer *m = nullptr; }"
        whitelist = {"TPZBurger", "TPZDarcyFlow"}
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None):
            destinos = pipeline._whitelist_utilizavel(whitelist, self.BURGER)
            _, correcoes = pipeline._corrigir_classes_automaticamente(
                codigo, whitelist, {}, destinos=destinos)
        self.assertNotIn("TPZBurger", destinos)
        self.assertIn("TPZDarcyFlow", destinos)   # classe utilizável fica
        self.assertEqual(correcoes, [])           # sem destino, nome fica alucinado

    def test_classe_fora_do_indice_continua_sendo_destino(self):
        # Não saber onde a classe mora não é motivo para descartá-la: sem
        # entrada no índice classe→header, ela segue disponível como destino
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None):
            destinos = pipeline._whitelist_utilizavel({"TPZClasseNova"}, self.BURGER)
        self.assertEqual(destinos, {"TPZClasseNova"})

    def test_loop_nao_acusa_alucinacao_nem_queima_retry(self):
        llm = _LLMFalso("Segue:\n\n```cpp\nTPZBurger *mat = new TPZBurger(1, 2);\n```\n")
        db = _DBFalso()
        with patch.object(pipeline.validation, "_neopz_prefix", return_value=None), \
             patch.object(pipeline, "_compilar_codigo") as compilar, \
             redirect_stdout(io.StringIO()):
            r = pipeline.gerar_codigo(
                "equação de convecção",
                llm=llm, headers_db=db, examples_db=db,
                whitelist={"TPZBurger"},
                headers_whitelist={"pzburger.h"},
                system_base="sistema",
                class_header_index=self.BURGER,
            )
        # Sem o header, o g++ cospe "was not declared in this scope" para cada
        # uso — diagnóstico que também está em _DIAG_ALUCINACAO. Compilar aqui
        # só geraria acusação falsa em cascata.
        compilar.assert_not_called()
        self.assertEqual(r["compilacao"]["status"], "indisponivel")
        self.assertEqual(r["tentativas"], 1)          # antes: MAX_RETRIES + 1
        self.assertTrue(r["valido"])
        self.assertEqual(r["alucinacoes"], [])
        self.assertEqual(r["classes_indisponiveis"],
                         {"TPZBurger": "not part of the NeoPZ build"})


class TestClassesCitadasEmErros(unittest.TestCase):
    def test_classe_do_diagnostico_vira_reforco(self):
        erros = ["'class TPZDarcyFlow' has no member named 'SetElasticity'"]
        self.assertEqual(
            pipeline._classes_citadas_em_erros(erros, {"TPZDarcyFlow", "TPZGeoMesh"}),
            {"TPZDarcyFlow"})

    def test_ruido_de_template_fora_da_whitelist_e_descartado(self):
        # g++ despeja tipos instanciados na mensagem; buscar chunk de nome que
        # não existe na whitelist só poluiria o contexto do retry
        erros = ["no matching function for call to 'TPZVecInexistente<double>::Resize()'"]
        self.assertEqual(pipeline._classes_citadas_em_erros(erros, {"TPZDarcyFlow"}), set())


class TestReforcoPorNomeCitadoEmErro(unittest.TestCase):
    ERRO_ENUM = ["'EHexa' is not a member of 'MMeshType'"]
    DECL_ENUM = "enum class MMeshType\n{\n    ETriangular, EQuadrilateral, EHexahedral\n};"

    class _DBComHeaders(_DBFalso):
        def __init__(self, docs):
            from langchain_core.documents import Document
            self.docs = [Document(page_content=t, metadata={"source": f, "classe": ""})
                         for f, t in docs]
            self.consultas = []

        def similarity_search(self, consulta, k=4, **kw):
            self.consultas.append(consulta)
            return self.docs[:k]

    def test_nomes_fora_do_padrao_tpz_saem_do_erro(self):
        nomes = pipeline._nomes_citados_em_erros(
            self.ERRO_ENUM + ["'class TPZVec<int>' has no member named 'Push'"])
        self.assertIn("MMeshType", nomes)
        self.assertIn("EHexa", nomes)
        self.assertNotIn("TPZVec", nomes)

    def test_so_entra_doc_que_declara_o_nome(self):
        db = self._DBComHeaders([("Pre/uso.h", "void f(MMeshType t);"),
                                 ("Pre/MMeshType.h", self.DECL_ENUM)])
        docs = pipeline._buscar_declaracoes_por_nome(db, {"MMeshType", "EHexa"}, limite=2)
        self.assertEqual([d.metadata["source"] for d in docs], ["Pre/MMeshType.h"])

    def test_declaracao_do_enum_chega_ao_prompt_do_retry(self):
        llm = _LLMFalso("```cpp\nint main() { auto t = MMeshType::EHexa; return 0; }\n```\n")
        db = self._DBComHeaders([("Pre/MMeshType.h", self.DECL_ENUM)])
        with patch.object(pipeline, "_compilar_codigo",
                          return_value={"status": "erros", "erros": self.ERRO_ENUM, "ignorados": 0}), \
             patch.object(pipeline, "validar_semantica", return_value=[]), \
             patch.object(pipeline.time, "sleep"), \
             redirect_stdout(io.StringIO()):
            pipeline.gerar_codigo("3D mesh", llm=llm, headers_db=db, examples_db=_DBFalso(),
                                  whitelist={"TPZGeoMesh"}, headers_whitelist=set(),
                                  system_base="sistema")
        self.assertNotIn("EHexahedral", llm.prompts[0])
        self.assertIn("EHexahedral", llm.prompts[1])


class TestCardsGarantidos(unittest.TestCase):
    """Os cards de API (tipo 'doc_card') perdiam o rerank da wiki para
    páginas de prosa e nunca entravam no contexto. Quando a pergunta cita a
    classe pelo nome, o card é garantido no início de w_docs — fora do
    K_WIKI, como `garantidos` faz com headers."""

    def _contexto(self, pergunta, wiki_db):
        headers_db = MockDB()
        examples_db = MockDB()
        with patch("pipeline.retrieval._get_reranker",
                   return_value=_RerankerFalso([10.0] * 20)):
            return pipeline._recuperar_contexto(
                pergunta, headers_db, examples_db, wiki_db, explicativa=True)

    def _card(self, classe):
        from langchain_core.documents import Document
        return Document(
            page_content=f"# {classe} — API card",
            metadata={"tipo": "doc_card", "classes_usadas": classe,
                      "source": f"wiki/classes/{classe}.md"})

    def test_card_entra_quando_a_pergunta_cita_a_classe(self):
        card = self._card("TPZCondensedCompEl")
        prosa = Document_wiki("conceito", "condensacao.md")
        wiki_db = MockDB(docs_sim=[card], docs_mmr=[prosa])
        _, _, w_docs, _ = self._contexto(
            "How does TPZCondensedCompEl work?", wiki_db)
        self.assertEqual(w_docs[0].metadata["tipo"], "doc_card")
        self.assertIn("TPZCondensedCompEl", w_docs[0].page_content)

    def test_card_nao_entra_sem_classe_citada(self):
        card = self._card("TPZCondensedCompEl")
        prosa = Document_wiki("conceito", "condensacao.md")
        wiki_db = MockDB(docs_sim=[card], docs_mmr=[prosa])
        _, _, w_docs, _ = self._contexto(
            "What is static condensation?", wiki_db)
        self.assertNotIn("doc_card", {d.metadata.get("tipo") for d in w_docs})

    def test_card_nao_conta_no_k_wiki(self):
        from pipeline.config import K_WIKI
        card = self._card("TPZCondensedCompEl")
        prosas = [Document_wiki("conceito", f"prosa{i}.md") for i in range(K_WIKI)]
        wiki_db = MockDB(docs_sim=[card], docs_mmr=prosas)
        _, _, w_docs, _ = self._contexto(
            "How does TPZCondensedCompEl work?", wiki_db)
        self.assertEqual(len(w_docs), K_WIKI + 1)
        self.assertEqual(w_docs[0].metadata["tipo"], "doc_card")

    def test_falso_positivo_de_similaridade_e_filtrado(self):
        # similarity_search pode devolver o card de OUTRA classe — só é
        # aceito se a classe citada constar em classes_usadas do card
        card_outra = self._card("TPZCompMeshTools")
        wiki_db = MockDB(docs_sim=[card_outra], docs_mmr=[])
        _, _, w_docs, _ = self._contexto(
            "How does TPZCondensedCompEl work?", wiki_db)
        self.assertEqual(w_docs, [])


def Document_wiki(tipo, source):
    from langchain_core.documents import Document
    return Document(page_content=f"prosa {source}",
                    metadata={"tipo": tipo, "classes_usadas": "", "source": source})


def _gerar(pergunta, llm):
    return pipeline.gerar_codigo(
        pergunta,
        llm=llm,
        headers_db=MockDB(),
        examples_db=MockDB(),
        wiki_db=None,
        whitelist={"TPZGeoMesh"},
        headers_whitelist={"pzgmesh.h"},
        methods_whitelist=set(),
        class_header_index={},
        class_methods_index={},
        collisions={},
        renames={},
        legacy_classes=set(),
        enum_values_index={},
        system_base="system",
    )


_CODIGO_INVALIDO = "```cpp\nTPZClasseQueNaoExiste *x = nullptr;\n```"


class TestRetryPorEdicao(unittest.TestCase):
    def test_segunda_tentativa_recebe_o_codigo_anterior(self):
        llm = _LLMFalso(_CODIGO_INVALIDO, "Resposta final sem código.")
        resultado = _gerar("solve a problem", llm)
        self.assertEqual(resultado["tentativas"], 2)
        self.assertIn(_CODIGO_INVALIDO, llm.prompts[1])
        self.assertIn("fix ONLY the flagged parts", llm.prompts[1])
        self.assertNotIn("YOUR PREVIOUS CODE", llm.prompts[0])


class TestParadaAntecipada(unittest.TestCase):
    def test_diagnostico_identico_aborta_o_retry(self):
        llm = _LLMFalso(_CODIGO_INVALIDO)
        resultado = _gerar("solve a problem", llm)
        self.assertEqual(resultado["tentativas"], 2)
        self.assertEqual(len(resultado["diagnosticos"]), 2)


class TestClassesPorIntencao(unittest.TestCase):
    def test_vtk_sugere_class_sem_citar_nome(self):
        classes = pipeline.retrieval._classes_por_intencao(
            "export the solution to vtk")
        self.assertIn("TPZVTKGenerator", classes)


class TestSleepSoParaAPI(unittest.TestCase):
    def test_ollama_nao_dorme_entre_retries(self):
        OllamaLLMFalso = type("OllamaLLM", (_LLMFalso,), {})
        llm = OllamaLLMFalso(_CODIGO_INVALIDO)
        with patch("pipeline.time.sleep") as dormir:
            _gerar("solve a problem", llm)
        dormir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
