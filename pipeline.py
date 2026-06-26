from pathlib import Path
import re
import json
import difflib

try:
    from langchain_ollama import OllamaLLM
except ImportError:
    from langchain_community.llms import Ollama as OllamaLLM

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from cpp_parser import find_tpz_classes_in_code

# ── Configurações ──────────────────────────────────────────────────────────────
OLLAMA_MODEL           = "assistente-labmec"
EMBED_MODEL            = "BAAI/bge-base-en-v1.5"
INDEX_DIR              = Path("./banco_chroma")
WHITELIST_FILE         = INDEX_DIR / "whitelist.txt"
HEADERS_WHITELIST_FILE = INDEX_DIR / "headers_whitelist.txt"

# Índice determinístico classe -> header real (gerado por
# header_index/build_class_header_index.py a partir do source do NeoPZ).
# Mais forte que HEADERS_WHITELIST_FILE: aquele só checa se o NOME do header
# existe em algum lugar do repo; este checa se é o header CORRETO para a
# classe específica que foi usada no código.
HEADER_INDEX_DIR        = Path("./header_index")
CLASS_HEADER_INDEX_FILE  = HEADER_INDEX_DIR / "class_header_index.json"
COLLISIONS_FILE          = HEADER_INDEX_DIR / "collisions.json"
TEMPERATURE            = 0.1
MAX_RETRIES            = 2          # tentativas extras ao detectar alucinação
K_HEADERS              = 4          # chunks de declaração de classe a recuperar
K_EXAMPLES             = 4          # chunks de exemplo de uso a recuperar

COL_HEADERS  = "neopz_headers"
COL_EXAMPLES = "neopz_examples"
# ──────────────────────────────────────────────────────────────────────────────


# ── Inicialização ──────────────────────────────────────────────────────────────

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


def _carregar_class_header_index() -> dict:
    """Carrega {classe: 'caminho/relativo/header.h'} gerado por build_class_header_index.py."""
    if not CLASS_HEADER_INDEX_FILE.exists():
        print("⚠️  class_header_index.json não encontrado — rode header_index/build_class_header_index.py.")
        return {}
    dados = json.loads(CLASS_HEADER_INDEX_FILE.read_text(encoding='utf-8'))
    print(f"  Índice classe→header: {len(dados)} classes mapeadas")
    return dados


def _carregar_collisions() -> dict:
    """Carrega classes com mais de um header válido (não corrigir automaticamente)."""
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
    return headers_db, examples_db


# ── Recuperação ────────────────────────────────────────────────────────────────

def _recuperar_contexto(pergunta: str, headers_db, examples_db) -> tuple:
    """
    Busca nas duas coleções com MMR e retorna (h_docs, e_docs, fontes).
    MMR = Maximal Marginal Relevance — evita trazer chunks repetidos.
    """
    h_docs = headers_db.max_marginal_relevance_search(
        pergunta, k=K_HEADERS, fetch_k=K_HEADERS * 3
    )
    e_docs = examples_db.max_marginal_relevance_search(
        pergunta, k=K_EXAMPLES, fetch_k=K_EXAMPLES * 3
    )

    all_docs = h_docs + e_docs
    fontes = {doc.metadata.get("source", "?") for doc in all_docs}

    return h_docs, e_docs, fontes


def _formatar_contexto(h_docs: list, e_docs: list) -> str:
    """Formata os documentos recuperados em um bloco de contexto legível."""
    partes = []

    if h_docs:
        partes.append("=== DECLARAÇÕES DE CLASSE (interface real do NeoPZ) ===")
        for doc in h_docs:
            classe = doc.metadata.get("classe", "")
            label = f"[Classe: {classe}]" if classe else "[Header]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== FIM DAS DECLARAÇÕES ===")

    if e_docs:
        partes.append("\n=== EXEMPLOS DE USO ===")
        for doc in e_docs:
            fonte = Path(doc.metadata.get("source", "")).name
            partes.append(f"[Arquivo: {fonte}]\n{doc.page_content}")
        partes.append("=== FIM DOS EXEMPLOS ===")

    return "\n\n---\n\n".join(partes)


