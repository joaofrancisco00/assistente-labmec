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

from pipeline.cpp_parser import (
    build_class_whitelist,
    build_inheritance_index,
    build_tiered_class_whitelist,
    extract_classes_from_header,
    find_suspicious_method_calls,
    find_tpz_classes_in_code,
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
        nomes = [m["name"] for m in chunks[0].methods]
        self.assertIn("SetExact", nomes)
        self.assertIn("Run", nomes)

    def test_asterisco_colado_no_nome(self):
        # Estilo dominante no NeoPZ: `TPZGeoMesh *Metodo(...)` — com o
        # separador antigo (\s+) o método ficava invisível à whitelist
        chunks = _parse("""
namespace TPZGeoMeshTools {
    TPZGeoMesh *CreateGeoMeshOnGrid(int dim, REAL minX, REAL maxX);
}
""")
        self.assertEqual(chunks[0].class_name, "TPZGeoMeshTools")
        nomes = [m["name"] for m in chunks[0].methods]
        self.assertIn("CreateGeoMeshOnGrid", nomes)

    def test_referencia_colada_no_nome(self):
        # Mesmo bug do asterisco, com retorno por referência (`&Solution()`)
        chunks = _parse("""
class TPZAnalysis {
public:
    TPZFMatrix<STATE> &Solution();
};
""")
        nomes = [m["name"] for m in chunks[0].methods]
        self.assertIn("Solution", nomes)


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


class TestWhitelistDoisNiveis(unittest.TestCase):
    def test_classe_so_do_legado_e_separada(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "Material").mkdir()
            (base / "Material" / "novo.h").write_text(
                "class TPZMatPoisson { public: void Contribute(); };\n"
                "class TPZCompartilhada;\n", encoding="utf-8")
            legado = base / "Material" / "needrefactor"
            legado.mkdir()
            (legado / "velho.h").write_text(
                "class TPZMatVelha { public: void Foo(); };\n"
                "class TPZCompartilhada { public: void Bar(); };\n", encoding="utf-8")
            todas, apenas_legado = build_tiered_class_whitelist(base)

        # Classe do legado EXISTE (não pode virar falso positivo de alucinação)
        self.assertIn("TPZMatVelha", todas)
        self.assertIn("TPZMatPoisson", todas)
        # Só quem vive EXCLUSIVAMENTE no legado entra no segundo nível;
        # quem aparece nos dois lados fica de fora (menos aviso = lado seguro)
        self.assertEqual(apenas_legado, {"TPZMatVelha"})


class TestChamadasSuspeitas(unittest.TestCase):
    METODOS = {"Print", "NNodes", "CreateGeoMeshOnGrid"}
    CLASSES = {"TPZGeoMesh", "TPZGeoMeshTools"}

    def test_declaracao_nua_vincula_variavel(self):
        # Regressão: `TPZGeoMesh mesh;` não vinculava a variável a nada e
        # qualquer método inventado chamado nela passava batido
        codigo = "TPZGeoMesh mesh;\nmesh.GenerateMesh();\nmesh.Print();"
        suspeitos_nome, _ = find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES)
        self.assertIn(("TPZGeoMesh", "GenerateMesh"), suspeitos_nome)
        self.assertNotIn(("TPZGeoMesh", "Print"), suspeitos_nome)

    def test_stl_nao_e_sinalizada(self):
        # vetor.push_back() não é NeoPZ — não deve virar falso positivo
        codigo = "std::vector<int> v;\nv.push_back(1);"
        suspeitos_nome, suspeitos_aridade = find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES)
        self.assertEqual(suspeitos_nome, [])
        self.assertEqual(suspeitos_aridade, [])

    def test_chamada_qualificada(self):
        codigo = ("TPZGeoMeshTools::CreateRectMesh(2);\n"
                  "TPZGeoMeshTools::CreateGeoMeshOnGrid(2);")
        suspeitos_nome, _ = find_suspicious_method_calls(codigo, self.METODOS, self.CLASSES)
        self.assertIn(("TPZGeoMeshTools", "CreateRectMesh"), suspeitos_nome)
        self.assertNotIn(("TPZGeoMeshTools", "CreateGeoMeshOnGrid"), suspeitos_nome)


