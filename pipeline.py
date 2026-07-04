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

from cpp_parser import find_tpz_classes_in_code, find_suspicious_method_calls

# ── Configurações ──────────────────────────────────────────────────────────────
OLLAMA_MODEL           = "qwen2.5-coder:7b"
EMBED_MODEL            = "BAAI/bge-base-en-v1.5"
INDEX_DIR              = Path("./banco_chroma")
WHITELIST_FILE         = INDEX_DIR / "whitelist.txt"
HEADERS_WHITELIST_FILE = INDEX_DIR / "headers_whitelist.txt"

# Whitelist GLOBAL de métodos (não por classe — ver nota em
# cpp_parser.find_suspicious_method_calls sobre por que não tentamos herança).
# Antes desta validação, só classe e header eram checados: um método inventado
# numa classe real (ex: `gmesh->SetBoundaryTypeFancy(1)`) passava como
# "✅ validado", mesmo sendo o tipo mais comum de alucinação na prática.
METHODS_WHITELIST_FILE = INDEX_DIR / "methods_whitelist.txt"

# Índice {classe: [métodos]} — usado SÓ na correção automática de método, não
# na detecção (que continua global, de propósito). Ver
# cpp_parser.build_class_methods_index: uma correção automática baseada na
# whitelist global já trocou 'CreateRectMesh' (inventado) por 'CreateMesh'
# (método de OUTRA classe, parecido só por coincidência de string) em vez do
# método real 'CreateGeoMeshOnGrid' — restringir a busca de correspondência
# aos métodos da própria classe evita essa contaminação cruzada.
CLASS_METHODS_INDEX_FILE = INDEX_DIR / "class_methods_index.json"

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
EXAMPLE_POOL_MULT      = 6          # tamanho do pool buscado antes do boost por classe citada

COL_HEADERS  = "neopz_headers"
COL_EXAMPLES = "neopz_examples"
COL_WIKI     = "neopz_wiki"        # documentação curada (wiki do professor)

K_WIKI       = 3                   # chunks da wiki a recuperar por consulta

# Headers "chute" que o modelo inventa e que NÃO existem no projeto — removidos
# automaticamente na correção pós-geração (ver _corrigir_includes_automaticamente).
INCLUDES_LIXO_CONHECIDOS = {"neopz.h", "pz.h", "pzc.h"}
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


def _carregar_methods_whitelist() -> set:
    if not METHODS_WHITELIST_FILE.exists():
        print("⚠️  methods_whitelist.txt não encontrada — rode indexer.py.")
        return set()
    methods = set(METHODS_WHITELIST_FILE.read_text(encoding='utf-8').splitlines())
    print(f"  Whitelist de métodos: {len(methods)} reais")
    return methods


def _carregar_class_methods_index() -> dict:
    """Carrega {classe: [métodos]} — usado só na correção automática (ver comentário na constante)."""
    if not CLASS_METHODS_INDEX_FILE.exists():
        print("⚠️  class_methods_index.json não encontrado — rode indexer.py.")
        return {}
    dados = json.loads(CLASS_METHODS_INDEX_FILE.read_text(encoding='utf-8'))
    print(f"  Índice classe→métodos: {len(dados)} classes mapeadas")
    return dados


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
    # Wiki é opcional — só carrega se já foi indexada com indexer_wiki.py
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


# ── Recuperação ────────────────────────────────────────────────────────────────

def _boost_por_classe(docs: list, classes_citadas: set, metadata_key: str) -> list:
    """
    Reordena `docs` para colocar primeiro os chunks cuja metadata (`classe` para
    headers, `classes_usadas` para exemplos) bate exatamente com alguma classe
    TPZ citada na pergunta do usuário. Pura reordenação determinística — não
    depende de embedding/MMR, é um complemento para os casos em que a busca
    semântica pura não traz o exemplo/declaração certa para uma classe citada
    explicitamente.
    """
    if not classes_citadas:
        return docs
    boost, resto = [], []
    for doc in docs:
        valor = doc.metadata.get(metadata_key, "") or ""
        partes = {c.strip() for c in valor.split(",") if c.strip()}
        if partes & classes_citadas:
            boost.append(doc)
        else:
            resto.append(doc)
    return boost + resto


