"""
Parser inteligente para headers C++ do NeoPZ.
Extrai declarações de classe completas em vez de cortar aleatoriamente.
"""
import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ClassChunk:
    class_name: str
    file_path: str
    content: str
    methods: list = field(default_factory=list)

    def to_text(self) -> str:
        """Formata o chunk para indexação."""
        lines = [
            f"// === CLASSE: {self.class_name} ===",
            f"// Arquivo: {self.file_path}",
        ]
        if self.methods:
            lines.append(f"// Métodos públicos: {', '.join(self.methods[:10])}")
        lines.append("")
        lines.append(self.content)
        return "\n".join(lines)


# ── Funções auxiliares de parsing ─────────────────────────────────────────────

def _find_matching_brace(text: str, start: int) -> int:
    """Encontra a chave de fechamento correspondente à abertura em `start`."""
    depth = 0
    i = start
    in_line_comment = False
    in_block_comment = False
    in_string = False

    while i < len(text):
        c = text[i]
        nc = text[i + 1] if i + 1 < len(text) else ''

        if in_line_comment:
            if c == '\n':
                in_line_comment = False
        elif in_block_comment:
            if c == '*' and nc == '/':
                in_block_comment = False
                i += 1
        elif in_string:
            if c == '"' and (i == 0 or text[i - 1] != '\\'):
                in_string = False
        elif c == '/' and nc == '/':
            in_line_comment = True
        elif c == '/' and nc == '*':
            in_block_comment = True
        elif c == '"':
            in_string = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return len(text) - 1


def _extract_public_section(header_line: str, body: str) -> str:
    """Extrai apenas a seção pública da classe."""
    parts = re.split(r'\n\s*(public|protected|private)\s*:', body)

    public_parts = []
    current = "private"  # padrão C++ para `class`

    for part in parts:
        stripped = part.strip()
        if stripped in ('public', 'protected', 'private'):
            current = stripped
        elif current == 'public' and stripped:
            public_parts.append(stripped)

    if public_parts:
        content = '\n'.join(public_parts)
        return f"{header_line} {{\npublic:\n{content}\n}};"

    # struct é público por padrão — retorna o corpo direto
    return f"{header_line} {{\n{body[:1200]}\n}};"


_METHOD_BLACKLIST = {'if', 'while', 'for', 'switch', 'return', 'else', 'do',
                     'template', 'typename', 'decltype', 'sizeof', 'operator'}

# Só encontra o INÍCIO de uma possível declaração de método (prefixo de tipo +
# nome + '('). O que vem depois do '(' é resolvido por _scan_matching_paren,
# não por regex — parâmetros do tipo std::function<void(...)> têm parênteses
# ANINHADOS, e um regex ingênuo tipo `\([^;{)]*\)` (que para no primeiro ')')
# corta a assinatura no meio e perde o método inteiro. Isso já aconteceu de
# verdade aqui: `SetExact(std::function<void (...)> f, int pOrder=1)` ficava
# invisível à whitelist com o regex antigo, e SetExact é usado no tutorial
# mais básico do NeoPZ — teria virado outro falso positivo de alucinação.
_METHOD_NAME_START_RE = re.compile(
    r'(?:virtual\s+|static\s+|explicit\s+|inline\s+)*'
    r'[\w:<>*&\s,~]+\s+(~?[a-zA-Z]\w*)\s*\(',
    re.MULTILINE
)


def _scan_matching_paren(text: str, open_pos: int) -> int:
    """Encontra o ')' que fecha o '(' em open_pos, respeitando aninhamento
    (necessário para assinaturas com std::function<...>, ponteiros de função,
    etc, que têm parênteses dentro dos parênteses dos parâmetros)."""
    depth = 0
    i = open_pos
    n = len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            if c == '"' and text[i - 1] != '\\':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# O que pode vir logo depois do ')' de uma declaração de método real:
# 'const', 'override', '= 0' (pura virtual), e então ';' (declaração pura) ou
# '{' (definida inline no header, comum em getters/setters simples do NeoPZ).
_METHOD_TAIL_RE = re.compile(r'\s*(?:const\s*)?(?:override\s*)?(?:=\s*0\s*)?[;{]')