class TestIndiceDeHeranca(unittest.TestCase):
    def test_header_com_multiplas_bases(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "teste.h").write_text(
                "class TPZF : public TPZA, public TPZB {\npublic:\n    void Foo();\n};\n"
                "class TPZG : private NS::TPZH<STATE> {\npublic:\n    void Bar();\n};\n"
                "class TPZSemBase { public: void Baz(); };\n",
                encoding="utf-8")
            indice = build_inheritance_index(Path(tmp))
        self.assertEqual(indice.get("TPZF"), ["TPZA", "TPZB"])
        # template e namespace são resolvidos: TPZH<STATE> / NS::TPZH → TPZH
        self.assertEqual(indice.get("TPZG"), ["TPZH"])
        self.assertNotIn("TPZSemBase", indice)


class TestMetodoContraHierarquia(unittest.TestCase):
    METODOS = {"SetX", "SetX2", "SetY"}
    CLASSES = {"TPZFilho", "TPZPai", "TPZTerceiro"}
    INDICE_METODOS = {"TPZFilho": {"SetX": {"min_args": 1, "max_args": 1}},
                      "TPZPai": {"SetX2": {"min_args": 1, "max_args": 1}},
                      "TPZTerceiro": {"SetY": {"min_args": 1, "max_args": 1}}}
    HERANCA = {"TPZFilho": ["TPZPai"]}

    def test_metodo_herdado_do_pai_e_aceito(self):
        codigo = "TPZFilho *f = nullptr;\nf->SetX2(1);\nf->SetX(1);"
        suspeitos, _ = find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES, self.INDICE_METODOS, self.HERANCA)
        self.assertEqual(suspeitos, [])

    def test_metodo_de_terceira_classe_e_sinalizado(self):
        codigo = "TPZFilho *f = nullptr;\nf->SetY(1);"
        suspeitos, _ = find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES, self.INDICE_METODOS, self.HERANCA)
        self.assertIn(("TPZFilho", "SetY"), suspeitos)

    def test_sem_indice_de_heranca_comportamento_antigo(self):
        # método existe na whitelist global mas não na classe — sem o índice
        # de herança passa batido, como antes
        codigo = "TPZFilho *f = nullptr;\nf->SetY(1);"
        suspeitos, _ = find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES, self.INDICE_METODOS)
        self.assertEqual(suspeitos, [])


class TestAssinaturaNoErroDeAridade(unittest.TestCase):
    CODIGO = "TPZFoo *f = nullptr;\nf->Bar(1, 2);\n"
    METODOS = {"Bar"}
    CLASSES = {"TPZFoo"}

    def test_indice_com_sigs_anexa_assinatura(self):
        indice = {"TPZFoo": {"Bar": {
            "min_args": 3, "max_args": 3,
            "sigs": ["Bar(int a, int b = 0, int c = 0)"]}}}
        _, aridade = find_suspicious_method_calls(
            self.CODIGO, self.METODOS, self.CLASSES, indice)
        self.assertEqual(len(aridade), 1)
        self.assertIn("expects exactly 3 argument(s), but got 2", aridade[0])
        self.assertIn("Signature: Bar(int a, int b = 0, int c = 0)", aridade[0])

    def test_indice_legado_sem_sigs_mantem_msg_antiga(self):
        indice = {"TPZFoo": {"Bar": {"min_args": 3, "max_args": 3}}}
        _, aridade = find_suspicious_method_calls(
            self.CODIGO, self.METODOS, self.CLASSES, indice)
        self.assertEqual(
            aridade,
            ["TPZFoo::Bar expects exactly 3 argument(s), but got 2."])

    def test_overloads_listam_as_assinaturas(self):
        indice = {"TPZFoo": {"Bar": {
            "min_args": 1, "max_args": 3,
            "sigs": ["Bar(int a)", "Bar(int a, TPZGeoMesh *g, int d = 0)"]}}}
        codigo = "TPZFoo *f = nullptr;\nf->Bar(1, 2, 3, 4);\n"
        _, aridade = find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES, indice)
        self.assertEqual(len(aridade), 1)
        self.assertIn("Signatures: Bar(int a) | Bar(int a, TPZGeoMesh *g, int d = 0)",
                      aridade[0])


