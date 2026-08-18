from pathlib import Path
import datetime
import os
import re
import json
import difflib
import shutil
import subprocess
import tempfile

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

from cpp_parser import DIRS_LEGADO, find_tpz_classes_in_code, find_suspicious_method_calls

# ── Configurações ──────────────────────────────────────────────────────────────
OLLAMA_MODEL           = "qwen2.5-coder:7b"

# Janela de contexto pedida ao Ollama. SEM isso, o servidor usa o default dele
# (2048–4096 tokens dependendo da versão) e TRUNCA o prompt em silêncio — com
# 4 headers (~2500 chars) + 4 exemplos (~2000) + 3 páginas inteiras de wiki, o
# prompt passa fácil de 4096 tokens, e parte das regras/do contexto recuperado
# pode nem chegar ao modelo (o que explica em parte ele "ignorar" instruções
# de correção). qwen2.5-coder suporta 32k; 16k dá folga sem estourar memória.
NUM_CTX                = 8192

EMBED_MODEL            = "BAAI/bge-base-en-v1.5"

# Índice PRÓPRIO desta branch (gerado contra o NeoPZ do develop). O
# banco_chroma/ não é versionado, então ele é compartilhado entre branches no
# mesmo working tree: se as duas usassem o mesmo diretório, reindexar aqui
# apagaria o índice da main (~360 MB, minutos de embedding) e a main passaria
# a validar contra a whitelist do develop sem ninguém perceber. Diretórios
# separados deixam as duas coexistirem — trocar de branch não exige reindexar.
INDEX_DIR              = Path("./banco_chroma_develop")
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

# Segundo nível da whitelist: classes que SÓ existem nos diretórios legados
# do NeoPZ (needrefactor/, PerfTests/) — existem de verdade (usar não é
# alucinação nem bloqueia), mas geram aviso "prefira a API atual".
# Gerado pelo indexer (build_tiered_class_whitelist).
LEGACY_CLASSES_FILE     = INDEX_DIR / "legacy_classes.txt"

# Log de interações em JSONL (uma linha JSON por pergunta respondida).
# Motivo: com revisão humana ocasional, os pares (pergunta, resposta validada)
# viram de graça o conjunto de avaliação — e um eventual dataset de
# fine-tuning — sem trabalho extra de curadoria depois.
LOG_INTERACOES_FILE     = Path("./logs/interacoes.jsonl")

# Mapa CURADO {classe_antiga: classe_atual} de renomeações conhecidas entre
# versões do NeoPZ (ex: TPZMatLaplacian → TPZMatPoisson na refatoração de
# materiais). O modelo decorou a API antiga no treino — é o erro mais
# previsível que existe, e o difflib não resolve: sugere por semelhança de
# STRING (já empurrou 'TPZMatLaplacian' para 'TPZMatPlaca2', material de
# placa, num problema de Poisson). Arquivo editável à mão; ver _carregar_renames.
RENAMES_FILE            = Path("./renames.json")
TEMPERATURE            = 0.1
MAX_RETRIES            = 2          # tentativas extras ao detectar alucinação
K_HEADERS              = 4          # chunks de declaração de classe a recuperar
K_EXAMPLES             = 4          # chunks de exemplo de uso a recuperar
EXAMPLE_POOL_MULT      = 6          # tamanho do pool buscado antes do boost por classe citada

COL_HEADERS  = "neopz_headers"
COL_EXAMPLES = "neopz_examples"
COL_WIKI     = "neopz_wiki"        # documentação curada

K_WIKI       = 3                   # chunks da wiki a recuperar por consulta

# Vagas de K_WIKI reservadas para documentos que NÃO são receitas (doc_fluxo).
# As receitas são longas e semanticamente densas, então vencem qualquer
# disputa por similaridade: numa pergunta sobre "Darcy em H1" as 3 vagas
# foram ocupadas pelas receitas de poisson/elasticidade/darcy-misto e o
# catálogo problema→material — o ÚNICO documento que diz "Darcy em H1 →
# TPZDarcyFlow" — ficou de fora, justamente na pergunta em que era decisivo.
# O problema piora a cada receita nova, por isso a reserva é fixa.
K_WIKI_CONCEITOS = 1

# Headers "chute" que o modelo inventa e que NÃO existem no projeto — removidos
# automaticamente na correção pós-geração (ver _corrigir_includes_automaticamente).
INCLUDES_LIXO_CONHECIDOS = {"neopz.h", "pz.h", "pzc.h"}

# Headers da biblioteca padrão C que terminam em .h — NUNCA validar contra a
# whitelist do NeoPZ (ver _validar_includes: <math.h> era marcado como "header
# não encontrado" e disparava retries à toa).
HEADERS_SISTEMA = {"math.h", "stdio.h", "stdlib.h", "string.h", "assert.h",
                   "time.h", "float.h", "limits.h", "ctype.h", "stddef.h"}

# ── Compilação do código gerado ───────────────────────────────────────────────
# A whitelist responde "esse nome existe em ALGUM lugar do NeoPZ"; o compilador
# responde "esse método existe NESTA classe, com ESTA assinatura". A diferença
# é exatamente o buraco que METHODS_WHITELIST_FILE deixa de propósito:
# `mat->SetElasticity(E, nu)` num TPZDarcyFlow passa na whitelist global
# (SetElasticity existe — em TPZElasticity2D) e o g++ recusa em 0,5 s.
#
# Custo medido com -fsyntax-only (sem link) nas 4 receitas de
# reference_solutions/: 0,50–0,64 s cada, contra dezenas de segundos de geração
# no 7b local. Compilar é ruído no orçamento do pipeline.
#
# Instalações candidatas, em ordem: a do develop (que ESTA branch indexa) e a de
# 2022 como fallback (que a branch main valida). Casar a instalação com o índice
# importa: compilar contra 2022 o código gerado a partir da whitelist do develop
# acusaria como erro classe nova que existe de verdade. NEOPZ_PREFIX no
# ambiente sobrescreve.
NEOPZ_PREFIXES = (
    Path.home() / "opt" / "neopz-develop",
    Path("/opt/neopz"),
)
# Mesmo compilador que compilou o NeoPZ (no laboratório: g++ do MacPorts) — ver
# README. Em -fsyntax-only não há link para quebrar, mas libstdc++ e libc++
# divergem o bastante nos headers para gerar erro fantasma.
NEOPZ_CXX           = "/opt/local/bin/g++"
TIMEOUT_COMPILACAO  = 60   # s — uma TU leva ~0,5 s; isto é guarda contra travar
MAX_ERROS_RELATADOS = 5    # o compilador cascateia; o 7b não precisa de 40 linhas
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


def _carregar_legacy_classes() -> set:
    """Classes que só existem no legado (ver LEGACY_CLASSES_FILE). Opcional —
    sem o arquivo (indexer antigo), o pipeline segue sem o aviso."""
    if not LEGACY_CLASSES_FILE.exists():
        return set()
    classes = set(LEGACY_CLASSES_FILE.read_text(encoding='utf-8').splitlines()) - {""}
    if classes:
        print(f"  Classes da API antiga (aviso, não erro): {len(classes)}")
    return classes


def _carregar_renames() -> dict:
    """
    Carrega o mapa curado de renomeações (ver comentário em RENAMES_FILE).
    Chaves começando com '_' são ignoradas (servem de comentário no JSON).
    Arquivo opcional — sem ele o pipeline segue só com difflib.
    """
    if not RENAMES_FILE.exists():
        return {}
    dados = json.loads(RENAMES_FILE.read_text(encoding='utf-8'))
    renames = {k: v for k, v in dados.items() if not k.startswith("_")}
    if renames:
        print(f"  Renomeações conhecidas: {len(renames)} mapeadas")
    return renames


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


# Diretórios do NeoPZ que contêm a API ANTIGA (pré-refatoração) ou código de
# benchmark — o modelo já tende à API velha pelo treino; o retrieval não
# precisa reforçar isso trazendo justamente esses chunks primeiro.
_DIRS_LEGADO = ("needrefactor", "PerfTests")

# Diretórios que NÃO são a biblioteca. Diferente do legado, é código VIVO: os
# .cpp de UnitTest_PZ/TestDeRham compilam limpo contra o NeoPZ de hoje. O que
# eles não são é API — o CMake os monta com add_unit_test(), que expande para
# add_executable(), nunca para target_sources(pz). Viram binário de teste
# separado; instalação nenhuma os expõe, com flag nenhuma ligada.
#
# Por que aqui e não excluídos no indexer como _DIRS_LEGADO: para 10 classes
# (TPZMatDeRham*, TPZSurface, TPZMatL2Product, TPZHybridPoissonCollapsed) o
# header de teste é a ÚNICA declaração no repositório inteiro — apagá-los
# deixaria a pergunta explicativa sem contexto algum, pior que hoje. Ficam
# como RESERVA: no fim do pool, atrás de qualquer chunk da API real, e
# etiquetados na resposta (ver fontes_nao_api).
_DIRS_NAO_API = ("UnitTest_PZ", "Publications", "PerfUtil")


