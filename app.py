"""
Interface web do Assistente LabMeC (Gradio).

Uso:
    uv run app.py
    # local:   http://localhost:7860
    # na rede: http://<ip-desta-maquina>:7860   (alunos do laboratório)

Notas de operação:
  - Uma geração por vez (concurrency_limit=1): o qwen2.5-coder:7b local
    serializa de qualquer jeito, e assim a fila fica explícita para o usuário.
  - Sem autenticação — pensado para a rede interna do laboratório.
  - Cada interação vai para logs/interacoes.jsonl (mesmo log do CLI).
"""
import datetime
import json
import queue
import threading
from pathlib import Path

import gradio as gr

import pipeline
from pipeline import (
    OLLAMA_MODEL,
    NUM_CTX,
    TEMPERATURE,
    EMBED_MODEL,
    gerar_codigo,
    _registrar_interacao,
    obter_llm,
)
from pipeline.agent import gerar_codigo_agente

# ── Carga única (modelos, índices, whitelists) ─────────────────────────────────
from pipeline.context import PipelineContext
_ctx = PipelineContext.load()


# ── Formatação da resposta final ───────────────────────────────────────────────

def _rodape(resultado: dict) -> str:
    """Status de validação + fontes, no rodapé da resposta (Markdown)."""
    linhas = []

    if resultado["correcoes_automaticas"]:
        linhas.append("🔧 **Automatic fixes**: " + ", ".join(resultado["correcoes_automaticas"]))

    compilacao = resultado.get("compilacao", {"status": "nao_executada", "erros": []})

    if not resultado["valido"]:
        if resultado.get("erros_semanticos"):
            linhas.append("⚠️ **Semantic errors**: " + " | ".join(resultado["erros_semanticos"]))
        if resultado.get("erros_aridade"):
            linhas.append("⚠️ **Signature errors (arity)**: " + " | ".join(resultado["erros_aridade"]))
        if resultado["alucinacoes"]:
            linhas.append("⚠️ **Unverified classes**: " + ", ".join(resultado["alucinacoes"]))
        if resultado["includes"]:
            linhas.append("⚠️ **Unverified headers**: " + ", ".join(resultado["includes"].keys()))
        if resultado["includes_por_classe"]:
            linhas.append("⚠️ **Missing header**: " + ", ".join(
                f"{c} → {h}" for c, h in resultado["includes_por_classe"].items()))
        if resultado["metodos_suspeitos"]:
            linhas.append("⚠️ **Methods not found**: " + ", ".join(
                f"{c}::{m}" for c, m in resultado["metodos_suspeitos"]))
        # Erro de compilador é o único que a checagem de nomes não pega (método
        # de outra classe, assinatura errada) — vale mostrar a mensagem crua,
        # que diz exatamente onde está o problema
        if compilacao["erros"]:
            linhas.append("❌ **The compiler rejected the code**:\n" + "\n".join(
                f"- `{e}`" for e in compilacao["erros"]))
    elif compilacao["status"] == "ok":
        linhas.append("✅ **Compiled and verified** — g++ accepted the code, signatures match and no modeling rule was violated.")
    else:
        linhas.append("✅ **Names and signatures verified** — classes, headers, methods and arity really exist in NeoPZ.")

    if resultado["classes_legado"]:
        dicas = [f"{c} → prefer {_ctx.renames[c]}" if c in _ctx.renames else c
                 for c in resultado["classes_legado"]]
        linhas.append("⚠️ **Old API used**: " + ", ".join(dicas))

    # A classe existe no NeoPZ, mas o header não está instalado nesta máquina —
    # o código não compila aqui, e isso NÃO é alucinação do modelo. O selo acima
    # já não diz "Compilado" nesse caso (a compilação é pulada), mas o usuário
    # precisa saber por que o código não vai passar no compilador dele.
    if resultado.get("classes_indisponiveis"):
        linhas.append("⚠️ **Class outside this NeoPZ installation**: " + ", ".join(
            f"{c} ({m})" for c, m in sorted(resultado["classes_indisponiveis"].items())
        ) + " — the class exists in NeoPZ, but its header is not installed here, "
            "so this code does not compile on this machine")

    # Código de teste/benchmark não é exemplo de uso da biblioteca: compila,
    # mas o CMake o transforma em executável separado, nunca na libpz. Ele só
    # chega aqui quando a API real não tinha nada melhor a oferecer — dizer
    # isso é mais honesto do que listá-lo no rodapé como fonte qualquer.
    if resultado.get("fontes_nao_api"):
        linhas.append("ℹ️ **Test/benchmark sources**: " + ", ".join(
            f"`{Path(f).name}`" for f in resultado["fontes_nao_api"]
        ) + " — this is NeoPZ test code, not the library: useful to understand "
            "the class, not as a canonical usage example")

    fontes = ", ".join(sorted(Path(f).name for f in resultado["fontes"]))
    linhas.append(f"📄 **Sources** ({resultado['tentativas']} attempt(s)): {fontes}")

    return "\n\n---\n" + "\n\n".join(linhas)


# ── Feedback 👍/👎 ─────────────────────────────────────────────────────────────

