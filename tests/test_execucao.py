"""
Execução do programa gerado e CMakeLists.txt para o aluno (pipeline/execucao.py).

Compilar não pega bug de runtime (ex.: SetElasticity compila, roda e grava
tensões zeradas; alocação manual de nós errada). Executar é opt-in
(EXECUTAR_CODIGO=1): roda código gerado pelo modelo na máquina.

Os testes que compilam/executam de verdade são pulados sem NeoPZ instalado.

Rodar:  python3 -m unittest discover -s tests -v
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from pipeline import execucao

RAIZ = Path(__file__).resolve().parent.parent
TEM_NEOPZ = (pipeline._neopz_prefix() is not None
             and pipeline._compilador_disponivel() is not None)
precisa_neopz = unittest.skipUnless(TEM_NEOPZ, "sem instalação do NeoPZ/compilador")

PROGRAMA_OK = '#include <iostream>\nint main() {\n    std::cout << "ola" << std::endl;\n    return 0;\n}'


def bloco(codigo: str) -> str:
    return f"Segue o programa:\n\n```cpp\n{codigo}\n```\n"


class TestCMakeLists(unittest.TestCase):
    def test_conteudo_segue_a_receita_de_referencia(self):
        texto = execucao._gerar_cmakelists("meu_prog")
        self.assertIn("find_package(NeoPZ REQUIRED)", texto)
        self.assertIn("add_executable(meu_prog main.cpp)", texto)
        self.assertIn("target_link_libraries(meu_prog PRIVATE NeoPZ::pz)", texto)
        self.assertIn("CMAKE_CXX_STANDARD 17", texto)

    def test_instrucoes_usam_a_instalacao_encontrada(self):
        with patch.object(execucao, "_neopz_prefix", return_value=Path("/opt/pz")):
            texto = execucao._instrucoes_cmake(bloco(PROGRAMA_OK))
        self.assertIn("-DNeoPZ_DIR=/opt/pz/lib/cmake/neopz", texto)
        self.assertIn("```cmake", texto)

    def test_sem_instalacao_usa_marcador(self):
        with patch.object(execucao, "_neopz_prefix", return_value=None):
            texto = execucao._instrucoes_cmake(bloco(PROGRAMA_OK))
        self.assertIn("-DNeoPZ_DIR=/path/to/neopz/lib/cmake/neopz", texto)

    def test_so_programa_completo_recebe_cmake(self):
        self.assertEqual(execucao._instrucoes_cmake("Só prosa."), "")
        self.assertEqual(execucao._instrucoes_cmake(bloco("int x = 1;")), "")


class TestLeituraDaInstalacao(unittest.TestCase):
    def test_biblioteca_e_definicoes_vem_dos_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "lib" / "cmake" / "neopz"
            cfg.mkdir(parents=True)
            (cfg / "NeoPZTargets.cmake").write_text(
                'INTERFACE_COMPILE_DEFINITIONS "\\$<\\$<CONFIG:RELEASE>:PZNODEBUG>;PZ_USING_LAPACK"\n')
            (cfg / "NeoPZTargets-relwithdebinfo.cmake").write_text(
                'IMPORTED_LOCATION_RELWITHDEBINFO "${_IMPORT_PREFIX}/pz/lib/libpz.dylib"\n')
            self.assertEqual(execucao._definicoes(Path(tmp)), ["-DPZ_USING_LAPACK"])
            self.assertEqual(execucao._biblioteca_pz(Path(tmp)), Path(tmp) / "pz/lib/libpz.dylib")


class TestQuandoNaoExecuta(unittest.TestCase):
    def test_trecho_e_prosa_nao_se_aplicam(self):
        for resposta in ("Só prosa.", bloco("int x = 1;"),
                         bloco(PROGRAMA_OK) + "\n```cpp\nint y = 2;\n```\n"):
            with self.subTest(resposta=resposta[:20]):
                self.assertEqual(execucao._executar_codigo(resposta)["status"], "nao_aplicavel")

    def test_sem_neopz_fica_indisponivel(self):
        with patch.object(execucao, "_neopz_prefix", return_value=None):
            self.assertEqual(execucao._executar_codigo(bloco(PROGRAMA_OK))["status"], "indisponivel")


@precisa_neopz
class TestExecucaoDeVerdade(unittest.TestCase):
    def _rodar(self, codigo, **kw):
        return execucao._executar_codigo(bloco(codigo), **kw)

    def test_receitas_de_referencia_executam(self):
        for cpp in sorted(RAIZ.glob("reference_solutions/task_*/*.cpp")):
            with self.subTest(receita=cpp.name):
                r = self._rodar(cpp.read_text(encoding="utf-8"))
                self.assertEqual(r["status"], "ok", r)

    def test_vtk_gerado_aparece_nos_arquivos(self):
        r = self._rodar((RAIZ / "reference_solutions/task_03_poisson2d/poisson.cpp").read_text())
        self.assertTrue(any(a.endswith(".vtk") for a in r["arquivos"]), r["arquivos"])

    def test_saida_e_capturada(self):
        r = self._rodar(PROGRAMA_OK)
        self.assertEqual(r["status"], "ok")
        self.assertIn("ola", r["saida"])

    def test_codigo_de_saida_diferente_de_zero(self):
        r = self._rodar('#include <cstdlib>\nint main() { return 3; }')
        self.assertEqual(r["status"], "erro_execucao")
        self.assertEqual(r["codigo_saida"], 3)

    def test_crash(self):
        r = self._rodar('int main() { int *p = nullptr; *p = 1; return 0; }')
        self.assertEqual(r["status"], "crash")

    def test_timeout(self):
        r = self._rodar('int main() { volatile int x = 0; while (true) { x++; } }', timeout=2)
        self.assertEqual(r["status"], "timeout")

    def test_erro_de_link(self):
        r = self._rodar('void naoDefinida();\nint main() { naoDefinida(); return 0; }')
        self.assertEqual(r["status"], "erro_build")
        self.assertTrue(r["erros"])


@precisa_neopz
@unittest.skipUnless(shutil.which("cmake"), "cmake não encontrado")
class TestCMakeDeVerdade(unittest.TestCase):
    def test_cmakelists_gerado_compila_e_roda_uma_receita(self):
        prefix = pipeline._neopz_prefix()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CMakeLists.txt").write_text(execucao._gerar_cmakelists("receita"))
            shutil.copy(RAIZ / "reference_solutions/task_03_poisson2d/poisson.cpp", Path(tmp) / "main.cpp")
            build = Path(tmp) / "build"
            for cmd in (["cmake", "-S", tmp, "-B", str(build),
                         f"-DNeoPZ_DIR={prefix}/lib/cmake/neopz",
                         f"-DCMAKE_CXX_COMPILER={pipeline._compilador_disponivel()}"],
                        ["cmake", "--build", str(build)]):
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-2000:])
            proc = subprocess.run([str(build / "receita")], cwd=tmp, capture_output=True, timeout=120)
            self.assertEqual(proc.returncode, 0)


class TestExecucaoNoPipeline(unittest.TestCase):
    RESPOSTA = bloco(PROGRAMA_OK)
    COMPILOU = {"status": "ok", "erros": [], "ignorados": 0}

    def _verificar(self, ligada):
        env = {"EXECUTAR_CODIGO": "1"} if ligada else {}
        with patch.dict(os.environ, env, clear=False), \
             patch.object(pipeline, "_compilar_codigo", return_value=self.COMPILOU), \
             patch.object(pipeline, "_executar_codigo",
                          return_value={"status": "ok", "saida": "ola", "arquivos": []}) as executar, \
             redirect_stdout(io.StringIO()):
            if not ligada:
                os.environ.pop("EXECUTAR_CODIGO", None)
            v = pipeline._verificar_resposta(
                self.RESPOSTA, whitelist=set(), headers_whitelist=set(), methods_whitelist=set(),
                class_header_index={}, class_methods_index={}, collisions={}, renames={},
                legacy_classes=set(), destinos=set())
        return v, executar

    def test_desligada_por_padrao(self):
        v, executar = self._verificar(ligada=False)
        executar.assert_not_called()
        self.assertEqual(v["execucao"]["status"], "nao_executada")

    def test_ligada_executa_depois_de_compilar(self):
        v, executar = self._verificar(ligada=True)
        executar.assert_called_once()
        self.assertEqual(v["execucao"]["status"], "ok")

    def test_resultado_traz_cmake_para_programa_completo(self):
        v, _ = self._verificar(ligada=False)
        self.assertIn("find_package(NeoPZ REQUIRED)", v["cmake"])


if __name__ == "__main__":
    unittest.main()
