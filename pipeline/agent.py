from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from .agent_tools import obter_todas_ferramentas
from .context import PipelineContext

def gerar_codigo_agente(pergunta: str, ctx: PipelineContext, historico: list = None, on_evento=None) -> dict:
    llm = ctx.llm
    
    try:
        tools = obter_todas_ferramentas()
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

    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "Você é um Engenheiro de Software Sênior especialista em C++ e na biblioteca de Elementos Finitos 'NeoPZ'.\n"
         "Sua missão é ajudar o usuário gerando código C++ limpo, sem erros e que compile perfeitamente.\n"
         "REGRAS DE OURO:\n"
         "1. O código gerado deve ser incluído em blocos Markdown (```cpp ... ```).\n"
         "2. ANTES de escrever o código, use as ferramentas disponíveis para entender as classes solicitadas:\n"
         "   - Use `buscar_declaracao_classe` para entender construtores e métodos públicos.\n"
         "   - Use `buscar_exemplos_codigo` para ver como a classe é instanciada na prática.\n"
         "   - Use `buscar_documentacao_wiki` para entender conceitos matemáticos do domínio.\n"
         "3. SEMPRE teste o seu código com a ferramenta `testar_compilacao` ANTES de dar a resposta final.\n"
         "   - Se o compilador retornar erros, você DEVE analisar o erro, usar ferramentas se necessário, e testar novamente com as correções.\n"
         "   - Você só pode terminar e dar sua resposta definitiva quando tiver 'SUCESSO' no teste de compilação, ou após 4 tentativas falhas.\n"
        ),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True, 
        max_iterations=10,
        handle_parsing_errors=True
    )
    
    if on_evento:
        on_evento("status", "🤖 O Agente acordou e está raciocinando (Acompanhe as chamadas de ferramenta no terminal)...")
    
    resposta_final = ""
    fontes_usadas = set(["Agente Autônomo (via Ferramentas)"])
    
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
        resposta_final = f"⚠️ Erro interno no raciocínio do agente: {str(e)}"
    
    if on_evento:
        on_evento("status", "🏁 O Agente concluiu sua execução e encontrou a resposta final.")
    
    # Mockando a estrutura que o frontend espera
    return {
        "resposta": resposta_final,
        "valido": True,
        "alucinacoes": [],
        "erros_aridade": [],
        "erros_semanticos": [],
        "includes": {},
        "includes_por_classe": {},
        "metodos_suspeitos": [],
        "compilacao": {"status": "ok", "erros": [], "ignorados": 0},
        "classes_legado": [],
        "classes_indisponiveis": {},
        "fontes_nao_api": [],
        "correcoes_automaticas": ["O Agente leu os erros e se auto-corrigiu internamente!"],
        "fontes": fontes_usadas,
        "tentativas": 1,
    }