def _extract_method_names(content: str) -> list:
    """Extrai nomes de métodos (declarações puras + definidas inline no header),
    com parênteses de parâmetros corretamente balanceados (ver _scan_matching_paren)."""
    names = []
    for m in _METHOD_NAME_START_RE.finditer(content):
        name = m.group(1).strip()
        if not name or name in _METHOD_BLACKLIST or name[0].isdigit():
            continue
        paren_open = m.end() - 1  # último char do match é sempre o '(' literal
        paren_close = _scan_matching_paren(content, paren_open)
        if paren_close == -1:
            continue
        tail = content[paren_close + 1:paren_close + 60]
        if not _METHOD_TAIL_RE.match(tail):
            continue
        names.append(name)
    return list(dict.fromkeys(names))  # mantém ordem, sem duplicatas


# ── Declarações que NÃO são class/struct (mesmo bug, escopo maior) ──────────────
#
# O NeoPZ também expõe API pública via `namespace TPZxxx { ... }` (ex:
# TPZGeoMeshTools::CreateGeoMeshOnGrid, a forma padrão de criar uma malha —
# literalmente o primeiro passo de qualquer tutorial), além de `using X = ...`,
# `typedef ... X;` e `enum (class) X`. Um regex que só reconhece class/struct
# trata todos esses nomes reais como inexistentes.

_NAMESPACE_DECL_RE = re.compile(r'\bnamespace\s+(TPZ\w+)\s*\{')
_USING_ALIAS_TPZ_RE = re.compile(r'\busing\s+(TPZ\w+)\s*=')
_TYPEDEF_TPZ_RE = re.compile(r'\btypedef\b[^;{}]*?\b(TPZ\w+)\s*;')
_ENUM_TPZ_RE = re.compile(r'\benum(?:\s+class)?\s+(TPZ\w+)\b')


def _find_extra_tpz_declarations(content: str) -> set:
    """Nomes TPZxxx declarados via namespace/using/typedef/enum (não class/struct)."""
    names = set()
    names.update(_NAMESPACE_DECL_RE.findall(content))
    names.update(_USING_ALIAS_TPZ_RE.findall(content))
    names.update(_TYPEDEF_TPZ_RE.findall(content))
    names.update(_ENUM_TPZ_RE.findall(content))
    return names


def _extract_simple_tpz_declarations(content: str, filepath: Path) -> list:
    """
    Gera ClassChunk leves para using/typedef/enum com prefixo TPZ — não têm
    corpo de classe (using/typedef nunca têm; enum às vezes tem um bloco de
    valores), então não passam pela lógica de seção pública/protegida/privada,
    só pegam a própria linha/bloco da declaração como conteúdo.
    """
    chunks = []
    seen = set()

    for m in re.finditer(r'(?:^|\n)[ \t]*using\s+TPZ\w+\s*=[^;]+;', content, re.MULTILINE):
        name_m = _USING_ALIAS_TPZ_RE.search(m.group(0))
        if not name_m or name_m.group(1) in seen:
            continue
        seen.add(name_m.group(1))
        chunks.append(ClassChunk(class_name=name_m.group(1), file_path=str(filepath),
                                  content=m.group(0).strip(), methods=[]))

    for m in re.finditer(r'(?:^|\n)[ \t]*typedef\b[^;{}]*;', content, re.MULTILINE):
        name_m = _TYPEDEF_TPZ_RE.search(m.group(0))
        if not name_m or name_m.group(1) in seen:
            continue
        seen.add(name_m.group(1))
        chunks.append(ClassChunk(class_name=name_m.group(1), file_path=str(filepath),
                                  content=m.group(0).strip(), methods=[]))

    for m in re.finditer(r'\benum(?:\s+class)?\s+TPZ\w+\b', content):
        name_m = _ENUM_TPZ_RE.search(m.group(0))
        if not name_m or name_m.group(1) in seen:
            continue
        brace_pos = content.find('{', m.start())
        semi_pos = content.find(';', m.start())
        if brace_pos != -1 and (semi_pos == -1 or brace_pos < semi_pos):
            end_pos = _find_matching_brace(content, brace_pos)
            text = content[m.start():end_pos + 1].strip() + ";"
        elif semi_pos != -1:
            text = content[m.start():semi_pos + 1].strip()
        else:
            continue
        seen.add(name_m.group(1))
        chunks.append(ClassChunk(class_name=name_m.group(1), file_path=str(filepath),
                                  content=text, methods=[]))

    return chunks


