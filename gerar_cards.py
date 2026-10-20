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


def gerar_card(nome: str, header_rel: str) -> str:
    header_path = NEOPZ_DIR / header_rel
    texto = header_path.read_text(encoding="utf-8", errors="replace")
    # remove comentários de bloco /** ... */ antes de quebrar em linhas
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    linhas = texto.splitlines()
    decls = extrair_publicos(linhas, nome)

    out = [f"# {nome} — API card",
           "",
           f"Generated from `{header_rel}` — do not edit by hand.",
           "",
           f'Include: `"{header_rel}"` (no código: #include "{header_rel}")',
           "",
           "Public methods (exact declarations from the header):"]
    out += [f"- `{d}`" for d in decls] or ["- (nenhuma declaração pública encontrada)"]
    return "\n".join(out) + "\n"


def main():
    args = sys.argv[1:]
    index = json.loads(HEADER_INDEX.read_text())

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
        header_rel = index.get(nome)
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