def _fora_da_api(source: str) -> str:
    """
    Etiqueta do que ESTE chunk é, ou "" quando é API instalável da biblioteca.

    Casa por COMPONENTE do caminho, não por substring como antes: 'PerfUtil'
    dentro de uma string casaria com um futuro 'Util/PerfUtilTimer.h', que é
    API de verdade.
    """
    partes = Path(source).parts
    if any(d in partes for d in _DIRS_LEGADO):
        return "legado"
    if any(d in partes for d in _DIRS_NAO_API):
        return "teste/benchmark"
    return ""


def _despriorizar_legado(docs: list) -> list:
    """Reordenação estável: empurra para o fim do pool os chunks que não são da
    API instalável — legado (_DIRS_LEGADO) e código de teste/benchmark
    (_DIRS_NAO_API). Eles continuam disponíveis (podem ser a única fonte de uma
    classe), só perdem a prioridade para a API atual."""
    atuais, fora = [], []
    for doc in docs:
        (fora if _fora_da_api(doc.metadata.get("source", "") or "") else atuais).append(doc)
    return atuais + fora


_PERGUNTA_EXPLICATIVA_RE = re.compile(
    r'\b(o que (é|e|faz|são|sao)|para que serve|explique|explica|como funciona|'
    r'qual (a |é a |e a )?diferen[çc]a)\b', re.IGNORECASE)
_PEDIDO_DE_CODIGO_RE = re.compile(
    r'\b(c[óo]digo|programa|escreva|implemente|crie|criar|gere|gerar|resolva|resolver|'
    r'monte|montar|exemplo completo)\b', re.IGNORECASE)


def _pergunta_e_explicativa(pergunta: str) -> bool:
    """
    Heurística: a pergunta pede EXPLICAÇÃO (e não código)?
    Usada para excluir as receitas (doc_fluxo — programas completos) do
    retrieval nessas perguntas: o modelo 7b tende a colar a receita INTEIRA
    como "exemplo de uso" mesmo quando irrelevante (aconteceu de verdade: a
    explicação de TPZInt1d veio com a receita do Poisson inteira, que não usa
    a classe em linha nenhuma). Instrução no prompt não bastou — o filtro
    determinístico no retrieval corta o problema na origem: sem programa
    completo no contexto, não há o que colar.
    """
    return (bool(_PERGUNTA_EXPLICATIVA_RE.search(pergunta))
            and not _PEDIDO_DE_CODIGO_RE.search(pergunta))


def _reservar_vagas_conceitos(docs: list, k: int, reservadas: int) -> list:
    """
    Ordena por prioridade (alta > media) e depois garante a reserva de vagas
    para documentos que NÃO são receitas (doc_fluxo). Isso garante que o
    catálogo de materiais (que tem prioridade alta, mas não é receita) não seja
    engolido por 3 receitas de prioridade alta.
    """
    alta = [d for d in docs if d.metadata.get("prioridade") == "alta"]
    media = [d for d in docs if d.metadata.get("prioridade") != "alta"]
    docs_priorizados = alta + media

    if reservadas <= 0:
        return docs_priorizados[:k]

    nao_receitas = [d for d in docs_priorizados if d.metadata.get("tipo") != "doc_fluxo"]
    escolhidos = nao_receitas[:reservadas]
    vistos = {d.page_content for d in escolhidos}
    for doc in docs_priorizados:
        if len(escolhidos) >= k:
            break
        if doc.page_content not in vistos:
            vistos.add(doc.page_content)
            escolhidos.append(doc)
    return escolhidos[:k]


def _dedup_docs(docs: list) -> list:
    """Remove documentos duplicados preservando a ordem (chave = conteúdo)."""
    vistos, unicos = set(), []
    for doc in docs:
        if doc.page_content not in vistos:
            vistos.add(doc.page_content)
            unicos.append(doc)
    return unicos


def _buscar_declaracoes_por_classe(headers_db, pergunta: str, classes: set, limite: int) -> list:
    """
    Busca DETERMINÍSTICA por metadata: para cada classe, recupera o chunk de
    declaração dela via filtro exato (metadata `classe` == nome), independente
    de a busca semântica trazer ou não. O _boost_por_classe só REORDENA o pool
    que o MMR retornou — se a declaração da classe citada não veio no pool, o
    boost não faz nada; este fetch garante que ela entra no contexto.
    """
    docs = []
    for classe in sorted(classes)[:limite]:
        try:
            hits = headers_db.similarity_search(pergunta, k=1, filter={"classe": classe})
        except Exception:
            hits = []
        docs.extend(hits)
    return docs


def _recuperar_contexto(pergunta: str, headers_db, examples_db, wiki_db=None,
                        explicativa: bool = None) -> tuple:
    """
    Busca nas coleções com MMR (pool ampliado) e depois reordena (boost)
    priorizando chunks cuja classe bate com alguma classe TPZ citada na
    pergunta. Para classes citadas EXPLICITAMENTE, a declaração é buscada de
    forma garantida via filtro de metadata (não depende do pool do MMR).
    Se wiki_db estiver disponível, inclui documentação curada.
    Retorna (h_docs, e_docs, w_docs, fontes).
    """
    classes_citadas = find_tpz_classes_in_code(pergunta)

    # Fetch garantido das declarações das classes citadas na pergunta
    garantidos = _buscar_declaracoes_por_classe(headers_db, pergunta, classes_citadas, limite=K_HEADERS)

    pool_headers = max(K_HEADERS * EXAMPLE_POOL_MULT, K_HEADERS)
    h_pool = headers_db.max_marginal_relevance_search(
        pergunta, k=pool_headers, fetch_k=pool_headers * 2
    )
    h_docs = _dedup_docs(
        garantidos + _boost_por_classe(_despriorizar_legado(h_pool), classes_citadas, "classe")
    )[:K_HEADERS]

    pool_examples = max(K_EXAMPLES * EXAMPLE_POOL_MULT, K_EXAMPLES)
    e_pool = examples_db.max_marginal_relevance_search(
        pergunta, k=pool_examples, fetch_k=pool_examples * 2
    )
    e_docs = _boost_por_classe(_despriorizar_legado(e_pool), classes_citadas, "classes_usadas")[:K_EXAMPLES]

    # Wiki — documentação curada (API real, conceitos, bugs conhecidos)
    w_docs = []
    if wiki_db is not None:
        if explicativa is None:
            explicativa = _pergunta_e_explicativa(pergunta)
        w_pool = wiki_db.max_marginal_relevance_search(
            pergunta, k=K_WIKI * EXAMPLE_POOL_MULT, fetch_k=K_WIKI * EXAMPLE_POOL_MULT * 2
        )
        if explicativa:
            # Pergunta explicativa: receitas fora do contexto (ver
            # _pergunta_e_explicativa) — conceitos/código da wiki continuam
            w_pool = [d for d in w_pool if d.metadata.get("tipo") != "doc_fluxo"]
        w_boosted = _boost_por_classe(w_pool, classes_citadas, "classes_usadas")
        w_docs = _reservar_vagas_conceitos(w_boosted, K_WIKI, K_WIKI_CONCEITOS)

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


def _formatar_historico(historico: list, max_trocas: int = 3, max_chars_resposta: int = 1200) -> str:
    """
    Renderiza as últimas trocas da conversa para dar contexto a follow-ups
    ("e como eu refino essa malha?"). Respostas longas são truncadas: o que
    o follow-up precisa é do ASSUNTO discutido, não do código inteiro — e o
    orçamento de contexto (NUM_CTX) tem que sobrar para o RAG.
    `historico` é uma lista de pares (pergunta, resposta).
    """
    if not historico:
        return ""
    partes = []
    for pergunta_ant, resposta_ant in historico[-max_trocas:]:
        resposta_ant = resposta_ant or ""
        if len(resposta_ant) > max_chars_resposta:
            resposta_ant = resposta_ant[:max_chars_resposta] + "\n[... resposta truncada ...]"
        partes.append(f"Aluno: {pergunta_ant}\nAssistente: {resposta_ant}")
    return (
        "\n\nHISTÓRICO DA CONVERSA (só contexto — a tarefa atual está no fim):\n"
        + "\n---\n".join(partes)
    )


def _classes_do_contexto(h_docs: list, e_docs: list, w_docs: list = None) -> set:
    """
    Classes TPZ presentes nos chunks recuperados — usadas na lista de
    referência do prompt. São as classes relevantes para ESTA pergunta, ao
    contrário do antigo sorted(whitelist)[:50], que devolvia sempre as mesmas
    50 primeiras em ordem alfabética (quase nunca ligadas à pergunta).
    """
    classes = set()
    for doc in h_docs or []:
        c = doc.metadata.get("classe", "") or ""
        if c:
            classes.add(c)
    for doc in (e_docs or []) + (w_docs or []):
        valor = doc.metadata.get("classes_usadas", "") or ""
        classes.update(x.strip() for x in valor.split(",") if x.strip())
    return classes