# ── API pública ────────────────────────────────────────────────────────────────

def extract_classes_from_header(filepath: Path) -> list:
    """
    Extrai todas as declarações TPZxxx de um arquivo .h — classes, structs,
    namespaces (ex: TPZGeoMeshTools), e também using/typedef/enum (via
    _extract_simple_tpz_declarations). Retorna uma lista de ClassChunk — um
    por declaração encontrada.
    """
    try:
        content = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    # Encontra declarações de classe/struct/namespace com prefixo TPZ.
    # namespace entra aqui (não em _extract_simple_tpz_declarations) porque,
    # como class/struct, tem um corpo com chaves que vale a pena extrair
    # (ex: as assinaturas de função dentro de `namespace TPZGeoMeshTools {}`).
    class_pattern = re.compile(
        r'(?:^|\n)[ \t]*(?:template\s*<[^>]*>\s*)?'
        r'((class|struct|namespace)\s+(TPZ\w+)[^{;]*)',
        re.MULTILINE
    )

    chunks = []
    for match in class_pattern.finditer(content):
        header_line = match.group(1).strip()
        kind = match.group(2)
        class_name = match.group(3)

        # Encontra a chave de abertura
        brace_pos = content.find('{', match.start())
        if brace_pos == -1:
            continue

        # Ignora forward declarations (tem ';' entre a declaração e '{')
        if ';' in content[match.end():brace_pos]:
            continue

        end_pos = _find_matching_brace(content, brace_pos)
        body = content[brace_pos + 1:end_pos]

        if kind == "namespace":
            # namespace não tem public:/private: — indexa o corpo direto
            clean_body = body.strip()
            if len(clean_body) > 2500:
                clean_body = clean_body[:2500] + "\n    // ... (truncado)"
            clean = f"{header_line} {{\n{clean_body}\n}}"
        else:
            clean = _extract_public_section(header_line, body)
            if len(clean) > 2500:
                clean = clean[:2500] + "\n    // ... (truncado)"

        methods = _extract_method_names(body)

        chunks.append(ClassChunk(
            class_name=class_name,
            file_path=str(filepath),
            content=clean,
            methods=methods  # lista completa; to_text() trunca só para exibição
        ))

    chunks.extend(_extract_simple_tpz_declarations(content, filepath))

    return chunks


def build_class_whitelist(base_path: Path) -> set:
    """
    Varre todos os .h e retorna o conjunto de nomes TPZ reais — classes,
    structs, namespaces (ex: TPZGeoMeshTools), aliases `using`/`typedef` e
    enums. Usado pelo indexer para criar a whitelist de validação.
    """
    classes = set()
    for h_file in base_path.rglob("*.h"):
        try:
            content = h_file.read_text(encoding='utf-8', errors='replace')
            found = re.findall(r'\b(?:class|struct)\s+(TPZ\w+)', content)
            classes.update(found)
            classes.update(_find_extra_tpz_declarations(content))
        except Exception:
            pass
    return classes


def build_header_whitelist(base_path: Path) -> set:
    """
    Varre todos os .h e retorna o conjunto de nomes de headers reais.
    Ex: {'pzcmesh.h', 'pzgmesh.h', 'TPZLinearAnalysis.h', ...}
    Usado pelo indexer para criar a whitelist de validação de #include.
    """
    headers = set()
    for h_file in base_path.rglob("*.h"):
        headers.add(h_file.name)
    return headers


def find_tpz_classes_in_code(code: str) -> set:
    """Extrai todos os identificadores TPZxxx usados em um trecho de código."""
    return set(re.findall(r'\bTPZ[A-Z]\w+', code))


