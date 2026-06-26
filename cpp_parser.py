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


def _extract_method_names(content: str) -> list:
    """Extrai nomes de métodos públicos."""
    blacklist = {'if', 'while', 'for', 'switch', 'return', 'else', 'do',
                 'template', 'typename', 'decltype', 'sizeof', 'operator'}

    pattern = re.compile(
        r'(?:virtual\s+|static\s+|explicit\s+|inline\s+)*'
        r'[\w:<>*&\s,~]+\s+(~?[a-zA-Z]\w*)\s*\([^;{)]*\)'
        r'\s*(?:const\s*)?(?:override\s*)?(?:=\s*0\s*)?;',
        re.MULTILINE
    )
    names = []
    for m in pattern.finditer(content):
        name = m.group(1).strip()
        if name and name not in blacklist and not name[0].isdigit():
            names.append(name)
    return list(dict.fromkeys(names))  # mantém ordem, sem duplicatas


# ── API pública ────────────────────────────────────────────────────────────────

def extract_classes_from_header(filepath: Path) -> list:
    """
    Extrai todas as classes TPZxxx de um arquivo .h.
    Retorna uma lista de ClassChunk — um por classe encontrada.
    """
    try:
        content = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    # Encontra declarações de classe/struct com prefixo TPZ
    class_pattern = re.compile(
        r'(?:^|\n)[ \t]*(?:template\s*<[^>]*>\s*)?'
        r'((?:class|struct)\s+(TPZ\w+)[^{;]*)',
        re.MULTILINE
    )

    chunks = []
    for match in class_pattern.finditer(content):
        class_name = match.group(2)
        header_line = match.group(1).strip()

        # Encontra a chave de abertura
        brace_pos = content.find('{', match.start())
        if brace_pos == -1:
            continue

        # Ignora forward declarations (tem ';' entre a declaração e '{')
        if ';' in content[match.end():brace_pos]:
            continue

        end_pos = _find_matching_brace(content, brace_pos)
        body = content[brace_pos + 1:end_pos]

        clean = _extract_public_section(header_line, body)

        # Limita tamanho do chunk
        if len(clean) > 2500:
            clean = clean[:2500] + "\n    // ... (truncado)"

        methods = _extract_method_names(body)

        chunks.append(ClassChunk(
            class_name=class_name,
            file_path=str(filepath),
            content=clean,
            methods=methods[:15]
        ))

    return chunks


def build_class_whitelist(base_path: Path) -> set:
    """
    Varre todos os .h e retorna o conjunto de nomes de classes TPZ reais.
    Usado pelo indexer para criar a whitelist de validação.
    """
    classes = set()
    for h_file in base_path.rglob("*.h"):
        try:
            content = h_file.read_text(encoding='utf-8', errors='replace')
            found = re.findall(r'\b(?:class|struct)\s+(TPZ\w+)', content)
            classes.update(found)
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
