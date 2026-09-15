from pathlib import Path

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_ollama import OllamaLLM
except ImportError:
    try:
        from langchain_community.llms import Ollama as OllamaLLM
    except ImportError:
        OllamaLLM = None

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

# ── Configurações ──────────────────────────────────────────────────────────────
GEMINI_MODEL           = "gemini-3.6-flash"
OLLAMA_MODEL           = "qwen2.5-coder:7b"

NUM_CTX                = 8192

EMBED_MODEL            = "BAAI/bge-base-en-v1.5"

INDEX_DIR              = Path("./banco_chroma_develop")
WHITELIST_FILE         = INDEX_DIR / "whitelist.txt"
HEADERS_WHITELIST_FILE = INDEX_DIR / "headers_whitelist.txt"
METHODS_WHITELIST_FILE = INDEX_DIR / "methods_whitelist.txt"
CLASS_METHODS_INDEX_FILE = INDEX_DIR / "class_methods_index.json"

HEADER_INDEX_DIR        = Path("./header_index")
CLASS_HEADER_INDEX_FILE  = HEADER_INDEX_DIR / "class_header_index.json"
COLLISIONS_FILE          = HEADER_INDEX_DIR / "collisions.json"

LEGACY_CLASSES_FILE     = INDEX_DIR / "legacy_classes.txt"

LOG_INTERACOES_FILE     = Path("./logs/interacoes.jsonl")

RENAMES_FILE            = Path("./renames.json")
TEMPERATURE            = 0.1
MAX_RETRIES            = 2
K_HEADERS              = 4
K_EXAMPLES             = 4
EXAMPLE_POOL_MULT      = 6

COL_HEADERS  = "neopz_headers"
COL_EXAMPLES = "neopz_examples"
COL_WIKI     = "neopz_wiki"

K_WIKI       = 3
K_WIKI_CONCEITOS = 1

INCLUDES_LIXO_CONHECIDOS = {"neopz.h", "pz.h", "pzc.h"}

HEADERS_SISTEMA = {"math.h", "stdio.h", "stdlib.h", "string.h", "assert.h",
                   "time.h", "float.h", "limits.h", "ctype.h", "stddef.h"}

# ── Compilação do código gerado ───────────────────────────────────────────────
NEOPZ_PREFIXES = (
    Path.home() / "opt" / "neopz-develop",
    Path("/opt/neopz"),
)
NEOPZ_CXX           = "/opt/local/bin/g++"
TIMEOUT_COMPILACAO  = 60
MAX_ERROS_RELATADOS = 5

CUTOFF_CLASSE_AUTOMATICA = 0.80
CUTOFF_METODO_AUTOMATICO = 0.78

