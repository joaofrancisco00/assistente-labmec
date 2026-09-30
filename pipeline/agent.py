from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from .agent_tools import obter_todas_ferramentas
from .compilation import _compilar_codigo
from .config import OLLAMA_MODEL, TEMPERATURE, NUM_CTX
from .context import PipelineContext
from .prompt import _formatar_contexto
from .retrieval import _recuperar_contexto

def gerar_codigo_agente(pergunta: str, ctx: PipelineContext, historico: list = None, on_evento=None) -> dict:
    llm = ctx.llm
    if not hasattr(llm, "bind_tools") and type(llm).__name__ == "OllamaLLM":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)
    if hasattr(llm, "max_retries"):
        llm = llm.model_copy(update={"max_retries": 4})
    
    try:
        tools = obter_todas_ferramentas(ctx)
        # Validação simples se o modelo suporta
        llm.bind_tools(tools)
    except Exception:
        return {
            "resposta": "⚠️ Erro: O modelo atual não suporta Tool Calling (Function Calling). Mude para o Gemini para usar o Agente.",
            "valido": False, "alucinacoes": [], "erros_aridade": [], "erros_semanticos": [],
            "includes": {}, "includes_por_classe": {}, "metodos_suspeitos": [], 
            "compilacao": {"status": "erros", "erros": []}, "classes_legado": [], 
            "classes_indisponiveis": {}, "fontes_nao_api": [], "correcoes_automaticas": [], 
            "fontes": set(), "tentativas": 1
        }

    if on_evento:
        on_evento("status", "🔎 Recuperando contexto do NeoPZ para o agente...")
    h_docs, e_docs, w_docs, fontes = _recuperar_contexto(
        pergunta, ctx.headers_db, ctx.examples_db, ctx.wiki_db)
    contexto = _formatar_contexto(h_docs, e_docs, w_docs)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Você é um Engenheiro de Software Sênior especialista em C++ e na biblioteca de Elementos Finitos 'NeoPZ'.\n"
         "Sua missão é ajudar o usuário gerando código C++ limpo, sem erros e que compile perfeitamente.\n"
         "REGRAS DE OURO:\n"
         "1. O código gerado deve ser incluído em blocos Markdown (```cpp ... ```).\n"
         "2. Você já recebeu abaixo um CONTEXTO RECUPERADO com declarações de classe, exemplos reais e receitas da wiki relevantes para a pergunta. Use-o como base principal — as receitas são código completo já verificado por compilação.\n"
         "   Só chame ferramentas de busca (`buscar_declaracao_classe`, `buscar_exemplos_codigo`, `buscar_documentacao_wiki`) se faltar algo essencial que o contexto não cobre, ou para entender um erro do compilador.\n"
         "3. SEMPRE teste o seu código com a ferramenta `testar_compilacao` ANTES de dar a resposta final.\n"
         "   - Se o compilador retornar erros, você DEVE analisar o erro, usar ferramentas se necessário, e testar novamente com as correções.\n"
         "   - Você só pode terminar e dar sua resposta definitiva quando tiver 'SUCESSO' no teste de compilação, ou após 4 tentativas falhas.\n"
        ),
        ("system", "CONTEXTO RECUPERADO:\n{contexto}"),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    prompt = prompt.partial(contexto=contexto)

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=6,
        handle_parsing_errors=True
    )
    
    if on_evento:
        on_evento("status", "🤖 O Agente acordou e está raciocinando (Acompanhe as chamadas de ferramenta no terminal)...")
    
    resposta_final = ""
    houve_erro = False
    fontes_usadas = set(fontes)
    
    try:
        # Chat history parser
        chat_history = []
        if historico:
            for p, r in historico:
                chat_history.append(("human", p))
                chat_history.append(("ai", r))
                
        # Invoke não streama o raciocínio no frontend nativamente de forma simples (só no stdout do terminal)
        # O usuário que acionou do terminal verá as ferramentas rodando!
        res = agent_executor.invoke({"input": pergunta, "chat_history": chat_history})
        resposta_final = res["output"]
    except Exception as e:
        houve_erro = True
        resposta_final = f"⚠️ Erro interno no raciocínio do agente: {e}"
    
    if on_evento:
        on_evento("status", "🏁 O Agente concluiu sua execução e encontrou a resposta final.")
    
    compilacao = ({"status": "nao_executada", "erros": [], "ignorados": 0} if houve_erro
                  else _compilar_codigo(resposta_final))
    valido = not houve_erro and compilacao["status"] != "erros"
    
    # Mockando a estrutura que o frontend espera
    return {
        "resposta": resposta_final,
        "valido": valido,
        "compilacao": compilacao,
        "alucinacoes": [],
        "erros_aridade": [],
        "erros_semanticos": [],
        "includes": {},
        "includes_por_classe": {},
        "metodos_suspeitos": [],
        "classes_legado": [],
        "classes_indisponiveis": {},
        "fontes_nao_api": [],
        "correcoes_automaticas": [],
        "fontes": fontes_usadas,
        "tentativas": 1,
    }