def _recuperar_contexto(pergunta: str, headers_db, examples_db, wiki_db=None) -> tuple:
    """
    Busca nas coleções com MMR (pool ampliado) e depois reordena (boost)
    priorizando chunks cuja classe bate com alguma classe TPZ citada na
    pergunta. Se wiki_db estiver disponível, inclui documentação curada.
    Retorna (h_docs, e_docs, w_docs, fontes).
    """
    classes_citadas = find_tpz_classes_in_code(pergunta)

    pool_headers = max(K_HEADERS * EXAMPLE_POOL_MULT, K_HEADERS)
    h_pool = headers_db.max_marginal_relevance_search(
        pergunta, k=pool_headers, fetch_k=pool_headers * 2
    )
    h_docs = _boost_por_classe(h_pool, classes_citadas, "classe")[:K_HEADERS]

    pool_examples = max(K_EXAMPLES * EXAMPLE_POOL_MULT, K_EXAMPLES)
    e_pool = examples_db.max_marginal_relevance_search(
        pergunta, k=pool_examples, fetch_k=pool_examples * 2
    )
    e_docs = _boost_por_classe(e_pool, classes_citadas, "classes_usadas")[:K_EXAMPLES]

    # Wiki — documentação curada (API real, conceitos, bugs conhecidos)
    w_docs = []
    if wiki_db is not None:
        w_pool = wiki_db.max_marginal_relevance_search(
            pergunta, k=K_WIKI * EXAMPLE_POOL_MULT, fetch_k=K_WIKI * EXAMPLE_POOL_MULT * 2
        )
        w_docs = _boost_por_classe(w_pool, classes_citadas, "classes_usadas")[:K_WIKI]

    all_docs = h_docs + e_docs + w_docs
    fontes = {doc.metadata.get("source", "?") for doc in all_docs}

    return h_docs, e_docs, w_docs, fontes


