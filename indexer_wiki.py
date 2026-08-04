"""
indexer_wiki.py  (v2 — página inteira por documento)

Indexa a wiki de análise do NeoPZ no banco ChromaDB, coleção 'neopz_wiki'.

Estratégia:
  • Wiki (pages/):     1 arquivo .md = 1 documento. Sem chunking.
                       As páginas são pequenas (50-150 linhas) e já estão
                       organizadas por classe/conceito — cortar quebraria
                       a coerência e poderia separar assinaturas de métodos
                       do contexto explicativo.
  • Deliverables (ai-analysis/*.md):
                       Arquivos maiores divididos apenas no heading '## ',
                       mantendo cada seção intacta. Se o arquivo for pequeno
                       (<8 000 chars) entra como um único documento.

Execute UMA VEZ (ou sempre que a wiki for atualizada):

    cd ~/Documents/assistente-labmec
    python3 indexer_wiki.py
"""
import re
from pathlib import Path

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from langchain_core.documents import Document

# ── Configurações ──────────────────────────────────────────────────────────────
# A wiki vive DENTRO do projeto (wiki_neopz/) — versionada no git e portável
# para outras máquinas. Antes ficava em ~/Downloads/ai-analysis, que quebrava
# silenciosamente em qualquer computador que não fosse o original.
ANALISE_DIR = Path("./wiki_neopz")
WIKI_DIR    = ANALISE_DIR / "wiki"
INDEX_DIR   = Path("./banco_chroma_develop")  # ver nota em pipeline.py
EMBED_MODEL = "BAAI/bge-base-en-v1.5"
COL_WIKI    = "neopz_wiki"

# Deliverables maiores que este limite são divididos por seção (## heading)
MAX_PAGE_CHARS = 8_000
# ──────────────────────────────────────────────────────────────────────────────

TIPO_MAP = {
    "code":     "doc_codigo",
    "concepts": "doc_conceito",
    "findings": "doc_finding",
    "flows":    "doc_fluxo",
    "sources":  "doc_referencia",
}


def _tipo(path: Path) -> str:
    partes = list(path.parts)
    if "wiki" in partes:
        idx = partes.index("wiki")
        subdir = partes[idx + 1] if idx + 1 < len(partes) else ""
        return TIPO_MAP.get(subdir, "doc_wiki_meta")
    return "doc_analise"


def _split_por_secao(texto: str) -> list:
    """Divide texto apenas nos headings ## (seção de nível 1)."""
    partes = re.split(r'(?m)^(?=## )', texto)
    return [p.strip() for p in partes if p.strip()]


def _classes(texto: str) -> str:
    return ", ".join(sorted(set(re.findall(r"\bTPZ[A-Z]\w+", texto))))


def _carregar_documentos() -> list:
    docs = []

    # ── Wiki: página inteira = um documento ──────────────────────────────────
    if WIKI_DIR.exists():
        wiki_files = [f for f in sorted(WIKI_DIR.rglob("*.md"))
                      if ".obsidian" not in f.parts]
        print(f"  Wiki: {len(wiki_files)} páginas  →  {len(wiki_files)} documentos (1:1)")
        for path in wiki_files:
            try:
                texto = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                print(f"  ⚠️  {path.name}: {e}")
                continue
            if not texto:
                continue
            docs.append(Document(
                page_content=texto,
                metadata={
                    "source":         str(path),
                    "tipo":           _tipo(path),
                    "titulo":         path.stem.replace("-", " ").replace("_", " "),
                    "classes_usadas": _classes(texto),
                }
            ))
    else:
        print(f"  ⚠️  Wiki não encontrada em {WIKI_DIR}")

    # ── Deliverables: dividir por seção ## se arquivo grande ─────────────────
    if ANALISE_DIR.exists():
        deliverables = sorted(ANALISE_DIR.glob("*.md"))
        n_secoes = 0
        for path in deliverables:
            try:
                texto = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                print(f"  ⚠️  {path.name}: {e}")
                continue
            if not texto:
                continue

            secoes = _split_por_secao(texto) if len(texto) > MAX_PAGE_CHARS else [texto]
            titulo_base = path.stem.replace("-", " ").replace("_", " ")
            for sec in secoes:
                docs.append(Document(
                    page_content=sec,
                    metadata={
                        "source":         str(path),
                        "tipo":           "doc_analise",
                        "titulo":         titulo_base,
                        "classes_usadas": _classes(sec),
                    }
                ))
            n_secoes += len(secoes)

        print(f"  Deliverables: {len(deliverables)} arquivos  →  {n_secoes} seções")
    else:
        print(f"  ⚠️  ai-analysis não encontrada em {ANALISE_DIR}")

    return docs


def main():
    print("=" * 58)
    print("  INDEXADOR WIKI NEOPZ  (v2 — página inteira por doc)")
    print("=" * 58)
    print()

    docs = _carregar_documentos()
    if not docs:
        print("\n❌ Nenhum documento encontrado. Verifique os caminhos acima.")
        return

    print(f"\n  Total: {len(docs)} documentos")
    print(f"  Carregando modelo de embeddings: {EMBED_MODEL}...")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Remove coleção antiga para evitar duplicatas na reindexação
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(INDEX_DIR))
        nomes = [c.name for c in client.list_collections()]
        if COL_WIKI in nomes:
            client.delete_collection(COL_WIKI)
            print(f"  Coleção antiga '{COL_WIKI}' removida (reindexando limpo)")
    except Exception:
        pass  # ChromaDB mais antigo sem list_collections — tudo bem

    print(f"  Indexando na coleção '{COL_WIKI}'...")
    Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(INDEX_DIR),
        collection_name=COL_WIKI,
    )

    print(f"\n✅ {len(docs)} documentos indexados em '{COL_WIKI}'")
    print("   O pipeline.py usará a wiki automaticamente a partir de agora.")
    print("=" * 58)


if __name__ == "__main__":
    main()