# ── Validação de MÉTODOS (não só classe/header) ─────────────────────────────────
#
# Até aqui, só o NOME da classe e do header eram validados — um método
# inventado numa classe real (ex: `gmesh->SetBoundaryTypeFancy(1)`, sendo
# TPZGeoMesh uma classe real) passava batido: a classe existe, o header
# existe, "✅ validado". Na prática, inventar um método de uma classe real é
# um jeito bem mais comum de alucinar do que inventar a classe inteira.
#
# Escolha de design: whitelist GLOBAL de métodos (não por classe). Fazer a
# checagem por classe exigiria inferir herança (o NeoPZ tem hierarquias
# profundas e com múltipla herança/templates) — arriscado demais de acertar só
# com regex, e um falso positivo aqui é pior que não checar nada (é
# literalmente o que já aconteceu com o bug do namespace: o guard-rail
# empurrando o modelo para longe do código certo). Uma whitelist global pega o
# caso mais danoso (método que não existe em NENHUM lugar do NeoPZ) sem correr
# esse risco.


def build_method_whitelist(base_path: Path) -> set:
    """
    Varre todos os .h e retorna o conjunto de nomes de método/função
    encontrados dentro de qualquer classe/struct/namespace (via
    extract_classes_from_header, que já lida com corpo completo, inline vs.
    declaração pura, etc). Usado pelo indexer para a whitelist de métodos.
    """
    methods = set()
    for h_file in base_path.rglob("*.h"):
        for chunk in extract_classes_from_header(h_file):
            methods.update(chunk.methods)
    return methods


def build_class_methods_index(base_path: Path) -> dict:
    """
    {classe: [metodos]} — mesma fonte de build_method_whitelist, mas SEM
    achatar tudo num set global.

    Por que isso existe além da whitelist global: para DETECTAR alucinação,
    global é mais seguro (ver nota acima). Mas para CORRIGIR automaticamente
    (reescrever o texto por um nome "parecido"), global é perigoso demais —
    a whitelist global tem ~3900 nomes curtos e genéricos (Create*, Get*,
    Set*, Add*...) repetidos de forma parecida em dezenas de classes
    diferentes. Isso já causou uma correção automática ERRADA de verdade:
    'TPZGeoMeshTools::CreateRectMesh' (inventado) virou
    'TPZGeoMeshTools::CreateMesh' (nome de OUTRA classe, por coincidência de
    string) em vez do método real 'CreateGeoMeshOnGrid'. Restringir a busca
    por correspondência aos métodos que aparecem REALMENTE naquela classe
    específica evita essa contaminação cruzada.

    Retorna apenas os métodos vistos diretamente na declaração da classe
    (não resolve herança) — por isso é usado só para tentar uma correção
    automática de alta confiança; se a classe não estiver aqui ou não houver
    candidato bom o bastante, a chamada some sem substituição, e continua
    marcada como suspeita para revisão/instrução no prompt.
    """
    index: dict = {}
    for h_file in base_path.rglob("*.h"):
        for chunk in extract_classes_from_header(h_file):
            if not chunk.methods:
                continue
            existentes = index.setdefault(chunk.class_name, [])
            for m in chunk.methods:
                if m not in existentes:
                    existentes.append(m)
    return index


# Vincula variável -> classe TPZ, para restringir a checagem de método a
# chamadas em objetos que a gente tem confiança razoável de que são de fato
# instâncias TPZ (evita marcar chamadas de STL/C++ padrão como suspeitas,
# ex: vetor.push_back(), que nunca estariam numa whitelist do NeoPZ).
_BIND_AUTOPOINTER_RE = re.compile(r'\bTPZAutoPointer\s*<\s*(TPZ\w+)\s*>\s*[\*&]?\s*(\w+)\b')
_BIND_POINTER_REF_RE = re.compile(r'\b(TPZ\w+)\s*[\*&]\s*(\w+)\s*(?:[=;]|\()')
_BIND_STACK_VALUE_RE = re.compile(r'\b(TPZ\w+)\s+(\w+)\s*\(')
# Declaração "nua" com construtor padrão, sem parênteses nem args (ex:
# `TPZGeoMesh mesh;`) — faltava esse caso: sem ele, uma variável declarada
# assim nunca é vinculada a nenhuma classe, e QUALQUER método chamado nela
# (real ou inventado) passa batido pela validação, sem nenhum aviso. Já
# aconteceu de verdade: `mesh.SetType(...)`, `mesh.AddVertex(...)`,
# `mesh.GenerateMesh()` (tudo inventado) não foram sinalizados por causa
# desse buraco.
_BIND_BARE_VALUE_RE = re.compile(r'\b(TPZ\w+)\s+(\w+)\s*;')
_BIND_AUTO_NEW_RE = re.compile(r'\bauto\s*[\*&]?\s*(\w+)\s*=\s*new\s+(TPZ\w+)\s*[\(<]')