# ── Sugestões de correção (difflib) ──────────────────────────────────────────────

def _sugerir_correcoes(alucinadas: list, whitelist: set, cutoff: float = 0.6) -> dict:
    """Para cada item inexistente, busca os nomes reais mais parecidos."""
    sugestoes = {}
    for item in alucinadas:
        sugestoes[item] = difflib.get_close_matches(item, whitelist, n=3, cutoff=cutoff)
    return sugestoes


# ── Geração / prompt ─────────────────────────────────────────────────────────────

def _montar_prompt(
    pergunta: str,
    contexto: str,
    system_base: str,
    whitelist: set,
    headers_whitelist: set,
    classes_alucinadas: list = None,
    includes_errados: dict = None,
    includes_por_classe: dict = None,
) -> str:
    """
    Monta o prompt completo como string.
    Se houver classes alucinadas ou includes errados, adiciona instrução de correção.
    """
    classes_reais = ", ".join(sorted(whitelist)[:50]) if whitelist else "—"

    instrucao_correcao = ""

    # Correção de classes
    if classes_alucinadas:
        sugestoes = _sugerir_correcoes(classes_alucinadas, whitelist)
        linhas = []
        for classe, matches in sugestoes.items():
            if matches:
                linhas.append(f"  - '{classe}' não existe. Você quis dizer: {', '.join(matches)}?")
            else:
                linhas.append(f"  - '{classe}' não existe e não há classe parecida.")
        instrucao_correcao += (
            "\n\n⚠️ CLASSES INVÁLIDAS:\n"
            + "\n".join(linhas)
        )

    # Correção de includes
    if includes_errados:
        linhas_inc = []
        for inc, sugs in includes_errados.items():
            if sugs:
                linhas_inc.append(f"  - '#include \"{inc}\"' NÃO existe. Use no lugar: {', '.join(sugs)}")
            else:
                linhas_inc.append(
                    f"  - '#include \"{inc}\"' NÃO existe e NÃO há header parecido. "
                    f"NÃO existe header único no NeoPZ. Inclua os headers específicos "
                    f"de cada classe usada (ex: \"pzgmesh.h\" para TPZGeoMesh, "
                    f"\"pzcmesh.h\" para TPZCompMesh)."
                )
        instrucao_correcao += (
            "\n\n⚠️ CORRIJA OS HEADERS — OBRIGATÓRIO:\n"
            + "\n".join(linhas_inc)
            + "\nNÃO repita o header inválido na próxima resposta."
        )

    # Correção de includes por classe (índice determinístico classe -> header)
    if includes_por_classe:
        linhas_idx = [
            f"  - Você usou '{classe}' mas não incluiu \"{header}\". Adicione: #include \"{header}\""
            for classe, header in includes_por_classe.items()
        ]
        instrucao_correcao += (
            "\n\n⚠️ HEADERS FALTANDO (segundo índice classe→header, fonte de verdade):\n"
            + "\n".join(linhas_idx)
        )

    if instrucao_correcao:
        instrucao_correcao += "\nReescreva o código usando os nomes corretos."

    return f"""{system_base}

REGRA FUNDAMENTAL: NUNCA invente nomes de classes TPZ nem de headers.
Use SOMENTE classes e headers que aparecem no contexto fornecido abaixo.

REGRA ABSOLUTA SOBRE HEADERS: NUNCA escreva #include "NeoPZ.h" — esse arquivo
NÃO EXISTE e quebra a compilação. NÃO existe header único que inclui tudo.
Para CADA classe, inclua o header específico. Exemplos:
  TPZGeoMesh        → #include "pzgmesh.h"
  TPZCompMesh       → #include "pzcmesh.h"
  TPZLinearAnalysis → #include "TPZLinearAnalysis.h"

Classes TPZ que existem no projeto (lista parcial para referência):
{classes_reais}
{instrucao_correcao}

INSTRUÇÕES:
- Use apenas classes cujos headers aparecem no contexto
- Use apenas métodos visíveis nas declarações de classe acima
- Sempre inclua os #include específicos necessários
- Siga os padrões dos exemplos de uso
- Se não tiver certeza do nome exato, escreva: // TODO: verificar nome
- Se o usuário pedir uma explicação, responda com texto didático
- Se o usuário pedir código, gere com explicações do que cada parte faz
- Combine texto explicativo e código quando fizer sentido

{contexto}

Tarefa: {pergunta}

Resposta:"""


