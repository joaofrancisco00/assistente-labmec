"""
Indexador NeoPZ — versão melhorada.

Diferenças em relação ao indexer anterior:
  ❌ Antes: só .cpp, chunk_size=1000, tudo numa coleção
  ✅ Agora: .h com parser inteligente + .cpp maiores, 2 coleções separadas
            + whitelist de classes reais para validação
            + whitelist de headers reais para validação de #include
"""
import re
from pathlib import Path
from tqdm import tqdm

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

import json

from cpp_parser import (
    extract_classes_from_header,
    build_class_whitelist,
    build_header_whitelist,
    build_method_whitelist,
    build_class_methods_index,
)

# ── Configurações ──────────────────────────────────────────────────────────────
BASE_DIR               = Path("./base_de_dados")   # pasta com .h e .cpp do NeoPZ
INDEX_DIR              = Path("./banco_chroma")
WHITELIST_FILE          = INDEX_DIR / "whitelist.txt"
HEADERS_WHITELIST_FILE  = INDEX_DIR / "headers_whitelist.txt"
METHODS_WHITELIST_FILE  = INDEX_DIR / "methods_whitelist.txt"
CLASS_METHODS_INDEX_FILE = INDEX_DIR / "class_methods_index.json"
EMBED_MODEL            = "BAAI/bge-base-en-v1.5"

# Nomes das coleções no ChromaDB (não mudar depois de indexado)
COL_HEADERS  = "neopz_headers"   # declarações de classe
COL_EXAMPLES = "neopz_examples"  # exemplos de uso

# Tamanhos de chunk — maiores que o anterior para não cortar declarações
HEADER_CHUNK_SIZE  = 2500
EXAMPLE_CHUNK_SIZE = 2000
CHUNK_OVERLAP      = 300
# ──────────────────────────────────────────────────────────────────────────────


def _carregar_embeddings():
    print(f"Carregando embeddings: {EMBED_MODEL}")
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def _indexar_headers(embeddings):
    """
    Indexa arquivos .h com parser C++ inteligente.
    Cada chunk = uma declaração de classe completa.
    """
    print("\n📋 Indexando headers (.h)...")

    h_files = list(BASE_DIR.rglob("*.h"))
    if not h_files:
        print("  ⚠️  Nenhum .h encontrado!")
        print("  Os headers são ESSENCIAIS — contêm os nomes de classe reais.")
        print("  Adicione os arquivos .h do repositório neopz em base_de_dados/")
        return

    print(f"  {len(h_files)} arquivos .h encontrados")
    documents = []

    for h_file in tqdm(h_files, desc="  Parseando classes"):
        chunks = extract_classes_from_header(h_file)

        if not chunks:
            # Header sem classes TPZ — indexa como bloco genérico
            try:
                raw = h_file.read_text(encoding='utf-8', errors='replace')
                if raw.strip():
                    documents.append(Document(
                        page_content=raw[:2000],
                        metadata={"source": str(h_file), "tipo": "header", "classe": ""}
                    ))
            except Exception:
                pass
            continue

        for chunk in chunks:
            documents.append(Document(
                page_content=chunk.to_text(),
                metadata={
                    "source":  chunk.file_path,
                    "tipo":    "class_header",
                    "classe":  chunk.class_name,
                    "metodos": ", ".join(chunk.methods[:8]),
                }
            ))

    print(f"  {len(documents)} chunks gerados a partir dos headers")

    if not documents:
        return

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(INDEX_DIR),
        collection_name=COL_HEADERS,
    )
    print(f"  ✅ Salvo na coleção '{COL_HEADERS}'")