_METHOD_CALL_RE = re.compile(r'\b(\w+)\s*(?:->|\.)\s*([A-Za-z_]\w*)\s*\(')
_QUALIFIED_CALL_RE = re.compile(r'\b(TPZ\w+)::([A-Za-z_]\w*)\s*\(')


def _bind_variables_to_classes(code: str) -> dict:
    """
    Heurística leve para inferir {nome_da_variavel: ClasseTPZ} a partir de
    declarações no próprio trecho de código gerado. Não é um parser de C++
    completo (não resolve typedefs locais, não segue reatribuições) — é
    suficiente para os padrões de código NeoPZ mais comuns (ver
    reference_solutions/task_03_poisson2d/poisson.cpp).
    """
    bindings = {}
    # ordem: dos mais específicos para os mais genéricos, para que um bind
    # mais específico não seja sobrescrito por um genérico depois
    for regex in (_BIND_AUTO_NEW_RE,):
        for var, cls in regex.findall(code):
            bindings.setdefault(var, cls)
    for regex in (_BIND_AUTOPOINTER_RE, _BIND_POINTER_REF_RE, _BIND_STACK_VALUE_RE, _BIND_BARE_VALUE_RE):
        for cls, var in regex.findall(code):
            bindings.setdefault(var, cls)
    return bindings


def find_suspicious_method_calls(code: str, method_whitelist: set, class_whitelist: set = None) -> list:
    """
    Retorna uma lista de (variavel_ou_classe, metodo) para chamadas de método
    que:
      (a) foram feitas em uma variável que a heurística conseguiu associar com
          confiança a uma classe TPZ (ex: `gmesh->Foo()` onde `gmesh` foi
          declarado como `TPZAutoPointer<TPZGeoMesh> gmesh = ...`), OU
      (b) são chamadas qualificadas explícitas `TPZAlgumaCoisa::Foo(...)`;
    e cujo nome de método NÃO aparece na whitelist global de métodos.

    Chamadas em variáveis de tipo desconhecido (int, std::vector, ponteiro
    genérico, etc) são ignoradas de propósito — não dá pra saber se são
    métodos do NeoPZ ou de outra coisa, e marcar isso geraria falso positivo
    (ex: vetor.push_back(x) não é NeoPZ, não deveria ser sinalizado).
    """
    if not method_whitelist:
        return []

    class_whitelist = class_whitelist or set()
    bindings = _bind_variables_to_classes(code)

    suspeitos = []
    seen = set()

    for var, method in _METHOD_CALL_RE.findall(code):
        cls = bindings.get(var)
        if not cls:
            continue
        # construtor/destrutor explícito (ex: `gmesh->~TPZGeoMesh()`, raro mas
        # válido) ou chamada cujo "método" é na verdade o nome da classe
        if method in (cls, f"~{cls}"):
            continue
        if method not in method_whitelist:
            key = (cls, method)
            if key not in seen:
                seen.add(key)
                suspeitos.append(key)

    for cls, method in _QUALIFIED_CALL_RE.findall(code):
        if cls not in class_whitelist:
            continue  # classe já é desconhecida — isso é alucinação de classe, não de método
        if method in (cls, f"~{cls}"):
            continue
        if method not in method_whitelist:
            key = (cls, method)
            if key not in seen:
                seen.add(key)
                suspeitos.append(key)

    return suspeitos