class TestAridadeConstrutores(unittest.TestCase):
    """Caso real do benchmark: TPZManVector<REAL,3> v(1., 2., 3.) só era
    recusado pelo g++ — o construtor mora no índice sob o nome da própria
    classe e a aridade da chamada pode ser comparada antes do retry."""
    METODOS = {"Print"}
    CLASSES = {"TPZManVector", "TPZElasticity2D", "TPZGeoMesh", "TPZGeoQuad"}
    INDICE = {
        "TPZManVector": {"TPZManVector": {
            "min_args": 0, "max_args": 2,
            "sigs": ["TPZManVector(const int64_t size = 0)",
                     "TPZManVector(const int64_t size, const T& copy)"]}},
        "TPZElasticity2D": {"TPZElasticity2D": {"min_args": 1, "max_args": 6}},
        "TPZGeoMesh": {"TPZGeoMesh": {"min_args": 0, "max_args": 0}},
    }

    def _aridade(self, codigo, indice=None):
        _, aridade = find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES,
            self.INDICE if indice is None else indice)
        return aridade

    def test_ctor_stack_com_args_a_mais_e_flagado(self):
        aridade = self._aridade("TPZManVector<REAL,3> v(1., 2., 3.);")
        self.assertEqual(len(aridade), 1)
        self.assertIn("TPZManVector::TPZManVector", aridade[0])
        self.assertIn("got 3", aridade[0])
        self.assertIn("TPZManVector(const int64_t size, const T& copy)", aridade[0])

    def test_ctor_stack_com_args_validos_passa(self):
        self.assertEqual(self._aridade("TPZManVector<REAL,3> v(3, 0.);"), [])

    def test_ctor_new_dentro_da_faixa_passa(self):
        codigo = "auto *mat = new TPZElasticity2D(1, 1000., 0.3, 0., 0., 1);"
        self.assertEqual(self._aridade(codigo), [])

    def test_ctor_new_com_args_a_mais_e_flagado(self):
        codigo = "auto *mat = new TPZElasticity2D(1, 1000., 0.3, 0., 0., 1, 7);"
        self.assertEqual(len(self._aridade(codigo)), 1)

    def test_definicao_de_funcao_nao_e_ctor(self):
        # TPZGeoMesh CriarMalha(int n) { é função retornando a classe por
        # valor — o '(' dela não é chamada de construtor (e aqui min=max=0
        # faria QUALQUER arg flagar, se o skip falhasse)
        codigo = "TPZGeoMesh CriarMalha(int n) {\n    return TPZGeoMesh();\n}"
        self.assertEqual(self._aridade(codigo), [])

    def test_classe_fora_da_whitelist_nao_e_checada(self):
        codigo = "TPZFooInexistente v(1, 2, 3);"
        self.assertEqual(self._aridade(codigo), [])

    def test_classe_sem_construtor_no_indice_passa(self):
        indice = {"TPZGeoMesh": {"Print": {"min_args": 0, "max_args": 1}}}
        self.assertEqual(self._aridade("TPZGeoMesh g(1, 2, 3);", indice), [])

    def test_ctor_qualificado_com_args_a_mais_e_flagado(self):
        # Forma que a correção automática de namespaces escreve:
        # `pzgeom::TPZGeoQuad q(...)` — o ':' no lookbehind não pode blindar
        indice = {"TPZGeoQuad": {"TPZGeoQuad": {"min_args": 0, "max_args": 3}}}
        aridade = self._aridade("pzgeom::TPZGeoQuad q(1, 2, 3, 4, 5);", indice)
        self.assertEqual(len(aridade), 1)
        self.assertIn("TPZGeoQuad::TPZGeoQuad", aridade[0])
        self.assertIn("got 5", aridade[0])

    def test_ctor_qualificado_com_args_validos_passa(self):
        indice = {"TPZGeoQuad": {"TPZGeoQuad": {"min_args": 0, "max_args": 3}}}
        self.assertEqual(
            self._aridade("pzgeom::TPZGeoQuad q(nodes, 1, gmesh);", indice), [])