def _formatar_contexto(h_docs: list, e_docs: list, w_docs: list = None) -> str:
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

    if w_docs:
        partes.append("\n=== DOCUMENTAÇÃO VERIFICADA (wiki de análise) ===")
        for doc in w_docs:
            titulo = doc.metadata.get("titulo", Path(doc.metadata.get("source", "")).stem)
            tipo   = doc.metadata.get("tipo", "")
            label  = f"[{titulo} | {tipo}]" if tipo else f"[{titulo}]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== FIM DA DOCUMENTAÇÃO ===")

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
    metodos_suspeitos: list = None,
    methods_whitelist: set = None,
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

    # Correção de métodos inventados (whitelist global — ver _validar_metodos)
    if metodos_suspeitos:
        linhas_met = []
        for classe, metodo in metodos_suspeitos:
            sugestoes = difflib.get_close_matches(metodo, methods_whitelist or set(), n=3, cutoff=0.6)
            if sugestoes:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' NÃO existe no NeoPZ. Você quis dizer: {', '.join(sugestoes)}?"
                )
            else:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' NÃO existe no NeoPZ e não há método parecido. "
                    f"Use apenas métodos que aparecem nas declarações de classe do contexto."
                )
        instrucao_correcao += (
            "\n\n⚠️ MÉTODOS INVENTADOS:\n"
            + "\n".join(linhas_met)
            + "\nNÃO use um método só porque parece lógico — confira nas declarações de classe do contexto."
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

def _resposta_contem_codigo(resposta: str) -> bool:
    """
    Heurística para distinguir uma resposta com código real de uma resposta
    em prosa (ex: "o que é a classe X e para que ela serve"). Usada para não
    exigir/injetar #include em respostas puramente explicativas, onde a
    classe é só citada no texto, não usada de fato.
    """
    if "```" in resposta:
        return True
    if re.search(r'#include\s*[<"]', resposta):
        return True
    if re.search(r'\bnew\s+TPZ\w+', resposta):
        return True
    # Padrões de uso real: declaração/instanciação/chamada (TPZX *v = ..., TPZX v(...), TPZX::Metodo)
    if re.search(r'\bTPZ\w+\s*[\*&]?\s*\w+\s*[=;(]', resposta):
        return True
    return False


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


def _validar_metodos(codigo: str, methods_whitelist: set, whitelist: set) -> list:
    """
    Verifica se os métodos chamados no código (em variáveis que a heurística
    conseguiu associar a uma classe TPZ, ou em chamadas qualificadas
    TPZClasse::Metodo) existem em ALGUM LUGAR do NeoPZ.

    Whitelist é GLOBAL, não por classe (ver nota em
    cpp_parser.find_suspicious_method_calls sobre a troca deliberada de
    precisão por segurança contra falso positivo — herança do NeoPZ é
    profunda demais para inferir só com regex).

    Retorna lista de (classe, metodo) suspeitos — vazia = tudo OK.
    """
    if not methods_whitelist:
        return []
    return find_suspicious_method_calls(codigo, methods_whitelist, whitelist)


# Cutoffs de confiança para substituição AUTOMÁTICA (sem depender do LLM
# aceitar a sugestão) — mais altos que os usados só para SUGERIR no prompt
# (0.6 em _sugerir_correcoes / 0.5 em _validar_includes), porque aqui o texto
# é reescrito direto, então o risco de trocar errado por acaso importa mais.
CUTOFF_CLASSE_AUTOMATICA = 0.80
CUTOFF_METODO_AUTOMATICO = 0.78


def _corrigir_classes_automaticamente(codigo: str, whitelist: set) -> tuple:
    """
    Correção determinística de nomes de classe TPZ "quase certos" — mesmo
    princípio de _corrigir_includes_automaticamente, mas para o nome da
    classe em si, não só o #include.

    Motivação real: o modelo local (qwen2.5-coder:7b) inventou uma vez
    'TPZGeomMeshTools' em vez de 'TPZGeoMeshTools' e repetiu o MESMO erro em
    3 tentativas seguidas mesmo com a sugestão certa no prompt
    (⚠️ CLASSES INVÁLIDAS: '...' Você quis dizer: TPZGeoMeshTools?) — ou seja,
    depender do LLM aceitar a correção não é confiável o bastante sozinho.

    Só substitui quando há um ÚNICO candidato de altíssima confiança
    (cutoff >= 0.80): evita trocar por engano um nome que só parece com outro
    por coincidência. Se não houver candidato confiante, o nome continua
    alucinado e cai na instrução de correção via prompt (fallback existente).

    Risco conhecido: a whitelist vem de um snapshot do NeoPZ de 2022 (ver
    header_index/README.md) — uma classe nova de verdade (criada depois
    desse snapshot) pode ser confundida com uma classe antiga parecida. As
    substituições aplicadas aparecem no log ("🔧 Corrigido automaticamente"),
    vale conferir de vez em quando.

    Retorna (codigo_corrigido, lista_de_correcoes_aplicadas).
    """
    if not whitelist:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    alucinadas = [c for c in usadas if c not in whitelist]
    if not alucinadas:
        return codigo, []

    correcoes = []
    for errada in alucinadas:
        candidatos = difflib.get_close_matches(errada, whitelist, n=1, cutoff=CUTOFF_CLASSE_AUTOMATICA)
        if not candidatos:
            continue
        certa = candidatos[0]
        codigo, n = re.subn(r'\b' + re.escape(errada) + r'\b', certa, codigo)
        if n:
            correcoes.append(f"{errada} → {certa}")
    return codigo, correcoes


def _corrigir_metodos_automaticamente(codigo: str, metodos_suspeitos: list, class_methods_index: dict) -> tuple:
    """
    Mesmo princípio de _corrigir_classes_automaticamente, mas para chamadas
    de método.

    IMPORTANTE — diferente da correção de classe: aqui a busca de
    correspondência é restrita aos métodos da PRÓPRIA classe
    (class_methods_index), não à whitelist global de métodos.
    A whitelist global tem ~3900 nomes curtos e genéricos (Create*, Get*,
    Set*...) repetidos de forma parecida em dezenas de classes — usá-la aqui
    já causou uma correção automática ERRADA de verdade: 'CreateRectMesh'
    (inventado) virou 'CreateMesh' (método de OUTRA classe, por coincidência
    de string) em vez do método real 'CreateGeoMeshOnGrid'. Restringir à
    própria classe evita essa contaminação cruzada — se a classe não estiver
    no índice ou não houver candidato bom o bastante ali, a chamada
    simplesmente NÃO é reescrita (fica marcada como suspeita mesmo, para
    revisão/instrução no prompt), o que é o comportamento seguro.

    Só troca o texto da CHAMADA em si (`->metodo(`, `.metodo(`,
    `Classe::metodo(`), preservando o prefixo (`->`/`.`/`::`).

    Retorna (codigo_corrigido, lista_de_correcoes_aplicadas).
    """
    if not class_methods_index or not metodos_suspeitos:
        return codigo, []

    correcoes = []
    for classe, errado in metodos_suspeitos:
        candidatos_da_classe = class_methods_index.get(classe)
        if not candidatos_da_classe:
            continue  # classe fora do índice (ou sem métodos capturados) — não arrisca
        candidatos = difflib.get_close_matches(errado, candidatos_da_classe, n=1, cutoff=CUTOFF_METODO_AUTOMATICO)
        if not candidatos:
            continue
        certo = candidatos[0]
        padrao = re.compile(r'(->|\.|::)\s*' + re.escape(errado) + r'\s*\(')
        codigo, n = padrao.subn(r'\1' + certo + '(', codigo)
        if n:
            correcoes.append(f"{classe}::{errado} → {classe}::{certo}")
    return codigo, correcoes


def _corrigir_includes_automaticamente(
    codigo: str,
    class_header_index: dict,
    collisions: dict,
    headers_whitelist: set,
) -> tuple:
    """
    Correção determinística pós-geração — não depende do LLM obedecer a
    instrução de correção no prompt (na prática, ele não obedece de forma
    confiável neste modelo local: chegou a repetir o mesmo header errado em
    3 tentativas seguidas).

    1. Remove includes "lixo" conhecidos (ex: "NeoPZ.h") e includes "chutados"
       (<NomeDaClasse>.h) que não existem na whitelist real de headers.
    2. Para cada classe TPZ usada no código que está no índice determinístico
       (e não é ambígua/collision), garante que o #include correto está
       presente — injetando-o se estiver faltando.

    Retorna (codigo_corrigido, lista_de_correcoes_aplicadas).
    """
    if not class_header_index:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    necessarios = {
        classe: Path(class_header_index[classe]).name
        for classe in usadas
        if classe not in collisions and class_header_index.get(classe)
    }

    linhas = codigo.split("\n")

    def _includes_atuais(linhas: list) -> dict:
        atuais = {}
        for i, linha in enumerate(linhas):
            m = re.search(r'#include\s*[<"]([^>"]+\.h)[>"]', linha)
            if m:
                atuais.setdefault(Path(m.group(1)).name, i)
        return atuais

    atuais = _includes_atuais(linhas)
    candidatos_chute = {f"{c.lower()}.h" for c in necessarios}
    linhas_remover = {
        idx for nome, idx in atuais.items()
        if nome.lower() in INCLUDES_LIXO_CONHECIDOS
        or (nome.lower() in candidatos_chute and nome not in headers_whitelist)
    }
    if linhas_remover:
        linhas = [l for i, l in enumerate(linhas) if i not in linhas_remover]

    if not necessarios:
        return "\n".join(linhas), []

    atuais = _includes_atuais(linhas)
    faltando = {c: h for c, h in necessarios.items() if h not in atuais}
    if not faltando:
        return "\n".join(linhas), []

    posicoes_include = [i for i, l in enumerate(linhas) if re.match(r'\s*#include\b', l)]
    ultimo_include_idx = max(posicoes_include, default=-1)

    novas = [f'#include "{h}"' for h in sorted(set(faltando.values()))]
    if ultimo_include_idx >= 0:
        linhas = linhas[:ultimo_include_idx + 1] + novas + linhas[ultimo_include_idx + 1:]
    else:
        linhas = novas + linhas

    correcoes = [f'{c}: + #include "{h}"' for c, h in faltando.items()]
    return "\n".join(linhas), correcoes


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
    wiki_db=None,
    methods_whitelist: set = None,
    class_methods_index: dict = None,
) -> dict:
    """
    Executa o pipeline completo:
    recuperação → formatação → geração → validação → retry se necessário.
    """
    class_header_index = class_header_index or {}
    collisions = collisions or {}
    methods_whitelist = methods_whitelist or set()
    class_methods_index = class_methods_index or {}

    classes_alucinadas = None
    includes_errados = None
    includes_por_classe = None
    metodos_suspeitos = None
    correcoes_automaticas = []

    for tentativa in range(1, MAX_RETRIES + 2):
        print(f"  [Tentativa {tentativa}] Buscando contexto e gerando resposta...")

        # 1. Recupera documentos relevantes
        h_docs, e_docs, w_docs, fontes = _recuperar_contexto(pergunta, headers_db, examples_db, wiki_db)

        # 2. Formata o contexto
        contexto = _formatar_contexto(h_docs, e_docs, w_docs)

        # 3. Monta o prompt (com correções se for retry)
        prompt = _montar_prompt(
            pergunta, contexto, system_base, whitelist, headers_whitelist,
            classes_alucinadas, includes_errados, includes_por_classe,
            metodos_suspeitos, methods_whitelist,
        )

        # 4. Chama o modelo
        resposta = llm.invoke(prompt)

        # 4.5 Correção determinística pós-geração — não depende do LLM obedecer
        #     a instrução de correção no prompt (na prática ele não obedece de
        #     forma confiável: chegou a repetir o mesmo nome/header errado em
        #     3 tentativas seguidas mesmo com a sugestão certa no prompt).
        #     Só se aplica quando a resposta de fato contém código — em
        #     respostas de prosa (ex: "o que é a classe X") a classe é só
        #     citada no texto, não usada, então não faz sentido exigir/injetar
        #     #include ou reescrever chamadas.
        #
        #     Ordem importa: classe primeiro (afeta o binding variável->classe
        #     usado na correção de método, e afeta qual header é "o certo"),
        #     depois método, depois include por último.
        tem_codigo = _resposta_contem_codigo(resposta)
        correcoes_automaticas = []
        if tem_codigo:
            resposta, correcoes_classes = _corrigir_classes_automaticamente(resposta, whitelist)
            correcoes_automaticas.extend(correcoes_classes)

            metodos_suspeitos_pre_correcao = _validar_metodos(resposta, methods_whitelist, whitelist)
            resposta, correcoes_metodos = _corrigir_metodos_automaticamente(
                resposta, metodos_suspeitos_pre_correcao, class_methods_index,
            )
            correcoes_automaticas.extend(correcoes_metodos)

            resposta, correcoes_includes = _corrigir_includes_automaticamente(
                resposta, class_header_index, collisions, headers_whitelist,
            )
            correcoes_automaticas.extend(correcoes_includes)

            if correcoes_automaticas:
                print(f"  🔧 Corrigido automaticamente: {', '.join(correcoes_automaticas)}")

        # 5. Valida classes (sempre) E includes/métodos (só quando há código de fato)
        classes_alucinadas = _validar_codigo(resposta, whitelist)
        if tem_codigo:
            includes_errados = _validar_includes(resposta, headers_whitelist)
            includes_por_classe = _validar_includes_por_classe(resposta, class_header_index, collisions)
            metodos_suspeitos = _validar_metodos(resposta, methods_whitelist, whitelist)
        else:
            includes_errados = {}
            includes_por_classe = {}
            metodos_suspeitos = []

        if not classes_alucinadas and not includes_errados and not includes_por_classe and not metodos_suspeitos:
            print("  ✅ Validação OK — classes, headers e métodos existem e estão corretos no NeoPZ!")
            return {
                "resposta":             resposta,
                "valido":               True,
                "alucinacoes":          [],
                "includes":             {},
                "includes_por_classe":  {},
                "metodos_suspeitos":    [],
                "correcoes_automaticas": correcoes_automaticas,
                "fontes":               fontes,
                "tentativas":           tentativa,
            }

        if classes_alucinadas:
            print(f"  ⚠️  Classes não encontradas: {', '.join(classes_alucinadas)}")
        if includes_errados:
            print(f"  ⚠️  Headers não encontrados: {', '.join(includes_errados.keys())}")
        if includes_por_classe:
            print(f"  ⚠️  Header errado/faltando para classe: {includes_por_classe}")
        if metodos_suspeitos:
            print(f"  ⚠️  Métodos não encontrados: {metodos_suspeitos}")

        if tentativa >= MAX_RETRIES + 1:
            print("  ⚠️  Limite de tentativas atingido.")
            break

        print("  ↩️  Corrigindo automaticamente na próxima tentativa...")

    return {
        "resposta":             resposta,
        "valido":               False,
        "alucinacoes":          classes_alucinadas or [],
        "includes":             includes_errados or {},
        "includes_por_classe":  includes_por_classe or {},
        "metodos_suspeitos":    metodos_suspeitos or [],
        "correcoes_automaticas": correcoes_automaticas,
        "fontes":               fontes,
        "tentativas":           tentativa,
    }


