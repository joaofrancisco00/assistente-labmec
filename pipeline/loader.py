import json
from pathlib import Path

from .config import (
    WHITELIST_FILE,
    HEADERS_WHITELIST_FILE,
    METHODS_WHITELIST_FILE,
    CLASS_METHODS_INDEX_FILE,
    CLASS_HEADER_INDEX_FILE,
    LEGACY_CLASSES_FILE,
    RENAMES_FILE,
    COLLISIONS_FILE,
    INDEX_DIR,
    COL_HEADERS,
    COL_EXAMPLES,
    COL_WIKI,
    Chroma,
)

def _carregar_whitelist() -> set:
    if not WHITELIST_FILE.exists():
        print("⚠️  whitelist.txt não encontrada — execute indexer.py primeiro.")
        return set()
    classes = set(WHITELIST_FILE.read_text(encoding='utf-8').splitlines())
    print(f"  Whitelist de classes: {len(classes)} reais")
    return classes

def _carregar_headers_whitelist() -> set:
    if not HEADERS_WHITELIST_FILE.exists():
        print("⚠️  headers_whitelist.txt não encontrada — execute indexer.py primeiro.")
        return set()
    headers = set(HEADERS_WHITELIST_FILE.read_text(encoding='utf-8').splitlines())
    print(f"  Whitelist de headers: {len(headers)} reais")
    return headers

def _carregar_methods_whitelist() -> set:
    if not METHODS_WHITELIST_FILE.exists():
        print("⚠️  methods_whitelist.txt não encontrada — rode indexer.py.")
        return set()
    methods = set(METHODS_WHITELIST_FILE.read_text(encoding='utf-8').splitlines())
    print(f"  Whitelist de métodos: {len(methods)} reais")
    return methods

def _carregar_class_methods_index() -> dict:
    if not CLASS_METHODS_INDEX_FILE.exists():
        print("⚠️  class_methods_index.json não encontrado — rode indexer.py.")
        return {}
    dados = json.loads(CLASS_METHODS_INDEX_FILE.read_text(encoding='utf-8'))
    print(f"  Índice classe→métodos: {len(dados)} classes mapeadas")
    return dados

def _carregar_class_header_index() -> dict:
    if not CLASS_HEADER_INDEX_FILE.exists():
        print("⚠️  class_header_index.json não encontrado — rode header_index/build_class_header_index.py.")
        return {}
    dados = json.loads(CLASS_HEADER_INDEX_FILE.read_text(encoding='utf-8'))
    print(f"  Índice classe→header: {len(dados)} classes mapeadas")
    return dados

def _carregar_legacy_classes() -> set:
    if not LEGACY_CLASSES_FILE.exists():
        return set()
    classes = set(LEGACY_CLASSES_FILE.read_text(encoding='utf-8').splitlines()) - {""}
    if classes:
        print(f"  Classes da API antiga (aviso, não erro): {len(classes)}")
    return classes

def _carregar_renames() -> dict:
    if not RENAMES_FILE.exists():
        return {}
    dados = json.loads(RENAMES_FILE.read_text(encoding='utf-8'))
    renames = {k: v for k, v in dados.items() if not k.startswith("_")}
    if renames:
        print(f"  Renomeações conhecidas: {len(renames)} mapeadas")
    return renames

def _carregar_collisions() -> dict:
    if not COLLISIONS_FILE.exists():
        return {}
    dados = json.loads(COLLISIONS_FILE.read_text(encoding='utf-8'))
    if dados:
        print(f"  Colisões conhecidas (ambíguas, não auto-corrigidas): {len(dados)}")
    return dados

def _carregar_system_prompt() -> str:
    path = Path("system_prompt.txt")
    if path.exists():
        return path.read_text(encoding='utf-8').strip()
    return "Você é um especialista em programação C++ com a biblioteca NeoPZ."

def _carregar_bancos(embeddings):
    headers_db = Chroma(
        persist_directory=str(INDEX_DIR),
        embedding_function=embeddings,
        collection_name=COL_HEADERS,
    )
    examples_db = Chroma(
        persist_directory=str(INDEX_DIR),
        embedding_function=embeddings,
        collection_name=COL_EXAMPLES,
    )
    wiki_db = None
    try:
        candidate = Chroma(
            persist_directory=str(INDEX_DIR),
            embedding_function=embeddings,
            collection_name=COL_WIKI,
        )
        if candidate._collection.count() > 0:
            wiki_db = candidate
            print(f"  Wiki indexada: {candidate._collection.count()} chunks disponíveis")
        else:
            print("  Wiki não indexada ainda (rode indexer_wiki.py para ativá-la)")
    except Exception:
        print("  Wiki não indexada ainda (rode indexer_wiki.py para ativá-la)")
    return headers_db, examples_db, wiki_db
