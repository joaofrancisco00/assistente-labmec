from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from .agent_tools import obter_todas_ferramentas
from . import _recursos_validacao, _resultado_de, _verificar_resposta
from .config import OLLAMA_MODEL, TEMPERATURE, NUM_CTX
from .context import PipelineContext
from .prompt import _formatar_contexto
from .retrieval import _recuperar_contexto

def _resultado_sem_verificacao(resposta: str, fontes: set) -> dict:
    v = {"resposta": resposta, "alucinacoes": [], "erros_aridade": [], "erros_semanticos": [],
         "includes": {}, "includes_por_classe": {}, "metodos_suspeitos": [],
         "compilacao": {"status": "nao_executada", "erros": [], "ignorados": 0},
         "classes_legado": [], "classes_indisponiveis": {}, "correcoes_automaticas": []}
    return _resultado_de(v, False, fontes, 1)


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
        return _resultado_sem_verificacao(
            "⚠️ Error: the current model does not support Tool Calling (Function Calling). "
            "Switch to Gemini to use the Agent.", set())

    if on_evento:
        on_evento("status", "🔎 Retrieving NeoPZ context for the agent...")
    h_docs, e_docs, w_docs, fontes = _recuperar_contexto(
        pergunta, ctx.headers_db, ctx.examples_db, ctx.wiki_db)
    contexto = _formatar_contexto(h_docs, e_docs, w_docs)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a Senior Software Engineer specialized in C++ and in the 'NeoPZ' Finite Element library.\n"
         "Your mission is to help the user by generating clean, error-free C++ code that compiles perfectly.\n"
         "GOLDEN RULES:\n"
         "1. Generated code must be placed in Markdown blocks (```cpp ... ```).\n"
         "2. Below you have already received a RETRIEVED CONTEXT with class declarations, real examples and wiki recipes relevant to the question. Use it as your main basis — the recipes are complete code already verified by compilation.\n"
         "   Only call the search tools (`get_class_declaration`, `search_code_examples`, `search_wiki_docs`) if something essential is missing from the context, or to understand a compiler error.\n"
         "3. ALWAYS test your code with the `test_compilation` tool BEFORE giving the final answer.\n"
         "   - If the compiler returns errors, you MUST analyze the error, use tools if needed, and test again with the fixes.\n"
         "   - You may only finish and give your definitive answer once the compilation test returns 'SUCCESS', or after 4 failed attempts.\n"
         "4. Always answer in English.\n"
        ),
        ("system", "RETRIEVED CONTEXT:\n{contexto}"),
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
        on_evento("status", "🤖 The Agent is reasoning (follow the tool calls in the terminal)...")
    
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
        if isinstance(resposta_final, list):
            resposta_final = "".join(p.get("text", "") if isinstance(p, dict) else str(p)
                                     for p in resposta_final)
    except Exception as e:
        houve_erro = True
        resposta_final = f"⚠️ Internal error in the agent reasoning: {e}"
    
    if on_evento:
        on_evento("status", "🏁 The Agent finished and produced its final answer.")
    
    if houve_erro:
        return _resultado_sem_verificacao(resposta_final, fontes_usadas)

    v = _verificar_resposta(resposta_final, **_recursos_validacao(ctx), on_evento=on_evento)
    return _resultado_de(v, v["valido"], fontes_usadas, 1)
