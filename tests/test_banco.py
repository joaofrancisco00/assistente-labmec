"""
Busca exata em memória sobre as coleções do Chroma (pipeline/banco.py).

A busca HNSW do Chroma é aproximada: o mesmo vetor de consulta devolvia
candidatos diferentes entre processos, o prompt mudava e o LLM_CACHE errava.

Rodar:  python3 -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from pipeline.banco import BancoExato

RAIZ = Path(__file__).resolve().parent.parent


class _EmbeddingsFalsos:
    VETORES = {"malha": [1.0, 0.0, 0.0], "material": [0.0, 1.0, 0.0],
               "solver": [0.0, 0.0, 1.0]}

    def embed_query(self, texto):
        v = np.array(self.VETORES.get(texto, [1.0, 1.0, 0.0]))
        return list(v / np.linalg.norm(v))


def _banco(itens):
    vetores = np.array([v for _, v, _ in itens], dtype=np.float32)
    vetores /= np.linalg.norm(vetores, axis=1, keepdims=True)
    return BancoExato.de_dados(
        documentos=[t for t, _, _ in itens], metadados=[m for _, _, m in itens],
        embeddings=vetores, embeddings_fn=_EmbeddingsFalsos())


class TestBuscaExata(unittest.TestCase):
    ITENS = [
        ("TPZGeoMesh", [0.9, 0.1, 0.0], {"classe": "TPZGeoMesh"}),
        ("TPZMatPoisson", [0.1, 0.9, 0.0], {"classe": "TPZMatPoisson"}),
        ("TPZStepSolver", [0.0, 0.1, 0.9], {"classe": "TPZStepSolver"}),
        ("TPZGeoEl", [0.8, 0.2, 0.0], {"classe": "TPZGeoEl"}),
    ]

    def test_similaridade_ordena_pelo_mais_proximo(self):
        docs = _banco(self.ITENS).similarity_search("malha", k=2)
        self.assertEqual([d.page_content for d in docs], ["TPZGeoMesh", "TPZGeoEl"])

    def test_filtro_por_metadado(self):
        docs = _banco(self.ITENS).similarity_search("malha", k=3, filter={"classe": "TPZStepSolver"})
        self.assertEqual([d.page_content for d in docs], ["TPZStepSolver"])

    def test_empate_e_desfeito_pela_ordem_do_banco(self):
        itens = [("A", [1.0, 0.0, 0.0], {}), ("B", [1.0, 0.0, 0.0], {}), ("C", [0.0, 1.0, 0.0], {})]
        for _ in range(5):
            docs = _banco(itens).similarity_search("malha", k=2)
            self.assertEqual([d.page_content for d in docs], ["A", "B"])

    def test_mmr_diversifica(self):
        docs = _banco(self.ITENS).max_marginal_relevance_search("malha", k=2, fetch_k=4)
        self.assertEqual(docs[0].page_content, "TPZGeoMesh")
        self.assertNotEqual(docs[1].page_content, "TPZGeoEl")

    def test_metadados_nao_vazam_entre_consultas(self):
        banco = _banco(self.ITENS)
        banco.similarity_search("malha", k=1)[0].metadata["rerank_score"] = 1.0
        self.assertNotIn("rerank_score", banco.similarity_search("malha", k=1)[0].metadata)

    def test_k_maior_que_o_banco(self):
        self.assertEqual(len(_banco(self.ITENS).similarity_search("malha", k=50)), 4)


SCRIPT_HASH = r"""
import hashlib, io, contextlib, sys
with contextlib.redirect_stdout(io.StringIO()):
    import pipeline
    from pipeline.context import PipelineContext
    ctx = PipelineContext.load()
q = sys.argv[1]
h, e, w, _ = pipeline._recuperar_contexto(q, ctx.headers_db, ctx.examples_db, ctx.wiki_db)
print(hashlib.md5(pipeline._formatar_contexto(h, e, w).encode()).hexdigest())
"""


@unittest.skipUnless((RAIZ / "banco_chroma_develop" / "chroma.sqlite3").exists(),
                     "índice não gerado (rode indexer.py)")
@unittest.skipUnless(os.environ.get("TESTE_DETERMINISMO"),
                     "lento (carrega o índice 2x) — rode com TESTE_DETERMINISMO=1")
class TestContextoDeterministico(unittest.TestCase):
    def test_mesmo_contexto_em_processos_diferentes(self):
        pergunta = ("Write complete C++ code with NeoPZ to solve a 3D Poisson problem "
                    "on a unit cube meshed with hexahedra, with all the necessary includes.")
        hashes = set()
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "hash.py"
            script.write_text(SCRIPT_HASH)
            for semente in ("1", "2"):
                env = {**os.environ, "PYTHONHASHSEED": semente, "PYTHONPATH": str(RAIZ)}
                env.pop("GOOGLE_API_KEY", None)
                saida = subprocess.run([sys.executable, str(script), pergunta], cwd=RAIZ, env=env,
                                       capture_output=True, text=True, timeout=600)
                self.assertEqual(saida.returncode, 0, saida.stderr[-2000:])
                hashes.add(saida.stdout.strip().splitlines()[-1])
        self.assertEqual(len(hashes), 1)


class TestValidacaoOrdenada(unittest.TestCase):
    def test_classes_inventadas_saem_em_ordem_fixa(self):
        codigo = "TPZZeta *z; TPZAlfa *a; TPZMeio *m;"
        self.assertEqual(pipeline._validar_codigo(codigo, {"TPZGeoMesh"}),
                         ["TPZAlfa", "TPZMeio", "TPZZeta"])


if __name__ == "__main__":
    unittest.main()