def _indexar_exemplos(embeddings):
    """
    Indexa arquivos .cpp como exemplos de uso.
    Usa splitter convencional mas com chunks maiores e separadores C++.
    """
    print("\n💡 Indexando exemplos (.cpp)...")

    cpp_files = list(BASE_DIR.rglob("*.cpp"))
    if not cpp_files:
        print("  ⚠️  Nenhum .cpp encontrado.")
        return

    print(f"  {len(cpp_files)} arquivos .cpp encontrados")

    # Separadores que fazem sentido em C++ (evita cortar dentro de funções)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=EXAMPLE_CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\nint ", "\nvoid ", "\nbool ", "\nTPZ", "\n{", "\n}", "\n", " "],
    )

    documents = []
    for cpp_file in tqdm(cpp_files, desc="  Dividindo exemplos"):
        try:
            content = cpp_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        for chunk in splitter.split_text(content):
            # Registra quais classes TPZ aparecem nesse trecho (ajuda no retrieval)
            tpz_classes = ", ".join(set(re.findall(r'\bTPZ[A-Z]\w+', chunk)))
            documents.append(Document(
                page_content=chunk,
                metadata={
                    "source":        str(cpp_file),
                    "tipo":          "exemplo",
                    "classes_usadas": tpz_classes,
                }
            ))

    print(f"  {len(documents)} chunks gerados a partir dos exemplos")

    if not documents:
        return

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(INDEX_DIR),
        collection_name=COL_EXAMPLES,
    )
    print(f"  ✅ Salvo na coleção '{COL_EXAMPLES}'")


def _gerar_whitelist():
    """
    Varre todos os .h e salva:
      - whitelist.txt          → nomes TPZ reais (classe/struct/namespace/using/typedef/enum)
      - headers_whitelist.txt  → nomes de headers .h reais
      - methods_whitelist.txt  → nomes de método/função reais (whitelist GLOBAL,
                                  não por classe — ver cpp_parser.build_method_whitelist)
    Esses arquivos são usados pelo pipeline para detectar alucinações.
    """
    print("\n🔍 Gerando whitelists (classes + headers + métodos)...")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Whitelist de classes
    classes = build_class_whitelist(BASE_DIR)
    if not classes:
        print("  ⚠️  Whitelist de classes vazia. Verifique os .h em base_de_dados/")
    else:
        WHITELIST_FILE.write_text('\n'.join(sorted(classes)), encoding='utf-8')
        sample = sorted(classes)[:6]
        print(f"  ✅ {len(classes)} classes salvas em whitelist.txt")
        print(f"     Exemplos: {', '.join(sample)}...")

    # 2. Whitelist de headers
    headers = build_header_whitelist(BASE_DIR)
    if not headers:
        print("  ⚠️  Whitelist de headers vazia.")
    else:
        HEADERS_WHITELIST_FILE.write_text('\n'.join(sorted(headers)), encoding='utf-8')
        sample = sorted(headers)[:6]
        print(f"  ✅ {len(headers)} headers salvos em headers_whitelist.txt")
        print(f"     Exemplos: {', '.join(sample)}...")

    # 3. Whitelist de métodos (global — não por classe, ver docstring do módulo)
    methods = build_method_whitelist(BASE_DIR)
    if not methods:
        print("  ⚠️  Whitelist de métodos vazia.")
    else:
        METHODS_WHITELIST_FILE.write_text('\n'.join(sorted(methods)), encoding='utf-8')
        sample = sorted(methods)[:6]
        print(f"  ✅ {len(methods)} métodos salvos em methods_whitelist.txt")
        print(f"     Exemplos: {', '.join(sample)}...")

    # 4. Índice classe -> métodos (usado só na CORREÇÃO automática de método,
    #    não na detecção — ver cpp_parser.build_class_methods_index)
    class_methods = build_class_methods_index(BASE_DIR)
    if not class_methods:
        print("  ⚠️  Índice classe→métodos vazio.")
    else:
        CLASS_METHODS_INDEX_FILE.write_text(
            json.dumps(class_methods, indent=2, sort_keys=True, ensure_ascii=False), encoding='utf-8'
        )
        print(f"  ✅ {len(class_methods)} classes mapeadas em class_methods_index.json")


def main():
    print("=" * 55)
    print("  INDEXADOR NEOPZ — VERSÃO MELHORADA")
    print("=" * 55)

    if not BASE_DIR.exists():
        print(f"\n❌ Pasta '{BASE_DIR}' não encontrada!")
        print("  Crie a pasta base_de_dados/ e adicione os arquivos do NeoPZ.")
        return

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    _gerar_whitelist()
    embeddings = _carregar_embeddings()
    _indexar_headers(embeddings)
    _indexar_exemplos(embeddings)

    print("\n" + "=" * 55)
    print("  ✅ INDEXAÇÃO CONCLUÍDA!")
    print(f"  Índice salvo em: {INDEX_DIR}")
    print("=" * 55)


if __name__ == "__main__":
    main()
