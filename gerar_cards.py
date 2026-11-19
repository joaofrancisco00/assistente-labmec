"""
gerar_cards.py  —  gera "cards de classe" (.md compactos) a partir dos headers reais.

Para cada classe pedida, lê o header apontado em
header_index/class_header_index.json (caminho relativo a base_de_dados/neopz/)
e extrai VERBATIM as declarações públicas de métodos/construtores —
nenhum caractere da assinatura é inventado: só linhas copiadas do header,
com comentários inline removidos e continuações unidas numa linha só.

Saída: wiki_neopz/wiki/classes/<Classe>.md  (indexada por indexer_wiki.py)

Uso:

    uv run gerar_cards.py TPZElasticity3D TPZCompMeshTools ...
    uv run gerar_cards.py --todas   # todas as classes com header + índice de métodos

Determinístico e idempotente: mesma entrada → mesmo arquivo.
"""
import json
import re
import sys
from pathlib import Path

HEADER_INDEX = Path("header_index/class_header_index.json")
COLLISIONS_INDEX = Path("header_index/collisions.json")
METHODS_INDEX = Path("banco_chroma_develop/class_methods_index.json")
NEOPZ_DIR = Path("base_de_dados/neopz")
SAIDA_DIR = Path("wiki_neopz/wiki/classes")

# especificadores de acesso no corpo da classe
_RE_ACESSO = re.compile(r"^\s*(public|private|protected)\s*:")
# início da declaração: `class Nome`, `struct Nome` ou `namespace Nome`
_RE_DECL = {
    "class":     re.compile(r"\bclass\s+{nome}\b"),
    "struct":    re.compile(r"\bstruct\s+{nome}\b"),
    "namespace": re.compile(r"\bnamespace\s+{nome}\b"),
}
_RE_COMENT = re.compile(r"//.*")


def _achar_corpo(linhas: list, nome: str):
    """Localiza a declaração de `nome` e devolve (tipo, indice do '{').

    Procura class/struct/namespace nessa ordem de preferência real:
    testa cada linha por qualquer um dos três e usa a primeira ocorrência.
    """
    padroes = {k: re.compile(p.pattern.format(nome=re.escape(nome)))
               for k, p in _RE_DECL.items()}
    for i, linha in enumerate(linhas):
        if linha.lstrip().startswith("//"):
            continue
        for tipo, pat in padroes.items():
            if pat.search(linha):
                # achar o '{' que abre o corpo (pode estar linhas abaixo)
                for j in range(i, len(linhas)):
                    if "{" in linhas[j]:
                        return tipo, j
                return None, None
    return None, None


def _limpa(linha: str) -> str:
    """Remove comentário inline e normaliza espaços."""
    return _RE_COMENT.sub("", linha).strip()


def extrair_publicos(linhas: list, nome: str) -> list:
    """Extrai declarações verbatim da seção public: do corpo de `nome`.

    Se não houver seção public: (struct/namespace), usa o corpo inteiro.
    Só guarda declarações que contêm '(' (métodos e construtores).
    """
    tipo, abre = _achar_corpo(linhas, nome)
    if tipo is None:
        return []

    # 1) coleta as linhas do corpo com o acesso vigente em cada uma
    prof = 0
    acesso = "public" if tipo in ("struct", "namespace") else "private"
    corpo = []          # (acesso, linha_limpa)
    tem_public = False
    for linha in linhas[abre:]:
        # remove comentários antes de contar chaves
        limpa = _RE_COMENT.sub("", linha)
        delta = limpa.count("{") - limpa.count("}")
        if prof == 1:
            m = _RE_ACESSO.match(limpa)
            if m:
                acesso = m.group(1)
                if acesso == "public":
                    tem_public = True
            elif limpa.strip():
                if "{" in limpa:
                    # bloco (enum, corpo inline): a continuação ocorre com
                    # prof>1 e não entra no corpo. Guarda o que vem antes
                    # do '{' (pode ser a assinatura) + sentinela de flush.
                    antes = limpa.split("{")[0].strip()
                    if antes:
                        corpo.append((acesso, antes))
                    corpo.append((acesso, "\x00"))
                else:
                    corpo.append((acesso, limpa))
        prof += delta
        if prof <= 0:
            break

    corpo = [l for a, l in corpo if not tem_public or a == "public"]

    # 2) junta declarações multi-linha: acumula até ';'
    decls = []
    buf = ""
    def _flush(buf):
        """Emite as declarações de `buf` (pode haver mais de uma por linha)."""
        for parte in re.sub(r"\s+", " ", buf).split(";"):
            parte = parte.strip()
            if "(" in parte and not parte.startswith(
                    ("if", "for", "while", "switch", "return")):
                decls.append(parte)

    for linha in corpo:
        linha = linha.strip()
        if linha == "\x00":          # corpo inline/enum: a assinatura já está em buf
            _flush(buf)
            buf = ""
            continue
        if not linha or linha.startswith("#") or linha.startswith("using ") \
                or linha.startswith("typedef") or linha.startswith("friend "):
            continue
        buf = (buf + " " + linha).strip() if buf else linha
        if ";" in linha:
            _flush(buf)
            buf = ""
    _flush(buf)
    return decls


