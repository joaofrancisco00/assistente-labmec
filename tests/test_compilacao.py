"""
Testes da compilação do código gerado (_compilar_codigo e auxiliares).

Os testes de MONTAGEM e FILTRO são puros e rodam em qualquer máquina. Os que
compilam de fato são pulados quando não há instalação do NeoPZ — que é a
situação de quem instalou pelo Caminho A do README.

Rodar:  python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline

RAIZ = Path(__file__).resolve().parent.parent
TEM_NEOPZ = (pipeline._neopz_prefix() is not None
             and pipeline._compilador_disponivel() is not None)
precisa_neopz = unittest.skipUnless(
    TEM_NEOPZ, "sem instalação do NeoPZ/compilador — checagem de compilação é opcional")


def bloco(codigo: str) -> str:
    """Embrulha código como o modelo entrega: prosa + bloco cercado."""
    return f"Segue o exemplo:\n\n```cpp\n{codigo}\n```\n\nEspero ter ajudado."


class TestExtracaoDeBlocos(unittest.TestCase):
    def test_bloco_cpp_e_extraido(self):
        self.assertEqual(pipeline._extrair_blocos_codigo(bloco("int x = 1;")), "int x = 1;")

    def test_blocos_de_shell_sao_ignorados(self):
        # O modelo às vezes ensina a compilar junto com o código; ```bash não
        # é C++ e compilá-lo geraria erro inventado
        resposta = "Compile assim:\n\n```bash\ncmake --build .\n```\n"
        self.assertEqual(pipeline._extrair_blocos_codigo(resposta), "")

    def test_blocos_multiplos_sao_juntados_na_ordem(self):
        resposta = ("Primeiro a malha:\n\n```cpp\nTPZGeoMesh *g = nullptr;\n```\n"
                    "Depois o material:\n\n```cpp\nint id = 1;\n```\n")
        self.assertEqual(pipeline._extrair_blocos_codigo(resposta),
                         "TPZGeoMesh *g = nullptr;\nint id = 1;")

    def test_prosa_sem_bloco_nao_tem_codigo(self):
        resposta = "A classe TPZGeoMesh guarda a malha geométrica e seus nós."
        self.assertEqual(pipeline._extrair_blocos_codigo(resposta), "")


class TestMontagemDaTU(unittest.TestCase):
    def test_trecho_solto_e_envolvido_em_main(self):
        tu = pipeline._montar_tu('#include "pzgmesh.h"\nTPZGeoMesh *g = new TPZGeoMesh();')
        self.assertIn("int main()", tu)
        self.assertLess(tu.index('#include "pzgmesh.h"'), tu.index("int main()"))

    def test_programa_completo_nao_ganha_segundo_main(self):
        codigo = '#include "pzgmesh.h"\nint main() {\n    return 0;\n}'
        self.assertEqual(pipeline._montar_tu(codigo).count("int main"), 1)

    def test_definicao_de_funcao_nao_e_aninhada(self):
        # C++ não aceita função dentro de função: envolver isto num main daria
        # "a function-definition is not allowed here" — erro nosso, não do modelo
        codigo = 'TPZGeoMesh *CriaMalha(int n) {\n    return nullptr;\n}'
        tu = pipeline._montar_tu(codigo)
        self.assertLess(tu.index("CriaMalha"), tu.index("int main"))

    def test_includes_sobem_e_sao_deduplicados(self):
        codigo = ('#include "pzgmesh.h"\nint a = 1;\n#include "pzcmesh.h"\n'
                  '#include "pzgmesh.h"\nint b = 2;')
        tu = pipeline._montar_tu(codigo)
        self.assertEqual(tu.count('#include "pzgmesh.h"'), 1)
        self.assertLess(tu.index('#include "pzcmesh.h"'), tu.index("int main()"))


class TestFiltroDeDiagnosticos(unittest.TestCase):
    def test_metodo_inexistente_na_classe_e_alucinacao(self):
        self.assertTrue(pipeline._erro_denuncia_alucinacao(
            "'class TPZDarcyFlow' has no member named 'SetElasticity'"))
        self.assertTrue(pipeline._erro_denuncia_alucinacao(
            "no member named 'SetElasticity' in 'TPZDarcyFlow'"))  # redação do clang

    def test_header_inexistente_e_alucinacao(self):
        self.assertTrue(pipeline._erro_denuncia_alucinacao(
            "TPZMatPoisson.h: No such file or directory"))

    def test_classe_inexistente_e_alucinacao(self):
        self.assertTrue(pipeline._erro_denuncia_alucinacao(
            "'TPZMatLaplacian' was not declared in this scope"))

    def test_variavel_do_contexto_omitido_e_artefato(self):
        # O trecho referencia algo definido "acima", que o modelo não colou.
        # Tratar isso como alucinação gastaria retry sem motivo — o critério
        # é conservador: só nome TPZ conta
        self.assertFalse(pipeline._erro_denuncia_alucinacao(
            "'gmesh' was not declared in this scope"))

    def test_recorte_truncado_e_artefato(self):
        self.assertFalse(pipeline._erro_denuncia_alucinacao(
            "expected '}' at end of input"))
        self.assertFalse(pipeline._erro_denuncia_alucinacao(
            "a function-definition is not allowed here before '{' token"))


class TestCompilacaoSemAmbiente(unittest.TestCase):
    def test_prosa_nao_dispara_compilacao(self):
        r = pipeline._compilar_codigo("TPZGeoMesh guarda a malha geométrica.")
        self.assertEqual(r["status"], "sem_codigo")


@precisa_neopz
class TestCompilacaoDeVerdade(unittest.TestCase):
    def test_receitas_de_referencia_compilam(self):
        # As 4 receitas são o padrão-ouro do projeto: se alguma parar de
        # compilar, a wiki gerada a partir dela ensina código quebrado
        receitas = sorted(RAIZ.glob("reference_solutions/task_*/*.cpp"))
        self.assertEqual(len(receitas), 4, "esperado 4 receitas em reference_solutions/")
        for cpp in receitas:
            with self.subTest(receita=cpp.name):
                r = pipeline._compilar_codigo(bloco(cpp.read_text(encoding="utf-8")))
                self.assertEqual(r["status"], "ok", r["erros"])

    def test_metodo_de_outra_classe_e_pego(self):
        # O buraco que a whitelist global de métodos deixa de propósito:
        # SetElasticity existe (em TPZElasticity2D), então o validador de nomes
        # aprova esta chamada num material de Darcy. O compilador não.
        codigo = ('#include "DarcyFlow/TPZDarcyFlow.h"\n'
                  'auto *mat = new TPZDarcyFlow(1, 2);\n'
                  'mat->SetElasticity(2.e3, 0.3);')
        r = pipeline._compilar_codigo(bloco(codigo))
        self.assertEqual(r["status"], "erros")
        self.assertTrue(any("SetElasticity" in e for e in r["erros"]), r["erros"])

    def test_assinatura_errada_de_construtor_e_pega(self):
        # TPZElasticity2D(id, dim) é a alucinação que a própria receita task_04
        # lista como comum — a classe existe, a whitelist aprova
        codigo = ('#include "Elasticity/TPZElasticity2D.h"\n'
                  'auto *mat = new TPZElasticity2D(1, 2);')
        r = pipeline._compilar_codigo(bloco(codigo))
        self.assertEqual(r["status"], "erros")

    def test_include_sem_prefixo_de_familia_e_pego(self):
        # Headers de material da API nova moram em subpasta; o basename
        # sozinho não compila (ver _include_para_header)
        codigo = '#include "TPZMatPoisson.h"\nint x = 1;'
        r = pipeline._compilar_codigo(bloco(codigo))
        self.assertEqual(r["status"], "erros")
        self.assertTrue(any("TPZMatPoisson.h" in e for e in r["erros"]), r["erros"])

    def test_trecho_parcial_valido_compila(self):
        # Resposta típica: sem main, sem programa completo, mas API correta
        codigo = ('#include "pzgmesh.h"\n'
                  'TPZGeoMesh *gmesh = new TPZGeoMesh();\n'
                  'gmesh->SetDimension(2);')
        r = pipeline._compilar_codigo(bloco(codigo))
        self.assertEqual(r["status"], "ok", r["erros"])

    def test_variavel_de_fora_do_recorte_nao_vira_alucinacao(self):
        # O falso positivo que mataria a ideia: o trecho usa uma variável que
        # o modelo definiu num bloco anterior da explicação. Não compila, mas
        # NÃO é alucinação — precisa sair como 'inconclusivo', nunca 'erros'
        codigo = '#include "pzgmesh.h"\ngmesh->BuildConnectivity();'
        r = pipeline._compilar_codigo(bloco(codigo))
        self.assertEqual(r["status"], "inconclusivo", r["erros"])
        self.assertGreater(r["ignorados"], 0)


@unittest.skipUnless(pipeline.METHODS_WHITELIST_FILE.exists(),
                     "whitelist de métodos não gerada (rode indexer.py)")
@precisa_neopz
class TestContrasteComWhitelist(unittest.TestCase):
    def test_whitelist_aprova_o_que_o_compilador_recusa(self):
        # Documenta a lacuna que motiva a compilação no loop. Se um dia este
        # teste falhar porque a whitelist REPROVOU, a detecção por classe
        # passou a existir e vale reavaliar o custo/benefício.
        codigo = ('#include "DarcyFlow/TPZDarcyFlow.h"\n'
                  'auto *mat = new TPZDarcyFlow(1, 2);\n'
                  'mat->SetElasticity(2.e3, 0.3);')
        aprovado_pela_whitelist = pipeline._validar_metodos(
            codigo,
            pipeline._carregar_methods_whitelist(),
            pipeline._carregar_whitelist(),
        )
        self.assertEqual(aprovado_pela_whitelist, [])
        self.assertEqual(pipeline._compilar_codigo(bloco(codigo))["status"], "erros")


if __name__ == "__main__":
    unittest.main()