# ── Validação ──────────────────────────────────────────────────────────────────

def _validar_codigo(codigo: str, whitelist: set) -> list:
    """
    Verifica se o código usa apenas classes reais do NeoPZ.
    Retorna lista de classes alucinadas (vazia = tudo OK).
    """
    if not whitelist:
        return []
    usadas = find_tpz_classes_in_code(codigo)
    return [c for c in usadas if c not in whitelist]


def _extrair_includes(codigo: str) -> list:
    """Extrai nomes de headers .h incluídos no código (ex: 'NeoPZ.h')."""
    achados = re.findall(r'#include\s*[<"]([^>"]+\.h)[>"]', codigo)
    return [Path(inc).name for inc in achados]


def _validar_includes(codigo: str, headers_whitelist: set) -> dict:
    """
    Verifica os #include .h contra a whitelist de headers reais.
    Retorna {include_errado: [sugestões]} — dict vazio = tudo OK.
    """
    if not headers_whitelist:
        return {}
    usados = _extrair_includes(codigo)
    problemas = {}
    for inc in usados:
        if inc not in headers_whitelist:
            problemas[inc] = difflib.get_close_matches(inc, headers_whitelist, n=3, cutoff=0.5)
    return problemas


def _validar_includes_por_classe(codigo: str, class_header_index: dict, collisions: dict) -> dict:
    """
    Verificação mais forte que _validar_includes(): para cada classe TPZ usada no
    código, checa se o #include CORRETO para aquela classe específica (segundo o
    índice determinístico class_header_index) está presente — não apenas se o
    nome do header existe em algum lugar do repo.

    Classes em collisions.json são ignoradas (mais de um header válido — não é
    possível forçar um único automaticamente).

    Retorna {classe: header_correto} para as classes cujo header certo está
    faltando — dict vazio = tudo OK.
    """
    if not class_header_index:
        return {}

    usadas = find_tpz_classes_in_code(codigo)
    includes_atuais = set(_extrair_includes(codigo))

    faltando = {}
    for classe in usadas:
        if classe in collisions:
            continue  # ambíguo — não força um único header
        caminho = class_header_index.get(classe)
        if not caminho:
            continue  # classe fora do índice (pode ser nova ou não-TPZ)
        header_real = Path(caminho).name
        if header_real not in includes_atuais:
            faltando[classe] = header_real
    return faltando


# ── Pipeline principal ─────────────────────────────────────────────────────────