_NOTAS_CARDS = {
    "TPZVTKGenerator": [
        "`SetSolution`, `Generate`, `Write`, `Export` do NOT exist — the solution is already stored in `TPZCompMesh` after `an.Solve()`; pass `an.Mesh()` (or `cmesh`) to the constructor and call `vtk.Do()`.",
    ],
    "TPZGeoMesh": [
        "`NodeVec().PushBack`, `NodeVec().Append`, `ElementVec().PushBack`, `AddNode`, `AddElement` do NOT exist, and `CreateUniqueNodeId()` does NOT allocate a node in `NodeVec()`.",
        "To add a node: `int64_t idx = gmesh->NodeVec().AllocateNewElement(); gmesh->NodeVec()[idx].Initialize(coord, *gmesh);`.",
        "To create an element: `int64_t elIdx = -1; gmesh->CreateGeoElement(ETriangle, nodeIndices, matId, elIdx);` (4 args; 1st arg is `MElementType` such as `ETriangle` or `EQuadrilateral` from `pzeltype.h`, NEVER `TPZTriangle::ClassId()`; 4th arg is an `int64_t` variable by reference, NEVER `-1`).",
    ],
    "TPZManVector": [
        "No constructor takes 3+ element values in parentheses `TPZManVector<REAL, 3> v(x, y, z)` — use brace initializer list `TPZManVector<REAL, 3> v = {x, y, z};` or `TPZManVector<REAL, 3> v(3, 0.0);`.",
    ],
    "TPZCompMeshTools": [
        "Canonical static condensation sequence on `TPZCompMesh *cmesh`: `TPZCompMeshTools::GroupElements(cmesh); TPZCompMeshTools::CreatedCondensedElements(cmesh, true);` (or `TPZCompMeshTools::CondenseElements(cmesh, 0, true);`), then solve with `TPZLinearAnalysis an(cmesh); an.Assemble(); an.Solve();`, then `TPZCompMeshTools::UnCondensedElements(cmesh);`.",
        "`TPZLinearAnalysis::SetMaterial` and `TPZNonLinMultGridAnalysis` do NOT exist — materials belong in `cmesh->InsertMaterialObject(mat)`.",
    ],
    "TPZBndCondT": [
        "Never instantiate directly with `new TPZBndCondT` — always create via `TPZBndCondT<STATE> *bc = mat->CreateBC(mat, bcId, bcType, val1, val2);` and insert with `cmesh->InsertMaterialObject(bc);` (types: 0 = Dirichlet, 1 = Neumann, 2 = Robin/mixed).",
        "For position-dependent (non-constant) boundary conditions, call `bc->SetForcingFunctionBC(bcFunc, pOrder);` where `bcFunc` takes 3 arguments: `[](const TPZVec<REAL> &loc, TPZVec<STATE> &val, TPZFMatrix<STATE> &deriv) { val[0] = ...; }`. (`SetForcingFunction` with 2 args is for domain materials, NOT `TPZBndCondT`).",
    ],
    "TPZHDivApproxCreator": [
        "Set polynomial order with `hdivCreator.SetDefaultOrder(pOrder);` (`HdivFamily()` is a getter taking 0 args; to change family call `SetHdivFamily(HDivFamily::EHDivStandard)` with values from `TPZEnumApproxFamily.h`: `EHDivStandard`, `EHDivConstant`, `EHDivKernel`).",
    ],
    "TPZGeoMeshTools": [
        "`CreateGeoMeshOnGrid` ONLY supports `dim = 2` or `dim = 3` (calling it with `dim = 1` triggers `DebugStop()` at runtime). For 1D meshes, allocate nodes with `gmesh->NodeVec().AllocateNewElement()` and create `EOned` elements with `gmesh->CreateGeoElement(EOned, nodeIndices, matId, elIndex)`.",
    ],
    "TPZLinearAnalysis": [
        "To compute exact L2/H1 errors: call `an.SetExact(exactSol, pOrder);` (signature `void(const TPZVec<REAL> &loc, TPZVec<STATE> &u, TPZFMatrix<STATE> &gradU)`) and `TPZManVector<REAL, 3> errors(3, 0.); an.PostProcessError(errors, false);` (`ComputeErrors` does NOT exist).",
    ],
}