class TestVariaveisAmbiguas(unittest.TestCase):
    """Caso real do benchmark: no esqueleto modular o mesmo nome `cmesh` é
    ligado a TPZCompMesh numa função e a TPZMultiphysicsCompMesh em outra —
    o primeiro binding ganhava e `cmesh->BuildMultiphysicsSpace` flagava um
    código correto. Com vários candidatos, só reporta se TODOS reprovam."""
    CLASSES = {"TPZCompMesh", "TPZMultiphysicsCompMesh"}
    METODOS = {"AutoBuild", "BuildMultiphysicsSpace", "DoIt"}
    INDICE = {
        "TPZCompMesh": {"AutoBuild": {"min_args": 0, "max_args": 0},
                        "DoIt": {"min_args": 3, "max_args": 3}},
        "TPZMultiphysicsCompMesh": {"BuildMultiphysicsSpace": {"min_args": 2, "max_args": 2},
                                    "DoIt": {"min_args": 2, "max_args": 2}},
    }
    CODIGO = (
        "TPZCompMesh *CreateFluxMesh(TPZGeoMesh *gmesh) {\n"
        "    auto *cmesh = new TPZCompMesh(gmesh);\n"
        "    cmesh->AutoBuild();\n"
        "    return cmesh;\n"
        "}\n"
        "TPZMultiphysicsCompMesh *CreateMulti(TPZGeoMesh *gmesh, TPZCompMesh *f, TPZCompMesh *p) {\n"
        "    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);\n"
        "    TPZManVector<TPZCompMesh *, 2> meshes = {f, p};\n"
        "    TPZManVector<int, 2> active = {1, 1};\n"
        "    cmesh->BuildMultiphysicsSpace(active, meshes);\n"
        "    return cmesh;\n"
        "}\n")

    # herança real: TPZMultiphysicsCompMesh é TPZCompMesh — com ela, um bind
    # único para TPZCompMesh flagaria BuildMultiphysicsSpace (foi o falso
    # positivo do benchmark); a lista de candidatos é o que absolve
    HERANCA = {"TPZMultiphysicsCompMesh": ["TPZCompMesh"]}

    def _chamadas(self, codigo):
        return find_suspicious_method_calls(
            codigo, self.METODOS, self.CLASSES, self.INDICE, self.HERANCA)

    def test_metodo_aceito_por_um_dos_candidatos_passa(self):
        suspeitos_nome, aridade = self._chamadas(self.CODIGO)
        self.assertEqual(suspeitos_nome, [])
        self.assertEqual(aridade, [])

    def test_metodo_inventado_flaga_uma_vez(self):
        codigo = self.CODIGO + "    cmesh->MetodoInventado();\n"
        suspeitos_nome, _ = self._chamadas(codigo)
        self.assertEqual(suspeitos_nome, [("TPZCompMesh", "MetodoInventado")])

    def test_aridade_aceita_por_um_candidato_passa(self):
        # DoIt existe nos dois com aridades diferentes: a chamada só bate
        # com TPZMultiphysicsCompMesh → ambiguidade resolve a favor
        codigo = self.CODIGO + "    cmesh->DoIt(1, 2);\n"
        _, aridade = self._chamadas(codigo)
        self.assertEqual(aridade, [])


class TestClassesEmComentarios(unittest.TestCase):
    def test_classe_em_comentario_nao_conta(self):
        # Regressão real: a receita de elasticidade 3D cita TPZElasticity2D num
        # comentário; o auto-include adicionava o header da classe comentada e
        # a regra semântica do 2D reprovava um código correto
        codigo = ("auto *m = new TPZElasticity3D(1, E, nu, f); // not TPZElasticity2D\n"
                  "/* TPZMatLaplacian */")
        self.assertEqual(find_tpz_classes_in_code(codigo), {"TPZElasticity3D"})

    def test_url_dentro_de_string_nao_vira_comentario(self):
        codigo = 'const char *url = "http://exemplo.com/TPZDoc";  // TPZFoo\nTPZBar *b;'
        self.assertEqual(find_tpz_classes_in_code(codigo),
                         {"TPZDoc", "TPZBar"})


if __name__ == "__main__":
    unittest.main()