def gerar_codigo(
    pergunta: str,
    llm,
    headers_db,
    examples_db,
    whitelist: set,
    headers_whitelist: set,
    system_base: str,
    class_header_index: dict = None,
    collisions: dict = None,
) -> dict:
    """
    Executa o pipeline completo:
    recuperação → formatação → geração → validação → retry se necessário.
    """
    class_header_index = class_header_index or {}
    collisions = collisions or {}

    classes_alucinadas = None
    includes_errados = None
    includes_por_classe = None

    for tentativa in range(1, MAX_RETRIES + 2):
        print(f"  [Tentativa {tentativa}] Buscando contexto e gerando resposta...")

        # 1. Recupera documentos relevantes
        h_docs, e_docs, fontes = _recuperar_contexto(pergunta, headers_db, examples_db)

        # 2. Formata o contexto
        contexto = _formatar_contexto(h_docs, e_docs)

        # 3. Monta o prompt (com correções se for retry)
        prompt = _montar_prompt(
            pergunta, contexto, system_base, whitelist, headers_whitelist,
            classes_alucinadas, includes_errados, includes_por_classe,
        )

        # 4. Chama o modelo
        resposta = llm.invoke(prompt)

        # 5. Valida classes E includes (whitelist + índice determinístico por classe)
        classes_alucinadas = _validar_codigo(resposta, whitelist)
        includes_errados = _validar_includes(resposta, headers_whitelist)
        includes_por_classe = _validar_includes_por_classe(resposta, class_header_index, collisions)

        if not classes_alucinadas and not includes_errados and not includes_por_classe:
            print("  ✅ Validação OK — classes e headers existem e estão corretos no NeoPZ!")
            return {
                "resposta":            resposta,
                "valido":              True,
                "alucinacoes":         [],
                "includes":            {},
                "includes_por_classe": {},
                "fontes":              fontes,
                "tentativas":          tentativa,
            }

        if classes_alucinadas:
            print(f"  ⚠️  Classes não encontradas: {', '.join(classes_alucinadas)}")
        if includes_errados:
            print(f"  ⚠️  Headers não encontrados: {', '.join(includes_errados.keys())}")
        if includes_por_classe:
            print(f"  ⚠️  Header errado/faltando para classe: {includes_por_classe}")

        if tentativa >= MAX_RETRIES + 1:
            print("  ⚠️  Limite de tentativas atingido.")
            break

        print("  ↩️  Corrigindo automaticamente na próxima tentativa...")

    return {
        "resposta":            resposta,
        "valido":              False,
        "alucinacoes":         classes_alucinadas or [],
        "includes":            includes_errados or {},
        "includes_por_classe": includes_por_classe or {},
        "fontes":              fontes,
        "tentativas":          tentativa,
    }


# ── Loop de conversa ───────────────────────────────────────────────────────────

def main():
    print("Carregando modelos e banco de dados...")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    headers_db, examples_db = _carregar_bancos(embeddings)
    whitelist          = _carregar_whitelist()
    headers_whitelist  = _carregar_headers_whitelist()
    class_header_index = _carregar_class_header_index()
    collisions         = _carregar_collisions()
    system_base        = _carregar_system_prompt()
    llm                = OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE)

    print("\n" + "=" * 50)
    print("  🤖 Assistente LabMeC Pronto!")
    print("  Digite 'sair' para encerrar.")
    print("=" * 50 + "\n")

    while True:
        pergunta = input("Você: ").strip()

        if pergunta.lower() in ("sair", "exit", "quit"):
            print("Encerrando. Bom trabalho!")
            break

        if not pergunta:
            continue

        print("\n[Pensando: buscando documentação e gerando resposta...]")

        resultado = gerar_codigo(
            pergunta, llm, headers_db, examples_db,
            whitelist, headers_whitelist, system_base,
            class_header_index, collisions,
        )

        print("\nAssistente LabMeC:\n")
        print(resultado["resposta"])
        print()

        # Status de validação
        if resultado["alucinacoes"]:
            print(f"⚠️  Classes não verificadas: {', '.join(resultado['alucinacoes'])}")
        if resultado["includes"]:
            print(f"⚠️  Headers não verificados: {', '.join(resultado['includes'].keys())}")
        if resultado["includes_por_classe"]:
            faltando_fmt = ", ".join(f"{c} → {h}" for c, h in resultado["includes_por_classe"].items())
            print(f"⚠️  Header incorreto/faltando para classe (índice determinístico): {faltando_fmt}")
        if not resultado["alucinacoes"] and not resultado["includes"] and not resultado["includes_por_classe"]:
            print("✅ Resposta validada — classes e headers existem e estão corretos no NeoPZ")

        # Fontes usadas
        fontes_curtas = [Path(f).name for f in resultado["fontes"]]
        print(f"📄 Fontes ({resultado['tentativas']} tentativa(s)): {', '.join(fontes_curtas)}")
        print("-" * 50 + "\n")


if __name__ == "__main__":
    main()