# ── Loop de conversa ───────────────────────────────────────────────────────────

def main():
    print("Carregando modelos e banco de dados...")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    headers_db, examples_db, wiki_db = _carregar_bancos(embeddings)
    whitelist          = _carregar_whitelist()
    headers_whitelist  = _carregar_headers_whitelist()
    class_header_index = _carregar_class_header_index()
    collisions         = _carregar_collisions()
    methods_whitelist  = _carregar_methods_whitelist()
    class_methods_index = _carregar_class_methods_index()
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
            class_header_index, collisions, wiki_db,
            methods_whitelist, class_methods_index,
        )

        print("\nAssistente LabMeC:\n")
        print(resultado["resposta"])
        print()

        # Status de validação
        if resultado["correcoes_automaticas"]:
            print(f"🔧 Headers corrigidos automaticamente: {', '.join(resultado['correcoes_automaticas'])}")
        if resultado["alucinacoes"]:
            print(f"⚠️  Classes não verificadas: {', '.join(resultado['alucinacoes'])}")
        if resultado["includes"]:
            print(f"⚠️  Headers não verificados: {', '.join(resultado['includes'].keys())}")
        if resultado["includes_por_classe"]:
            faltando_fmt = ", ".join(f"{c} → {h}" for c, h in resultado["includes_por_classe"].items())
            print(f"⚠️  Header incorreto/faltando para classe (índice determinístico): {faltando_fmt}")
        if resultado["metodos_suspeitos"]:
            metodos_fmt = ", ".join(f"{c}::{m}" for c, m in resultado["metodos_suspeitos"])
            print(f"⚠️  Métodos não encontrados no NeoPZ (whitelist global): {metodos_fmt}")
        if (not resultado["alucinacoes"] and not resultado["includes"]
                and not resultado["includes_por_classe"] and not resultado["metodos_suspeitos"]):
            print("✅ Resposta validada — classes, headers e métodos existem e estão corretos no NeoPZ")

        # Fontes usadas
        fontes_curtas = [Path(f).name for f in resultado["fontes"]]
        print(f"📄 Fontes ({resultado['tentativas']} tentativa(s)): {', '.join(fontes_curtas)}")
        print("-" * 50 + "\n")


if __name__ == "__main__":
    main()