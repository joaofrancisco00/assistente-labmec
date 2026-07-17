"""
Testes de regressão do cpp_parser.

Cada caso aqui corresponde a um bug que já aconteceu de verdade (documentado
nos comentários do próprio cpp_parser.py) — se um regex for ajustado no
futuro, estes testes garantem que os bugs antigos não voltam.

Rodar:  python3 -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cpp_parser import (
    build_class_whitelist,
    extract_classes_from_header,
    find_suspicious_method_calls,
)


def _parse(texto: str):
    """Escreve um header temporário e parseia."""
    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / "teste.h"
        arquivo.write_text(texto, encoding="utf-8")
        return extract_classes_from_header(arquivo)


def _whitelist(texto: str):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "teste.h").write_text(texto, encoding="utf-8")
        return build_class_whitelist(Path(tmp))


class TestExtracaoDeMetodos(unittest.TestCase):
    def test_std_function_com_parenteses_aninhados(self):
        # Regressão: SetExact ficava fora da whitelist porque o regex antigo
        # parava no primeiro ')' de dentro do std::function
        chunks = _parse("""
class TPZAnalysis {
public:
    void SetExact(std::function<void (const TPZVec<REAL> &loc, TPZVec<STATE> &result)> f, int pOrder = 1);
    void Run();
};
""")
        self.assertEqual(len(chunks), 1)
        self.assertIn("SetExact", chunks[0].methods)
        self.assertIn("Run", chunks[0].methods)

    def test_asterisco_colado_no_nome(self):
        # Estilo dominante no NeoPZ: `TPZGeoMesh *Metodo(...)` — com o
        # separador antigo (\s+) o método ficava invisível à whitelist
        chunks = _parse("""
namespace TPZGeoMeshTools {
    TPZGeoMesh *CreateGeoMeshOnGrid(int dim, REAL minX, REAL maxX);
}
""")
        self.assertEqual(chunks[0].class_name, "TPZGeoMeshTools")
        self.assertIn("CreateGeoMeshOnGrid", chunks[0].methods)

    def test_referencia_colada_no_nome(self):
        # Mesmo bug do asterisco, com retorno por referência (`&Solution()`)
        chunks = _parse("""
class TPZAnalysis {
public:
    TPZFMatrix<STATE> &Solution();
};
""")
        self.assertIn("Solution", chunks[0].methods)


class TestWhitelistDeClasses(unittest.TestCase):
    def test_declaracoes_alem_de_class_struct(self):
        # Regressão: nomes TPZ declarados via namespace/using/typedef/enum
        # eram tratados como inexistentes (bug do TPZGeoMeshTools)
        nomes = _whitelist("""
class TPZReal { public: void Print(); };
class TPZForward;
namespace TPZTools { void Foo(); }
using TPZAlias = TPZReal;
typedef TPZReal TPZVelho;
enum TPZCores { ECor1, ECor2 };
""")
        for esperado in ("TPZReal", "TPZForward", "TPZTools",
                         "TPZAlias", "TPZVelho", "TPZCores"):
            self.assertIn(esperado, nomes)


class TestChamadasSuspeitas(unittest.TestCase):
    METODOS = {"Print", "NNodes", "CreateGeoMeshOnGrid"}
    CLASSES = {"TPZGeoMesh", "TPZGeoMeshTools"}

    def test_declaracao_nua_vincula_variavel(self):
        # Regressão: `TPZGeoMesh mesh;` não vinculava a variável a nada e
        # qualquer método inventado chamado nela passava batido
        codigo = "TPZGeoMesh mesh;\nmesh.GenerateMesh();\nmesh.Print();"
        suspeitos = find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES)
        self.assertIn(("TPZGeoMesh", "GenerateMesh"), suspeitos)
        self.assertNotIn(("TPZGeoMesh", "Print"), suspeitos)

    def test_stl_nao_e_sinalizada(self):
        # vetor.push_back() não é NeoPZ — não deve virar falso positivo
        codigo = "std::vector<int> v;\nv.push_back(1);"
        self.assertEqual(
            find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES), [])

    def test_chamada_qualificada(self):
        codigo = ("TPZGeoMeshTools::CreateRectMesh(2);\n"
                  "TPZGeoMeshTools::CreateGeoMeshOnGrid(2);")
        suspeitos = find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES)
        self.assertIn(("TPZGeoMeshTools", "CreateRectMesh"), suspeitos)
        self.assertNotIn(("TPZGeoMeshTools", "CreateGeoMeshOnGrid"), suspeitos)


if __name__ == "__main__":
    unittest.main()