FEEDBACK_FILE = Path("./logs/feedback.jsonl")


def _registrar_feedback(data: gr.LikeData):
    """
    Voto do usuário numa resposta → logs/feedback.jsonl. É o sinal que
    nenhuma whitelist captura: resposta '✅ validada' porém errada na física
    aparece aqui como 👎. A correlação com logs/interacoes.jsonl é feita
    offline pelo conteúdo da resposta.
    """
    try:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        conteudo = data.value
        if isinstance(conteudo, dict):  # formatos novos do Gradio
            conteudo = conteudo.get("value", str(conteudo))
        registro = {
            "quando":   datetime.datetime.now().isoformat(timespec="seconds"),
            "gostou":   bool(data.liked),
            "resposta": str(conteudo)[:4000],
        }
        with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        print(f"  {'👍' if data.liked else '👎'} feedback registrado")
    except Exception as e:
        print(f"  (feedback falhou: {e})")


# ── Função de chat (generator: streaming na interface) ─────────────────────────

def responder(mensagem, historico_ui, usar_agente=False):
    # histórico do Gradio (messages) -> pares (pergunta, resposta) do pipeline
    pares = []
    pergunta_anterior = None
    for m in historico_ui or []:
        conteudo = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        papel = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
        if not isinstance(conteudo, str):
            continue
        if papel == "user":
            pergunta_anterior = conteudo
        elif papel == "assistant" and pergunta_anterior is not None:
            # remove o rodapé de validação do turno anterior — não é conteúdo
            pares.append((pergunta_anterior, conteudo.split("\n\n---\n")[0]))
            pergunta_anterior = None

    fila = queue.Queue()
    resultado_final = {}

    def trabalhar():
        try:
            if usar_agente:
                resultado = gerar_codigo_agente(
                    mensagem, _ctx,
                    historico=pares,
                    on_evento=lambda tipo, texto: fila.put((tipo, texto)),
                )
            else:
                resultado = gerar_codigo(
                    mensagem, _ctx,
                    historico=pares,
                    on_evento=lambda tipo, texto: fila.put((tipo, texto)),
                )
            resultado_final.update(resultado)
        except Exception as e:
            fila.put(("erro", f"{type(e).__name__}: {e}"))
        finally:
            fila.put(None)

    threading.Thread(target=trabalhar, daemon=True).start()

    texto = ""
    status = ""
    yield "🔎 _Searching the NeoPZ documentation..._"
    while True:
        item = fila.get()
        if item is None:
            break
        tipo, conteudo = item
        if tipo == "tentativa":
            texto = ""  # nova tentativa recomeça o texto
            status = "" if conteudo == "1" else f"🔁 _Attempt {conteudo} (fixing problems from the previous one)..._"
            yield status or "✍️ _Generating..._"
        elif tipo == "token":
            texto += conteudo
            yield (status + "\n\n" if status else "") + texto
        elif tipo == "status":
            status = f"_{conteudo}_"
            yield status + "\n\n" + texto
        elif tipo == "erro":
            yield f"⚠️ Internal error: {conteudo}"
            return

    if resultado_final:
        _registrar_interacao(mensagem, resultado_final)
        yield resultado_final["resposta"] + _rodape(resultado_final)


# ── App ────────────────────────────────────────────────────────────────────────

_theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="slate",
    neutral_hue="slate",
)

demo = gr.ChatInterface(
    responder,
    title="🤖 LabMeC Assistant — NeoPZ",
    chatbot=gr.Chatbot(
        render_markdown=True,
        avatar_images=[None, "🤖"],
        height=600,
    ),
    textbox=gr.Textbox(
        placeholder="E.g.: How do I create a 2D mesh with TPZGeoMeshTools?",
        container=False,
        scale=7,
    ),
    fill_height=True,
    description=(
        "Code assistant for the **NeoPZ** library, with strict validation: "
        "classes, headers, methods, number of arguments and semantic rules are "
        "checked against the real source code, and the code also goes through "
        "the g++ compiler. The footer shows the detailed validation result."
    ),
    examples=[
        "Create a 2D geometric mesh using TPZGeoMeshTools and then a computational mesh with TPZCompMesh to solve a Poisson problem. Show the complete code with all the necessary includes.",
        "Write complete C++ code with NeoPZ to solve a 2D linear elasticity problem, with all the necessary includes.",
        "Write complete C++ code with NeoPZ to solve a 2D Darcy problem in the mixed formulation (flux and pressure), with all the necessary includes.",
        "What is the TPZGeoMesh class and what is it for?",
    ],
    additional_inputs=[
        gr.Checkbox(label="Use Autonomous Agent (the LLM searches and compiles the code on its own before answering)", value=False)
    ],
)

# Habilita os botões 👍/👎 nas respostas. Protegido: se a API mudar numa
# versão futura, o app sobe sem feedback em vez de quebrar.
try:
    with demo:
        demo.chatbot.like(_registrar_feedback)
except Exception as _e:
    print(f"⚠️  Botões de feedback indisponíveis nesta versão do Gradio: {_e}")

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0", server_port=7860, theme=_theme,
    )