def _include_curto(header_rel: str) -> str:
    partes = Path(header_rel).parts
    if len(partes) >= 3 and partes[0] == "Material":
        return "/".join(partes[1:])
    return Path(header_rel).name


def _resolver_header(nome: str, index: dict, collisions: dict):
    header_rel = index.get(nome)
    if header_rel is not None:
        return header_rel
    candidatos = [
        c for c in collisions.get(nome, [])
        if "needrefactor" not in Path(c).parts and "PerfTests" not in Path(c).parts
    ]
    if len(candidatos) == 1:
        return candidatos[0]
    return None


def gerar_card(nome: str, header_rel: str) -> str:
    header_path = NEOPZ_DIR / header_rel
    texto = header_path.read_text(encoding="utf-8", errors="replace")
    # remove comentários de bloco /** ... */ antes de quebrar em linhas
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    linhas = texto.splitlines()
    decls = extrair_publicos(linhas, nome)
    inc = _include_curto(header_rel)

    out = [f"# {nome} — API card",
           "",
           f"Generated from `{header_rel}` — do not edit by hand.",
           "",
           f'Include: `"{inc}"` (in C++ code: `#include "{inc}"`)',
           "",
           "Public methods (exact declarations from the header):"]
    out += [f"- `{d}`" for d in decls] or ["- (nenhuma declaração pública encontrada)"]
    if nome in _NOTAS_CARDS:
        out += ["", "Does NOT exist (common mistakes):"]
        out += [f"- {nota}" for nota in _NOTAS_CARDS[nome]]
    return "\n".join(out) + "\n"


def main():
    args = sys.argv[1:]
    index = json.loads(HEADER_INDEX.read_text())
    collisions = json.loads(COLLISIONS_INDEX.read_text()) if COLLISIONS_INDEX.exists() else {}

    if args == ["--todas"]:
        metodos = json.loads(METHODS_INDEX.read_text())
        alvos = sorted(c for c in index if c in metodos)
        print(f"  --todas: {len(alvos)} classes com header + índice de métodos")
    elif args:
        alvos = args
    else:
        print(__doc__)
        sys.exit(1)

    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    escritos = 0
    for nome in alvos:
        header_rel = _resolver_header(nome, index, collisions)
        if header_rel is None:
            print(f"  ❌ {nome}: não está em {HEADER_INDEX}")
            continue
        if not (NEOPZ_DIR / header_rel).exists():
            print(f"  ❌ {nome}: header não encontrado: {NEOPZ_DIR / header_rel}")
            continue
        card = gerar_card(nome, header_rel)
        (SAIDA_DIR / f"{nome}.md").write_text(card, encoding="utf-8")
        escritos += 1
        print(f"  ✍️  {nome}.md  ({card.count(chr(10)) - 8} declarações, de {header_rel})")

    print(f"\n✅ {escritos} cards escritos em {SAIDA_DIR}/")
    print("   Rode `uv run indexer_wiki.py` para reindexar a wiki.")


if __name__ == "__main__":
    main()