# ── Sugestões de correção (difflib) ──────────────────────────────────────────────

def _sugerir_correcoes(alucinadas: list, whitelist: set, cutoff: float = 0.6) -> dict:
    """Para cada item inexistente, busca os nomes reais mais parecidos.
    Recebe a whitelist já filtrada para destinos utilizáveis quando isso
    importa — ver _whitelist_utilizavel."""
    sugestoes = {}
    for item in alucinadas:
        sugestoes[item] = difflib.get_close_matches(item, whitelist, n=3, cutoff=cutoff)
    return sugestoes


def _whitelist_utilizavel(whitelist: set, class_header_index: dict) -> set:
    """
    Subconjunto da whitelist que pode servir de DESTINO — de correção
    automática, de sugestão no prompt e de reforço de contexto no retry.

    São duas perguntas diferentes e a whitelist só responde a primeira:

      "esse nome existe no NeoPZ?"     → precisa manter needrefactor e cia.,
                                         senão "o que é TPZBurger?" (prosa
                                         sobre classe real) vira acusação de
                                         alucinação;
      "posso mandar o modelo usar?"    → não, se o header não existe aqui.

    Reescrever o chute do modelo PARA uma classe que não compila em máquina
    nenhuma troca um erro por outro pior, ainda por cima carimbado "corrigido
    automaticamente". Achado real ao conferir a whitelist desta branch:
    'TPZBurguer' virava 'TPZBurger' (needrefactor) e 'TPZMatDeRhamH1D' virava
    'TPZMatDeRhamH1' (UnitTest_PZ) — 180 das 658 classes eram destino assim.

    Classe fora do índice classe→header fica: não saber onde ela mora não é
    motivo para descartá-la. Sem índice nenhum, devolve a whitelist inteira
    (comportamento anterior).
    """
    if not class_header_index:
        return whitelist
    utilizavel = set()
    for classe in whitelist:
        caminho = class_header_index.get(classe)
        if caminho is None or not _motivo_indisponivel(caminho):
            utilizavel.add(classe)
    return utilizavel


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
    erros_compilacao: list = None,
    classes_contexto: set = None,
    renames: dict = None,
    historico: list = None,
    destinos: set = None,
) -> str:
    """
    Monta o prompt completo como string.
    Se houver classes alucinadas ou includes errados, adiciona instrução de correção.

    destinos: whitelist filtrada para o que a instalação realmente tem (ver
    _whitelist_utilizavel). É o que pode ser OFERECIDO ao modelo — sugerir uma
    classe cujo header não existe aqui é mandá-lo escrever código que não
    compila. Ausente, cai na whitelist inteira.
    """
    destinos = whitelist if destinos is None else destinos

    # Lista de referência: classes presentes no contexto recuperado (relevantes
    # para esta pergunta). Cai para a whitelist global só se o contexto não
    # tiver nenhuma classe identificada.
    referencia = classes_contexto or destinos
    classes_reais = ", ".join(sorted(referencia)[:40]) if referencia else "—"

    instrucao_correcao = ""

    # Correção de classes
    if classes_alucinadas:
        renames = renames or {}
        sugestoes = _sugerir_correcoes(classes_alucinadas, destinos)
        linhas = []
        for classe, matches in sugestoes.items():
            if classe in renames and renames[classe] in destinos:
                linhas.append(
                    f"  - '{classe}' foi RENOMEADA no NeoPZ atual. Use '{renames[classe]}' no lugar."
                )
            elif matches:
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

    # Erros do COMPILADOR — o único bloco desta função que não é sugestão:
    # os outros dizem "provavelmente errado" (semelhança de string, whitelist
    # global); estes são a resposta do g++ sobre ESTE código. Vêm por último
    # de propósito: quando existem, são o motivo real do retry.
    if erros_compilacao:
        instrucao_correcao += (
            "\n\n❌ O COMPILADOR (g++) RECUSOU O CÓDIGO ANTERIOR:\n"
            + "\n".join(f"  - {e}" for e in erros_compilacao)
            + "\nCada linha acima é uma API que NÃO existe do jeito que você escreveu.\n"
            "Atenção a 'has no member named X in Y' / 'no member named X': o método X\n"
            "NÃO pertence à classe Y — mesmo que exista em OUTRA classe do NeoPZ.\n"
            "Use somente os métodos que aparecem na declaração da própria classe,\n"
            "no contexto acima. Não troque o método por outro 'parecido' sem conferir."
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

Classes TPZ reais relacionadas a esta tarefa (todas existem no NeoPZ):
{classes_reais}
{instrucao_correcao}

INSTRUÇÕES:
- Use apenas classes cujos headers aparecem no contexto
- Use apenas métodos visíveis nas declarações de classe acima
- Prefira SEMPRE a API atual do NeoPZ (ex: TPZMatPoisson, std::function em
  SetForcingFunction) em vez da API antiga (TPZDummyFunction, TPZMatPoisson3d)
- Sempre inclua os #include específicos necessários
- Siga os padrões dos exemplos de uso
- Se não tiver certeza do nome exato, escreva: // TODO: verificar nome
- Se o usuário pedir uma EXPLICAÇÃO (ex: "o que é a classe X"), responda com
  texto didático; código só se for um trecho CURTO usando a própria classe
  explicada. NUNCA cole um programa completo de outro assunto como "exemplo"
- Se o usuário pedir código/programa, gere com explicações do que cada parte faz
- Combine texto explicativo e código quando fizer sentido
- NUNCA afirme que o código que você gerou foi compilado, testado ou executado
  com sucesso — você não compilou nada. Se a documentação do contexto disser
  que um exemplo foi verificado, isso vale para AQUELE exemplo, não para o seu

{contexto}{_formatar_historico(historico)}

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


_INCLUDE_RE       = re.compile(r'#include\s*[<"]([^>"]+\.h)[>"]')
_INCLUDE_ASPAS_RE = re.compile(r'#include\s*"([^"]+\.h)"')


def _extrair_includes(codigo: str, apenas_aspas: bool = False) -> list:
    """
    Extrai nomes de headers .h incluídos no código (ex: 'NeoPZ.h').

    apenas_aspas=True limita a #include "..." — usado na VALIDAÇÃO: includes
    de sistema em <...> (ex: <math.h>) não são do NeoPZ e eram marcados como
    "header não encontrado", disparando retries à toa. Para checar PRESENÇA
    de um include (correção automática), as duas formas contam.
    """
    regex = _INCLUDE_ASPAS_RE if apenas_aspas else _INCLUDE_RE
    return [Path(inc).name for inc in regex.findall(codigo)]


def _includes_com_caminho(codigo: str) -> dict:
    """
    basename -> caminho exatamente como escrito no #include (ex:
    'TPZMatPoisson.h' -> 'Poisson/TPZMatPoisson.h', ou -> 'TPZMatPoisson.h'
    se o aluno/modelo escreveu sem o prefixo de família). Repetido, fica a
    ÚLTIMA ocorrência.

    Diferente de _extrair_includes: aqui o caminho NÃO é reduzido ao
    basename, porque para headers da API nova (ver _include_para_header) o
    basename sozinho parece presente mas não é o arquivo que compila —
    "TPZMatPoisson.h" e "Poisson/TPZMatPoisson.h" têm o mesmo basename e são
    includes DIFERENTES para o compilador.
    """
    return {Path(inc).name: inc for inc in _INCLUDE_RE.findall(codigo)}


def _validar_includes(codigo: str, headers_whitelist: set) -> dict:
    """
    Verifica os #include .h contra a whitelist de headers reais.
    Só valida includes entre aspas — <...> é sistema/externo, não é nosso
    para validar (ver _extrair_includes). Retorna {include_errado:
    [sugestões]} — dict vazio = tudo OK.
    """
    if not headers_whitelist:
        return {}
    usados = _extrair_includes(codigo, apenas_aspas=True)
    problemas = {}
    for inc in usados:
        if inc in HEADERS_SISTEMA:
            continue  # stdlib entre aspas (raro, mas compila) — não é alucinação
        if inc not in headers_whitelist:
            problemas[inc] = difflib.get_close_matches(inc, headers_whitelist, n=3, cutoff=0.5)
    return problemas


def _include_para_header(caminho: str) -> str:
    """
    Forma COMPILÁVEL do #include para um header do índice classe→header.

    Descoberto ao compilar as receitas contra o NeoPZ instalado: o NeoPZ
    propaga como include path só os diretórios de topo (Mesh/, Pre/,
    Material/, ...). Para headers da API nova de materiais, que ficam em
    subpastas (Material/Poisson/TPZMatPoisson.h), o include precisa do
    prefixo da família — '#include "TPZMatPoisson.h"' (só o basename) NÃO
    compila; o certo é '#include "Poisson/TPZMatPoisson.h"'. Para os demais
    diretórios (sem subpasta instalada), o basename continua correto.
    """
    partes = Path(caminho).parts
    if len(partes) >= 3 and partes[0] == "Material":
        return "/".join(partes[1:])
    return Path(caminho).name


# Diretórios que existem no source do NeoPZ mas que instalação NENHUMA expõe.
# Não é opção de build, é fato da revisão — conferido nos CMakeLists do develop
# (852a5116c) E do 2022 (4c6b6d277):
#   needrefactor/  não é citado em nenhum CMakeLists: não compila, não instala,
#                  e os .cpp de lá nem compilam mais (incluem pzbndcond.h, que
#                  sumiu na refatoração de materiais, e pedem
#                  HDivFamily::EDefault, que não existe mais no enum). A única
#                  referência viva no NeoPZ é um include COMENTADO em
#                  SubStruct/tpzgensubstruct.cpp.
#   os demais      são programas de teste/benchmark/companion de artigo, não a
#                  biblioteca — não há o que instalar.
# Vale em qualquer máquina, por isso é constante e não sonda.
_DIRS_NUNCA_INSTALADOS = ("needrefactor", "PerfTests", "UnitTest_PZ",
                          "Publications", "PerfUtil")

_INDISPONIVEL_CACHE = {}


def _motivo_indisponivel(caminho: str):
    """
    Por que o header dessa classe NÃO pode ser incluído aqui — ou None se pode.

    São duas perguntas diferentes, nesta ordem:

    1. UNIVERSAL — o diretório está em _DIRS_NUNCA_INSTALADOS? Então nenhuma
       instalação do NeoPZ tem esse header, em máquina nenhuma. Responder isso
       não exige NeoPZ instalado.
    2. DESTA MÁQUINA — o include resolve contra os -I que a instalação daqui
       propaga? Plasticidade é o caso típico: BUILD_PLASTICITY_MATERIALS é
       opção de build, então as mesmas 72 classes existem na instalação de quem
       ligou a flag e faltam na de quem não ligou. Por isso é SONDA e não lista
       gravada — uma lista fixa mentiria em metade das instalações.

    Sem NeoPZ instalado (Caminho A do README) só a pergunta 1 é respondível; a 2
    devolve None e o comportamento fica igual ao de hoje.
    """
    if any(p in _DIRS_NUNCA_INSTALADOS for p in Path(caminho).parts[:-1]):
        return "não faz parte do build do NeoPZ"

    prefix = _neopz_prefix()
    if prefix is None:
        return None

    chave = (str(prefix), caminho)
    if chave not in _INDISPONIVEL_CACHE:
        dirs = [Path(f[2:]) for f in _include_flags(prefix)]
        if not dirs:
            return None  # sem os -I da instalação não dá para afirmar nada
        forma = _include_para_header(caminho)
        _INDISPONIVEL_CACHE[chave] = (None if any((d / forma).is_file() for d in dirs)
                                      else "não está nesta instalação do NeoPZ")
    return _INDISPONIVEL_CACHE[chave]


def _classes_indisponiveis(codigo: str, class_header_index: dict) -> dict:
    """
    {classe: motivo} das classes TPZ usadas no código que EXISTEM no NeoPZ mas
    cujo header não pode ser incluído aqui (ver _motivo_indisponivel).

    Existe porque o índice classe→header é montado a partir da PASTA DO
    CÓDIGO-FONTE, enquanto a validação compila contra a BIBLIOTECA INSTALADA —
    e 238 das 847 classes do índice estão numa e não na outra. Sem esta
    checagem o pipeline injetava o include certo-no-source, o g++ respondia
    "No such file or directory", _erro_denuncia_alucinacao lia isso como
    alucinação, e o resultado era acusar o modelo por uma classe que existe de
    verdade: dois retries queimados e resposta entregue sem selo.
    """
    if not class_header_index:
        return {}
    indisponiveis = {}
    for classe in find_tpz_classes_in_code(codigo):
        caminho = class_header_index.get(classe)
        if not caminho:
            continue
        motivo = _motivo_indisponivel(caminho)
        if motivo:
            indisponiveis[classe] = motivo
    return indisponiveis


def _validar_includes_por_classe(codigo: str, class_header_index: dict, collisions: dict) -> dict:
    """
    Verificação mais forte que _validar_includes(): para cada classe TPZ usada no
    código, checa se o #include CORRETO para aquela classe específica (segundo o
    índice determinístico class_header_index) está presente — não apenas se o
    nome do header existe em algum lugar do repo.

    Classes em collisions.json são ignoradas (mais de um header válido — não é
    possível forçar um único automaticamente).

    Retorna {classe: header_correto} para as classes cujo header certo está
    faltando OU presente na forma ERRADA — dict vazio = tudo OK.

    BUG CORRIGIDO (achado pela checagem de compilação, ver README): a versão
    anterior checava presença pelo BASENAME, então "TPZMatPoisson.h" contava
    como igual a "Poisson/TPZMatPoisson.h" — a forma sem prefixo de família
    passava validada e não compilava. Atingia 187 das 847 classes do índice
    (Poisson, DarcyFlow, Elasticity, Plasticity, Projection, ConsLaw,
    Electromagnetics, needrefactor) — 5 de 8 respostas reais logadas em
    logs/interacoes.jsonl caíam nisso, todas carimbadas "✅ Nomes verificados".
    """
    if not class_header_index:
        return {}

    usadas = find_tpz_classes_in_code(codigo)
    includes_atuais = _includes_com_caminho(codigo)

    faltando = {}
    for classe in usadas:
        if classe in collisions:
            continue  # ambíguo — não força um único header
        caminho = class_header_index.get(classe)
        if not caminho:
            continue  # classe fora do índice (pode ser nova ou não-TPZ)
        if _motivo_indisponivel(caminho):
            continue  # header existe no source, mas não aqui — exigir o
                      # include seria pedir o impossível e disparar retry
                      # eterno (ver _classes_indisponiveis)
        forma_certa = _include_para_header(caminho)
        # Exige a forma COMPILÁVEL exata, não só o basename presente em
        # algum #include — ver docstring acima e _includes_com_caminho.
        if includes_atuais.get(Path(caminho).name) != forma_certa:
            faltando[classe] = forma_certa
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


# ── Compilação do código gerado (validação semântica) ─────────────────────────
#
# Fluxo: resposta → blocos de código → TU sintética → g++ -fsyntax-only →
# diagnósticos FILTRADOS. O filtro é a peça crítica: a resposta do assistente
# quase nunca é um .cpp completo, e um trecho solto deixa de compilar por
# motivos legítimos (variável definida "acima", sem main). Sem filtro, o
# pipeline entraria em retry à toa e ficaria PIOR do que sem compilar.

# Só blocos de C++: ```bash / ```cmake não casam porque a linguagem, quando
# presente, tem que ser uma das listadas (o \s*\n depois não come 'bash').
_BLOCO_CODIGO_RE = re.compile(r"```(?:cpp|c\+\+|cxx|cc|c)?[ \t]*\n(.*?)```",
                              re.DOTALL | re.IGNORECASE)
_INCLUDE_LINHA_RE = re.compile(r'^\s*#\s*include\s*[<"]')
_MAIN_RE          = re.compile(r'\bint\s+main\s*\(')
# Definição em nível de topo: função (sem indentação, assinatura terminando em
# '{'), classe, struct ou template. Envolver isso num main não compilaria —
# C++ não aceita função aninhada.
#
# O separador antes do nome é [\s\*&], não \s: em `TPZGeoMesh *CriaMalha(int)`
# o '*' cola no nome e não há espaço ali. Mesma armadilha que já tinha deixado
# 136 métodos reais invisíveis para o regex de `Tipo *Nome(...)` no cpp_parser.
_DEF_TOPO_RE = re.compile(
    r'^(?:template\s*<|class\s+\w|struct\s+\w|namespace\s+\w'
    r'|[A-Za-z_][\w:<>,\s\*&]*[\s\*&][A-Za-z_]\w*\s*\([^;{}]*\)\s*(?:const\s*)?\{)',
    re.MULTILINE)


def _extrair_blocos_codigo(resposta: str) -> str:
    """
    Junta os blocos ```cpp da resposta na ordem em que aparecem — na prática
    são pedaços do MESMO programa (malha, depois material, depois análise), e
    compilá-los juntos é a reconstrução mais fiel do que o aluno vai montar.
    Retorna "" quando não há bloco de código (resposta em prosa).
    """
    return "\n".join(b.strip() for b in _BLOCO_CODIGO_RE.findall(resposta) if b.strip())


def _montar_tu(codigo: str) -> str:
    """
    Monta uma unidade de tradução compilável a partir de um trecho.

    Três casos, porque envolver tudo num main daria erro em dois deles:
      1. já tem main            → usa como está
      2. define função/classe   → mantém no topo e acrescenta um main vazio
      3. só sentenças soltas    → envolve num main

    Includes sempre sobem para o topo (o modelo às vezes os repete no meio do
    texto) e são deduplicados.
    """
    includes, corpo = [], []
    for linha in codigo.splitlines():
        (includes if _INCLUDE_LINHA_RE.match(linha) else corpo).append(linha)

    vistos, incs = set(), []
    for inc in includes:
        chave = inc.strip()
        if chave not in vistos:
            vistos.add(chave)
            incs.append(chave)

    corpo_txt = "\n".join(corpo).strip("\n")
    if _MAIN_RE.search(corpo_txt):
        return "\n".join(incs + ["", corpo_txt, ""])
    if _DEF_TOPO_RE.search(corpo_txt):
        return "\n".join(incs + ["", corpo_txt, "", "int main() { return 0; }", ""])
    return "\n".join(incs + ["", "int main() {", corpo_txt, "    return 0;", "}", ""])


# Diagnósticos que DENUNCIAM ALUCINAÇÃO — o código pede algo que o NeoPZ não
# oferece. Cada padrão existe nas duas redações (g++ e clang) porque a
# instalação do laboratório usa g++ mas ninguém garante isso em outra máquina.
_DIAG_ALUCINACAO = (
    re.compile(r"has no member named"),                      # g++
    re.compile(r"no member named '[^']+' in"),               # clang
    re.compile(r"is not a member of"),
    re.compile(r"no matching function for call to '[^']*TPZ"),
    re.compile(r"no matching constructor for initialization of '[^']*TPZ"),  # clang
    re.compile(r"No such file or directory"),                # include errado
    re.compile(r"file not found"),                           # clang, idem
    re.compile(r"'TPZ\w+' was not declared in this scope"),
    re.compile(r"'TPZ\w+' does not name a type"),
    re.compile(r"unknown type name 'TPZ\w+'"),               # clang
    re.compile(r"use of undeclared identifier 'TPZ\w+'"),    # clang
)

# Linha de diagnóstico do compilador: "arquivo:linha:coluna: error: mensagem"
_LINHA_ERRO_RE = re.compile(
    r'^[^\n]*?:\d+:(?:\d+:)?\s*(?:fatal\s+)?error:\s*(.+)$', re.MULTILINE)


def _erro_denuncia_alucinacao(mensagem: str) -> bool:
    """
    Separa o erro que acusa API inexistente do erro que é só artefato do
    recorte. O critério é conservador de propósito: na dúvida, ARTEFATO.
    Deixar passar uma alucinação mantém o comportamento de hoje; inventar uma
    alucinação gasta retry e piora a resposta.

    Por isso 'x was not declared in this scope' só conta quando o nome é TPZ —
    variável não declarada é o sintoma normal de um trecho que referencia algo
    definido "acima", fora do que o modelo colou.
    """
    return any(p.search(mensagem) for p in _DIAG_ALUCINACAO)


def _neopz_prefix():
    """
    Raiz da instalação do NeoPZ (a que contém lib/cmake/neopz/), ou None.
    NEOPZ_PREFIX no ambiente sobrescreve — útil para apontar para a instalação
    que casa com a branch/índice em uso.
    """
    env = os.environ.get("NEOPZ_PREFIX")
    candidatas = [Path(env)] if env else list(NEOPZ_PREFIXES)
    for c in candidatas:
        if (c / "lib" / "cmake" / "neopz" / "NeoPZTargets.cmake").is_file():
            return c
    return None


def _compilador_disponivel():
    """Caminho do compilador C++, ou None. NEOPZ_CXX no ambiente sobrescreve."""
    for cand in (os.environ.get("NEOPZ_CXX"), NEOPZ_CXX, "g++", "c++"):
        if not cand:
            continue
        caminho = shutil.which(cand) if not os.path.isabs(cand) else (
            cand if os.path.exists(cand) else None)
        if caminho:
            return caminho
    return None


_INCLUDE_FLAGS_CACHE = {}
_INTERFACE_INCLUDES_RE = re.compile(
    r'INTERFACE_INCLUDE_DIRECTORIES\s+"([^"]+)"')


def _include_flags(prefix: Path) -> list:
    """
    Os -I EXATOS que a instalação propaga, lidos do NeoPZTargets.cmake — a
    mesma lista que o CMake daria a quem faz target_link_libraries(NeoPZ::pz).

    Não é detalhe: a lista expõe `Material` mas NÃO `Material/Poisson`, e é
    justamente por isso que o include correto é "Poisson/TPZMatPoisson.h" e o
    basename sozinho não compila (ver _include_para_header). Um atalho tentador
    aqui — passar -I de todo subdiretório — faria o include ERRADO compilar,
    apagando uma das quatro classes de erro que a compilação existe para pegar.
    """
    chave = str(prefix)
    if chave not in _INCLUDE_FLAGS_CACHE:
        alvos = prefix / "lib" / "cmake" / "neopz" / "NeoPZTargets.cmake"
        casado = _INTERFACE_INCLUDES_RE.search(alvos.read_text(encoding="utf-8"))
        if not casado:
            return []
        dirs = [d.replace("${_IMPORT_PREFIX}", str(prefix))
                for d in casado.group(1).split(";") if d.strip()]
        _INCLUDE_FLAGS_CACHE[chave] = [f"-I{d}" for d in dirs if Path(d).is_dir()]
    return _INCLUDE_FLAGS_CACHE[chave]


def _compilar_codigo(resposta: str, timeout: int = TIMEOUT_COMPILACAO) -> dict:
    """
    Compila (só sintaxe/semântica, sem link) o código de uma resposta.

    Retorna dict com:
      status: 'ok'           — compilou limpo
              'erros'        — não compilou E há erro que denuncia alucinação
              'inconclusivo' — não compilou, mas só por artefato do recorte
              'sem_codigo'   — resposta em prosa, nada a compilar
              'indisponivel' — sem instalação do NeoPZ ou sem compilador
              'timeout'      — estourou o tempo
      erros:     mensagens filtradas (as que denunciam alucinação)
      ignorados: quantos diagnósticos foram descartados como artefato

    'indisponivel' é o caminho normal para quem instalou pelo Caminho A do
    README (cópia completa, sem NeoPZ compilado) — nunca é falha de validação.
    """
    codigo = _extrair_blocos_codigo(resposta)
    if not codigo.strip():
        return {"status": "sem_codigo", "erros": [], "ignorados": 0}

    prefix = _neopz_prefix()
    compilador = _compilador_disponivel()
    if prefix is None or compilador is None:
        motivo = ("instalação do NeoPZ não encontrada" if prefix is None
                  else "compilador C++ não encontrado")
        return {"status": "indisponivel", "erros": [], "ignorados": 0, "motivo": motivo}

    flags_include = _include_flags(prefix)
    if not flags_include:
        # NeoPZTargets.cmake existe mas não expõe a lista esperada — compilar
        # com include path inventado daria diagnóstico errado, então é melhor
        # não compilar do que compilar torto.
        return {"status": "indisponivel", "erros": [], "ignorados": 0,
                "motivo": "include path da instalação não pôde ser lido"}

    tu = _montar_tu(codigo)
    with tempfile.TemporaryDirectory() as tmp:
        fonte = Path(tmp) / "gerado.cpp"
        fonte.write_text(tu, encoding="utf-8")
        cmd = [compilador, "-fsyntax-only", "-std=gnu++17", "-w",
               f"-fmax-errors={MAX_ERROS_RELATADOS * 2}",
               *flags_include, str(fonte)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "erros": [], "ignorados": 0}

    if proc.returncode == 0:
        return {"status": "ok", "erros": [], "ignorados": 0}

    mensagens = _LINHA_ERRO_RE.findall(proc.stderr)
    relevantes, ignorados = [], 0
    for msg in mensagens:
        msg = msg.strip()
        if _erro_denuncia_alucinacao(msg):
            if msg not in relevantes:
                relevantes.append(msg)
        else:
            ignorados += 1

    if not relevantes:
        return {"status": "inconclusivo", "erros": [], "ignorados": ignorados}
    return {"status": "erros", "erros": relevantes[:MAX_ERROS_RELATADOS],
            "ignorados": ignorados}


_CLASSE_EM_DIAGNOSTICO_RE = re.compile(r"\bTPZ\w+")


def _classes_citadas_em_erros(erros: list, whitelist: set) -> set:
    """
    Classes TPZ que aparecem nos diagnósticos do compilador — usadas para
    reforçar o contexto do retry.

    É o caso em que o reforço mais importa: "'class TPZDarcyFlow' has no member
    named 'SetElasticity'" identifica a classe cuja DECLARAÇÃO o modelo precisa
    ver para acertar (a whitelist global de métodos não sabe dizer isso). O
    filtro pela whitelist descarta o ruído do g++ (`TPZVec<...>` de mensagem de
    template instanciada, nome truncado) — buscar chunk de nome inexistente só
    poluiria o contexto.
    """
    citadas = set()
    for msg in erros:
        citadas.update(_CLASSE_EM_DIAGNOSTICO_RE.findall(msg))
    return {c for c in citadas if c in whitelist} if whitelist else citadas


# Cutoffs de confiança para substituição AUTOMÁTICA (sem depender do LLM
# aceitar a sugestão) — mais altos que os usados só para SUGERIR no prompt
# (0.6 em _sugerir_correcoes / 0.5 em _validar_includes), porque aqui o texto
# é reescrito direto, então o risco de trocar errado por acaso importa mais.
CUTOFF_CLASSE_AUTOMATICA = 0.80
CUTOFF_METODO_AUTOMATICO = 0.78


def _corrigir_classes_automaticamente(codigo: str, whitelist: set, renames: dict = None,
                                      destinos: set = None) -> tuple:
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

    # Quem ENTRA na correção é medido pela whitelist inteira (a classe existe
    # ou não); para onde ela SAI é medido pelos destinos utilizáveis — ver
    # _whitelist_utilizavel.
    destinos = whitelist if destinos is None else destinos
    renames = renames or {}
    correcoes = []
    for errada in alucinadas:
        # 1º o mapa curado de renomeações (determinístico, confiança máxima) —
        # difflib sugere por STRING e já empurrou 'TPZMatLaplacian' para
        # 'TPZMatPlaca2' (material de placa!) num problema de Poisson, quando
        # o certo era 'TPZMatPoisson' (string-distante, semanticamente certo).
        # Trava de segurança: só aplica se o destino existir na whitelist
        # (protege contra typo/entrada desatualizada no renames.json).
        if errada in renames and renames[errada] in destinos:
            certa = renames[errada]
            sufixo = " [renomeação]"
        else:
            candidatos = difflib.get_close_matches(errada, destinos, n=1, cutoff=CUTOFF_CLASSE_AUTOMATICA)
            if not candidatos:
                continue
            certa = candidatos[0]
            sufixo = ""
        codigo, n = re.subn(r'\b' + re.escape(errada) + r'\b', certa, codigo)
        if n:
            correcoes.append(f"{errada} → {certa}{sufixo}")
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
       (e não é ambígua/collision), garante que o #include CORRETO está
       presente: injeta se estiver faltando, ou REESCREVE a linha existente
       se ela usa uma forma que não compila (ex: "TPZMatPoisson.h" sem o
       prefixo de família — ver _include_para_header e _includes_com_caminho).

    Retorna (codigo_corrigido, lista_de_correcoes_aplicadas).
    """
    if not class_header_index:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    # classe -> caminho completo do índice; a forma compilável é derivada por
    # _include_para_header (pode exigir prefixo de família — não é o basename)
    necessarios = {
        classe: class_header_index[classe]
        for classe in usadas
        if classe not in collisions and class_header_index.get(classe)
    }

    linhas = codigo.split("\n")

    def _includes_atuais(linhas: list) -> dict:
        """basename -> (índice da linha, caminho exatamente como escrito)"""
        atuais = {}
        for i, linha in enumerate(linhas):
            m = re.search(r'#include\s*[<"]([^>"]+\.h)[>"]', linha)
            if m:
                atuais.setdefault(Path(m.group(1)).name, (i, m.group(1)))
        return atuais

    atuais = _includes_atuais(linhas)
    # Dois padrões de include "chutado" a partir do nome da classe:
    #   TPZInt1d → "tpzint1d.h"  e  "pzint1d.h"
    # O segundo imita a convenção real do NeoPZ (pzgmesh.h, pzcmesh.h,
    # pzquad.h) e por isso é o chute mais frequente — era o que escapava:
    # numa explicação de TPZInt1d o modelo escrevia #include "pzint1d.h"
    # (o header verdadeiro é pzquad.h) e a remoção automática não pegava.
    # A guarda `nome not in headers_whitelist` garante que só some include
    # que de fato não existe.
    candidatos_chute = set()
    for c in necessarios:
        base = c.lower()
        candidatos_chute.add(f"{base}.h")
        if base.startswith("tpz"):
            candidatos_chute.add(f"pz{base[3:]}.h")
    linhas_remover = {
        idx for nome, (idx, _caminho) in atuais.items()
        if nome.lower() in INCLUDES_LIXO_CONHECIDOS
        or (nome.lower() in candidatos_chute and nome not in headers_whitelist)
    }
    if linhas_remover:
        linhas = [l for i, l in enumerate(linhas) if i not in linhas_remover]

    if not necessarios:
        return "\n".join(linhas), []

    atuais = _includes_atuais(linhas)
    faltando   = {}  # classe -> forma certa: não há include NENHUM para essa classe
    a_corrigir = {}  # classe -> (índice, caminho errado, forma certa): include
                     # presente, mas na forma que não compila (BUG corrigido —
                     # ver README e _validar_includes_por_classe: a versão
                     # anterior comparava por basename e deixava passar
                     # "TPZMatPoisson.h" como se fosse "Poisson/TPZMatPoisson.h")
    # Classe cujo header não existe NESTA instalação sai daqui: injetar o
    # include certo-no-source garantiria "No such file or directory" no g++, e
    # esse diagnóstico é lido como alucinação (ver _classes_indisponiveis). A
    # remoção de chute acima continua valendo para ela — some o include
    # inventado, e nenhum outro entra no lugar.
    obtenivel = {c: cam for c, cam in necessarios.items()
                 if not _motivo_indisponivel(cam)}
    for c, caminho in obtenivel.items():
        forma_certa = _include_para_header(caminho)
        presente = atuais.get(Path(caminho).name)
        if presente is None:
            faltando[c] = forma_certa
        elif presente[1] != forma_certa:
            a_corrigir[c] = (presente[0], presente[1], forma_certa)

    correcoes = []
    for c, (idx, caminho_errado, forma_certa) in a_corrigir.items():
        padrao_linha = re.compile(r'(#include\s*[<"])' + re.escape(caminho_errado) + r'([>"])')
        nova_linha, n = padrao_linha.subn(r'\g<1>' + forma_certa + r'\g<2>', linhas[idx], count=1)
        if n:
            linhas[idx] = nova_linha
            correcoes.append(f'{c}: #include "{caminho_errado}" → "{forma_certa}"')

    if faltando:
        posicoes_include = [i for i, l in enumerate(linhas) if re.match(r'\s*#include\b', l)]
        ultimo_include_idx = max(posicoes_include, default=-1)

        novas = [f'#include "{forma_certa}"'
                 for forma_certa in sorted(set(faltando.values()))]
        if ultimo_include_idx >= 0:
            linhas = linhas[:ultimo_include_idx + 1] + novas + linhas[ultimo_include_idx + 1:]
            correcoes += [f'{c}: + #include "{forma_certa}"' for c, forma_certa in faltando.items()]
        else:
            # Nenhum include na resposta: a inserção precisa cair DENTRO do
            # bloco ```cpp. Colocar no topo do texto punha o header na prosa,
            # antes da cerca — o usuário via um #include solto acima do "Segue:"
            # e, pior, _extrair_blocos_codigo não o enxergava: o g++ recebia o
            # código sem include e respondia "'TPZMatPoisson' was not declared
            # in this scope", que _erro_denuncia_alucinacao lê como alucinação.
            # Mesma acusação falsa de _classes_indisponiveis, por outra porta —
            # e nesta o alvo é a API ATUAL, o caso comum.
            abre_bloco = next((i for i, l in enumerate(linhas)
                               if re.match(r'\s*```(?:cpp|c\+\+|cxx|cc|c)?[ \t]*$', l,
                                           re.IGNORECASE)), None)
            
            if abre_bloco is not None:
                corte = abre_bloco + 1
                linhas = linhas[:corte] + novas + linhas[corte:]
                correcoes += [f'{c}: + #include "{forma_certa}"' for c, forma_certa in faltando.items()]
            # Se abre_bloco for None, não há bloco de código válido e nem #includes
            # prévios. Provavelmente é uma resposta em prosa. Desistimos de injetar
            # para não colocar os includes no topo do texto soltos.

    return "\n".join(linhas), correcoes


# ── Log de interações (dataset futuro de avaliação/fine-tuning) ────────────────

def _registrar_interacao(pergunta: str, resultado: dict, caminho: Path = LOG_INTERACOES_FILE):
    """
    Acrescenta a interação ao JSONL (uma linha JSON auto-contida por resposta).
    Ver comentário em LOG_INTERACOES_FILE. Nunca deve derrubar o chat — em caso
    de erro, avisa e segue.
    """
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        registro = {
            "quando":                datetime.datetime.now().isoformat(timespec="seconds"),
            "pergunta":              pergunta,
            "resposta":              resultado["resposta"],
            "valido":                resultado["valido"],
            "tentativas":            resultado["tentativas"],
            "correcoes_automaticas": resultado["correcoes_automaticas"],
            "alucinacoes":           resultado["alucinacoes"],
            "includes_errados":      sorted(resultado["includes"].keys()),
            "metodos_suspeitos":     [f"{c}::{m}" for c, m in resultado["metodos_suspeitos"]],
            # Status da compilação + os erros: é o registro de quais alucinações
            # SÓ o compilador pegou — a lista que diz quais receitas escrever
            # em seguida (ver Curadoria no README).
            "compilacao":            resultado.get("compilacao", {}).get("status", "nao_executada"),
            "erros_compilacao":      resultado.get("compilacao", {}).get("erros", []),
            "classes_legado":        resultado.get("classes_legado", []),
            # Quais classes o índice ofereceu e a instalação não tinha: é a
            # lista que diz o que vale exportar/religar no build do NeoPZ.
            "classes_indisponiveis": resultado.get("classes_indisponiveis", {}),
            "fontes_nao_api":        resultado.get("fontes_nao_api", []),
            "fontes":                sorted(resultado["fontes"]),
        }
        with caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  (log de interações falhou: {e})")


def _emitir(on_evento, tipo: str, texto: str):
    """Notifica a interface (web) sobre progresso — tipos: 'tentativa',
    'token', 'status'. Nunca deve derrubar o pipeline."""
    if on_evento is None:
        return
    try:
        on_evento(tipo, texto)
    except Exception:
        pass


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
    renames: dict = None,
    legacy_classes: set = None,
    historico: list = None,
    on_evento=None,
) -> dict:
    """
    Executa o pipeline completo:
    recuperação (1x) → formatação → geração → correção determinística →
    validação de nomes → COMPILAÇÃO → retry com contexto reforçado, se
    necessário.

    historico: pares (pergunta, resposta) das trocas anteriores — dá contexto
    a follow-ups no prompt e na recuperação.
    on_evento: callback opcional (tipo, texto) para a interface web mostrar
    progresso/streaming — tipos: 'tentativa', 'token', 'status'.
    """
    class_header_index = class_header_index or {}
    collisions = collisions or {}
    methods_whitelist = methods_whitelist or set()
    class_methods_index = class_methods_index or {}
    renames = renames or {}
    legacy_classes = legacy_classes or set()

    # Whitelist = "esse nome existe no NeoPZ". Destinos = "posso mandar o
    # modelo usar" — o que a instalação de fato tem. Calculado uma vez por
    # pergunta (a sonda por header é cacheada); ver _whitelist_utilizavel.
    whitelist_destino = _whitelist_utilizavel(whitelist, class_header_index)

    classes_alucinadas = None
    includes_errados = None
    includes_por_classe = None
    metodos_suspeitos = None
    erros_compilacao = None
    compilacao = {"status": "nao_executada", "erros": [], "ignorados": 0}
    correcoes_automaticas = []
    classes_legado_usadas = []
    classes_indisponiveis = {}
    nomes_ok = False

    # Plano B: a PRIMEIRA tentativa com nomes limpos que só reprovou na
    # compilação. Existe por causa de uma regressão que plugar a compilação
    # criaria: antes, tentativa com nomes limpos era devolvida na hora; agora
    # ela vira insumo de retry, e sem esta rede a resposta final poderia ser
    # uma tentativa POSTERIOR e PIOR (com classe alucinada). Só é usada nesse
    # caso — se a última tentativa também tiver nomes limpos, ela fica, porque
    # viu os erros do compilador no prompt. "Menos erros de compilador" não
    # entra no critério: o g++ cascateia e a contagem não é ordem confiável.
    melhor = None

    def _resultado(valido: bool) -> dict:
        """Empacota o estado ATUAL do loop. Lê as variáveis acima no momento
        da chamada — por isso `melhor` guarda o dict pronto, não a intenção."""
        return {
            "resposta":             resposta,
            "valido":               valido,
            "alucinacoes":          classes_alucinadas or [],
            "includes":             includes_errados or {},
            "includes_por_classe":  includes_por_classe or {},
            "metodos_suspeitos":    metodos_suspeitos or [],
            "compilacao":           compilacao,
            "classes_legado":       classes_legado_usadas,
            "classes_indisponiveis": classes_indisponiveis,
            # Fontes que são código de teste/benchmark, não a biblioteca. Não
            # some do rodapé disfarçado de exemplo de uso: 852 dos 5984 chunks
            # de exemplo vêm daí, e um TestDeRham.cpp citado como "exemplo"
            # ensina a montar um teste unitário, não um problema de FEM.
            "fontes_nao_api":       sorted(f for f in fontes
                                           if _fora_da_api(f) == "teste/benchmark"),
            "correcoes_automaticas": correcoes_automaticas,
            "fontes":               set(fontes),
            "tentativas":           tentativa,
        }

    # 1. Recupera documentos relevantes — FORA do loop: a busca é determinística
    #    para a mesma pergunta, então repeti-la a cada retry só gastava
    #    embedding/busca para obter o MESMO resultado. No retry o contexto muda
    #    de outro jeito: reforço com as declarações das classes sugeridas
    #    (ver fim do loop).
    #    Follow-ups ("e como refino essa malha?") não carregam termos
    #    suficientes sozinhos — a consulta de retrieval é expandida com a
    #    pergunta anterior (só a consulta; a TAREFA no prompt é a atual).
    consulta = pergunta
    if historico:
        consulta = f"{historico[-1][0]}\n{pergunta}"
    # A heurística explicativa avalia a pergunta ATUAL (não a consulta
    # expandida — o histórico poderia contaminar a classificação)
    h_docs, e_docs, w_docs, fontes = _recuperar_contexto(
        consulta, headers_db, examples_db, wiki_db,
        explicativa=_pergunta_e_explicativa(pergunta),
    )

    for tentativa in range(1, MAX_RETRIES + 2):
        print(f"  [Tentativa {tentativa}] Gerando resposta...")
        _emitir(on_evento, "tentativa", str(tentativa))

        # 2. Formata o contexto
        contexto = _formatar_contexto(h_docs, e_docs, w_docs)

        # 3. Monta o prompt (com correções se for retry)
        prompt = _montar_prompt(
            pergunta, contexto, system_base, whitelist, headers_whitelist,
            classes_alucinadas, includes_errados, includes_por_classe,
            metodos_suspeitos, methods_whitelist,
            erros_compilacao=erros_compilacao,
            classes_contexto=_classes_do_contexto(h_docs, e_docs, w_docs),
            renames=renames,
            historico=historico,
            destinos=whitelist_destino,
        )

        tokens_estimados = len(prompt) // 4  # ~4 chars/token p/ código + PT misto
        if tokens_estimados > int(NUM_CTX * 0.9):
            print(f"  ⚠️  Prompt grande (~{tokens_estimados} tokens, NUM_CTX={NUM_CTX}) — risco de truncamento")

        # 4. Chama o modelo — em streaming quando possível, para a interface
        #    mostrar os tokens saindo (num 7b local a resposta leva dezenas de
        #    segundos; sem feedback o usuário acha que travou)
        try:
            pedacos = []
            for pedaco in llm.stream(prompt):
                pedacos.append(pedaco)
                _emitir(on_evento, "token", pedaco)
            resposta = "".join(pedacos)
        except (AttributeError, NotImplementedError):
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
            resposta, correcoes_classes = _corrigir_classes_automaticamente(
                resposta, whitelist, renames, destinos=whitelist_destino)
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
                _emitir(on_evento, "status", f"🔧 Corrigido automaticamente: {', '.join(correcoes_automaticas)}")

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

        # Segundo nível da whitelist: classe que existe, mas só no legado —
        # aviso informativo, NÃO bloqueia nem dispara retry (ver
        # LEGACY_CLASSES_FILE; um falso "alucinação" aqui seria pior que o aviso)
        classes_legado_usadas = sorted(find_tpz_classes_in_code(resposta) & legacy_classes)

        # Classe que existe no NeoPZ mas cujo header esta instalação não tem
        # (ver _classes_indisponiveis). Como o legado: avisa, não bloqueia e não
        # dispara retry — o modelo não errou, e insistir não faria aparecer um
        # header que não está no disco.
        classes_indisponiveis = (_classes_indisponiveis(resposta, class_header_index)
                                 if tem_codigo else {})

        nomes_ok = not (classes_alucinadas or includes_errados
                        or includes_por_classe or metodos_suspeitos)

        # 5.5 COMPILAÇÃO — a confirmação por CLASSE que a validação de nomes não
        #     dá. A whitelist de métodos é global de propósito (ver
        #     METHODS_WHITELIST_FILE), então `mat->SetElasticity(E, nu)` num
        #     TPZDarcyFlow chegava aqui aprovado: SetElasticity existe — em
        #     TPZElasticity2D. Era o selo "✅ Nomes verificados" cobrindo código
        #     que não compila. O g++ responde a pergunta certa ("existe NESTA
        #     classe, com ESTA assinatura") em ~0,5 s.
        #
        #     Só roda quando os nomes já estão limpos: é exatamente onde o
        #     pipeline ia carimbar e devolver. Com nome alucinado o retry já
        #     está decidido, e os diagnósticos seriam cascata do mesmo erro.
        #
        #     Só o status 'erros' reprova. 'inconclusivo' (erro que é artefato
        #     do recorte), 'indisponivel' (sem NeoPZ compilado — o Caminho A do
        #     README) e 'timeout' mantêm o comportamento de hoje: a ausência de
        #     compilador nunca pode virar reprovação.
        #
        #     Código que usa classe indisponível não é compilável NEM em
        #     princípio: sem o header, o g++ cospe "was not declared in this
        #     scope" para cada uso dela — e esse diagnóstico também está em
        #     _DIAG_ALUCINACAO. Compilar aqui só produziria acusação falsa em
        #     cascata, então a compilação é pulada e o motivo real fica no
        #     status (não é falha do modelo nem reprovação).
        compilacao = {"status": "nao_executada", "erros": [], "ignorados": 0}
        erros_compilacao = None
        if nomes_ok and tem_codigo and classes_indisponiveis:
            fora = "; ".join(f"{c} ({m})" for c, m in sorted(classes_indisponiveis.items()))
            compilacao = {"status": "indisponivel", "erros": [], "ignorados": 0,
                          "motivo": f"código usa classe fora desta instalação: {fora}"}
            print(f"  ⚠️  Compilação pulada — {compilacao['motivo']}")
            _emitir(on_evento, "status", f"⚠️ Compilação pulada — {compilacao['motivo']}")
        elif nomes_ok and tem_codigo:
            _emitir(on_evento, "status", "🛠️ Compilando o código gerado...")
            compilacao = _compilar_codigo(resposta)
            if compilacao["status"] == "erros":
                erros_compilacao = compilacao["erros"]
                print(f"  ❌ O compilador recusou o código: {'; '.join(erros_compilacao)}")
                _emitir(on_evento, "status",
                        "❌ O compilador recusou o código: " + "; ".join(erros_compilacao))
            elif compilacao["status"] == "inconclusivo":
                print(f"  ℹ️  Compilação inconclusiva — {compilacao['ignorados']} diagnóstico(s) "
                      "tratados como artefato do recorte, nenhum acusa API inexistente")
            elif compilacao["status"] == "timeout":
                print(f"  ⚠️  Compilação estourou {TIMEOUT_COMPILACAO}s — ignorada")
            # 'indisponivel' é silencioso de propósito (ver README)

        if nomes_ok and not erros_compilacao:
            if compilacao["status"] == "ok":
                print("  ✅ Compilado — o g++ aceitou o código: classes, métodos e assinaturas "
                      "existem de verdade (o resultado físico continua não verificado)")
            else:
                print("  ✅ Nomes verificados — classes, headers e métodos existem no NeoPZ "
                      "(semântica e assinaturas não são checadas)")
            return _resultado(True)

        # Nomes limpos + compilação reprovada: guarda como plano B antes de
        # gastar o retry (ver comentário de `melhor`).
        if nomes_ok and melhor is None:
            melhor = _resultado(False)

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

        # Reforço de contexto para o retry: até aqui o modelo era mandado usar
        # o nome sugerido (ex: "use TPZGeoMeshTools") sem nunca VER a
        # declaração da classe sugerida — a API certa podia não estar no
        # contexto. Busca os chunks das classes sugeridas/envolvidas e injeta
        # nos headers do contexto da próxima tentativa.
        classes_reforco = set()
        docs_semanticos = []
        for c in classes_alucinadas or []:
            # Renomeação conhecida tem prioridade (destino certo, determinístico)
            if c in renames and renames[c] in whitelist_destino:
                classes_reforco.add(renames[c])
            classes_reforco.update(
                difflib.get_close_matches(c, whitelist_destino, n=2, cutoff=0.6))
            # Busca SEMÂNTICA além da string: o nome alucinado + a pergunta
            # descrevem o CONCEITO que o modelo procurava. difflib sozinho já
            # empurrou 'TPZMatLaplacian' (Poisson) para 'TPZMatPlaca2'
            # (material de placa!) só porque as strings parecem — a busca por
            # embedding de "TPZMatLaplacian <pergunta sobre Poisson>" traz
            # TPZMatPoisson/TPZDarcyFlow, que são string-distantes mas certos.
            try:
                docs_semanticos.extend(headers_db.similarity_search(f"{c} {pergunta}", k=2))
            except Exception:
                pass
        for cls, _metodo in metodos_suspeitos or []:
            classes_reforco.add(cls)
        # Classe acusada pelo COMPILADOR: em "'class TPZDarcyFlow' has no member
        # named 'SetElasticity'" a declaração que falta ao modelo é a de
        # TPZDarcyFlow — mandar "não use SetElasticity" sem mostrar quais
        # métodos a classe TEM é pedir para ele chutar de novo.
        classes_reforco |= _classes_citadas_em_erros(erros_compilacao or [], whitelist)
        classes_reforco -= {d.metadata.get("classe", "") for d in h_docs}

        extras = _buscar_declaracoes_por_classe(headers_db, pergunta, classes_reforco, limite=K_HEADERS)
        extras = _despriorizar_legado(_dedup_docs(extras + docs_semanticos))
        ja_presentes = {d.page_content for d in h_docs}
        extras = [d for d in extras if d.page_content not in ja_presentes]
        if extras:
            h_docs = _dedup_docs(h_docs + extras)
            fontes |= {d.metadata.get("source", "?") for d in extras}
            nomes = ", ".join(sorted(
                {d.metadata.get("classe") or Path(d.metadata.get("source", "?")).name for d in extras}
            ))
            print(f"  📚 Contexto reforçado com declarações de: {nomes}")

        motivo = ("Compilação reprovada" if erros_compilacao
                  else "Problemas de validação detectados")
        _emitir(on_evento, "status", f"↩️ {motivo} — corrigindo e gerando de novo...")
        print("  ↩️  Corrigindo na próxima tentativa...")

    # Esgotou as tentativas. `melhor` (nomes limpos, só a compilação reprovou)
    # ganha da última tentativa quando esta chegou a alucinar nome — ver o
    # comentário de `melhor` lá em cima.
    if melhor is not None and not nomes_ok:
        print("  ↩️  Devolvendo a melhor tentativa (nomes limpos, compilação reprovada).")
        return melhor
    return _resultado(False)


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
    renames            = _carregar_renames()
    legacy_classes     = _carregar_legacy_classes()
    system_base        = _carregar_system_prompt()
    llm                = OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)

    print("\n" + "=" * 50)
    print("  🤖 Assistente LabMeC Pronto!")
    print("  Digite 'sair' para encerrar.")
    print("=" * 50 + "\n")

    historico = []  # pares (pergunta, resposta) — memória de conversa

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
            renames, legacy_classes,
            historico=historico,
        )

        historico.append((pergunta, resultado["resposta"]))
        del historico[:-6]  # só as últimas trocas interessam (e o prompt corta em 3)

        print("\nAssistente LabMeC:\n")
        print(resultado["resposta"])
        print()

        # Status de validação
        if resultado["correcoes_automaticas"]:
            print(f"🔧 Correções automáticas (classes/métodos/headers): {', '.join(resultado['correcoes_automaticas'])}")
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
        if resultado["compilacao"]["erros"]:
            print("❌ O compilador recusou o código (erro que a checagem de nomes não pega):")
            for e in resultado["compilacao"]["erros"]:
                print(f"   - {e}")
        if resultado["classes_legado"]:
            dicas = [
                f"{c} → prefira {renames[c]}" if c in renames else c
                for c in resultado["classes_legado"]
            ]
            print(f"⚠️  API antiga ({'/'.join(DIRS_LEGADO)}) usada: {', '.join(dicas)}")
            print("   Essas classes existem, mas são do legado — prefira a API atual do NeoPZ")
        if resultado.get("classes_indisponiveis"):
            indisp_fmt = ", ".join(f"{c} ({m})"
                                   for c, m in sorted(resultado["classes_indisponiveis"].items()))
            print(f"⚠️  Classe existe no NeoPZ mas não está disponível aqui: {indisp_fmt}")
            print("   O código não vai compilar sem esse header — a compilação foi pulada,")
            print("   não é alucinação do modelo (ver _classes_indisponiveis)")
        if resultado.get("fontes_nao_api"):
            nomes = ", ".join(Path(f).name for f in resultado["fontes_nao_api"])
            print(f"ℹ️  Fontes de teste/benchmark consultadas: {nomes}")
            print(f"   ({'/'.join(_DIRS_NAO_API)} viram executável separado, não entram na libpz —")
            print("    servem para entender a classe, não como exemplo canônico de uso)")
        if resultado["valido"] and resultado["compilacao"]["status"] == "ok":
            print("✅ Compilado: o g++ aceitou o código — classes, métodos e assinaturas existem de verdade")
            print("   (compilar NÃO verifica o resultado físico — confira se o material/formulação é o adequado ao problema)")
        elif resultado["valido"]:
            print("✅ Nomes verificados: classes, headers e métodos existem no NeoPZ")
            print("   (semântica e assinaturas NÃO são checadas — confira se o material/método é o adequado ao problema)")

        # Fontes usadas
        fontes_curtas = [Path(f).name for f in resultado["fontes"]]
        print(f"📄 Fontes ({resultado['tentativas']} tentativa(s)): {', '.join(fontes_curtas)}")
        print("-" * 50 + "\n")

        # Log JSONL — dataset futuro de avaliação/fine-tuning
        _registrar_interacao(pergunta, resultado)


if __name__ == "__main__":
    main()