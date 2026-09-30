from langchain_core.tools import tool
from typing import Annotated
from .context import PipelineContext
from .compilation import _compilar_codigo

@tool
def buscar_declaracao_classe(classe: Annotated[str, "O nome exato da classe NeoPZ, ex: TPZGeoMesh"]) -> str:
    """Busca a declaração completa (o arquivo .h) de uma classe do NeoPZ, mostrando todos os seus métodos públicos, construtores e heranças.
    Útil quando você precisa saber os argumentos exatos de um construtor ou quais métodos a classe possui."""
    ctx = PipelineContext.load()
    if ctx.headers_db is None: 
        return "Erro: Banco de headers indisponível."
    
    docs = ctx.headers_db.similarity_search(classe, k=3, filter={"classe": classe})
    if not docs:
        docs = ctx.headers_db.similarity_search(classe, k=3)
        
    return "\n\n".join([f"/// {d.metadata.get('source', 'Header')}\n{d.page_content}" for d in docs])

@tool
def buscar_exemplos_codigo(termo_de_busca: Annotated[str, "O que você quer encontrar no código, ex: 'TPZMixedDarcyFlow' ou 'criar malha geométrica'"]) -> str:
    """Busca exemplos reais de código fonte do NeoPZ (testes e tutoriais) onde classes e funções são usadas na prática.
    Útil quando você tem a declaração da classe mas não sabe como inicializá-la ou como ela interage com a malha computacional."""
    ctx = PipelineContext.load()
    if ctx.examples_db is None: 
        return "Erro: Banco de exemplos indisponível."
    
    docs = ctx.examples_db.max_marginal_relevance_search(termo_de_busca, k=4, fetch_k=20)
    return "\n\n".join([f"/// {d.metadata.get('source', 'Exemplo')}\n{d.page_content}" for d in docs])

@tool
def buscar_documentacao_wiki(termo_de_busca: Annotated[str, "Conceito matemático ou do NeoPZ, ex: 'convecção', 'espaço H1', 'ponto de sela'"]) -> str:
    """Busca explicações teóricas, documentação e receitas passo-a-passo na Wiki do projeto NeoPZ.
    Útil para entender a física, as formulações disponíveis ou os passos macro de como estruturar um projeto no NeoPZ."""
    ctx = PipelineContext.load()
    if ctx.wiki_db is None: 
        return "Erro: Banco da wiki indisponível."
    
    docs = ctx.wiki_db.similarity_search(termo_de_busca, k=3)
    return "\n\n".join([f"/// {d.metadata.get('source', 'Wiki')}\n{d.page_content}" for d in docs])

@tool
def testar_compilacao(codigo_cxx: Annotated[str, "Trecho completo de código C++ para ser testado pelo compilador GCC"]) -> str:
    """Passa um trecho de código pelo compilador g++ real usando o ambiente do NeoPZ.
    Retorna 'SUCESSO' se o código compilar corretamente, ou a lista de ERROS DO COMPILADOR.
    SEMPRE use esta ferramenta para validar sua ideia ANTES de dar a resposta final com o código gerado para o usuário, garantindo que o que você vai entregar funciona de verdade."""
    res = _compilar_codigo(codigo_cxx)
    if res["status"] == "ok":
        return "SUCESSO: O código compilou perfeitamente e os métodos/assinaturas existem de verdade no NeoPZ."
    elif res["status"] == "erros":
        erros_str = "\n".join(res["erros"])
        return f"ERRO DE COMPILAÇÃO. O compilador relatou os seguintes erros:\n{erros_str}\nEntenda os erros, consulte a declaração das classes se necessário (com buscar_declaracao_classe) e tente novamente."
    else:
        return f"Aviso: {res['status']}. Não foi possível confirmar se o código está 100% correto."

def obter_todas_ferramentas():
    return [
        buscar_declaracao_classe,
        buscar_exemplos_codigo,
        buscar_documentacao_wiki,
        testar_compilacao
    ]
