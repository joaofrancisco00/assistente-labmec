"""
Interface web do Assistente LabMeC (Gradio).

Uso:
    venv/bin/python app.py
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
    OllamaLLM,
    HuggingFaceEmbeddings,
    EMBED_MODEL,
    gerar_codigo,
    _registrar_interacao,
)

# ── Carga única (modelos, índices, whitelists) ─────────────────────────────────
print("Carregando modelos e banco de dados (uma vez, na subida do app)...")
_embeddings = HuggingFaceEmbeddings(
    model_name=EMBED_MODEL,
    encode_kwargs={"normalize_embeddings": True},
)
_headers_db, _examples_db, _wiki_db = pipeline._carregar_bancos(_embeddings)
_whitelist           = pipeline._carregar_whitelist()
_headers_whitelist   = pipeline._carregar_headers_whitelist()
_class_header_index  = pipeline._carregar_class_header_index()
_collisions          = pipeline._carregar_collisions()
_methods_whitelist   = pipeline._carregar_methods_whitelist()
_class_methods_index = pipeline._carregar_class_methods_index()
_renames             = pipeline._carregar_renames()
_legacy_classes      = pipeline._carregar_legacy_classes()
_system_base         = pipeline._carregar_system_prompt()
_llm                 = OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)
print("Pronto.\n")


# ── Formatação da resposta final ───────────────────────────────────────────────

def _rodape(resultado: dict) -> str:
    """Status de validação + fontes, no rodapé da resposta (Markdown)."""
    linhas = []

    if resultado["correcoes_automaticas"]:
        linhas.append("🔧 **Correções automáticas**: " + ", ".join(resultado["correcoes_automaticas"]))

    compilacao = resultado.get("compilacao", {"status": "nao_executada", "erros": []})

    if not resultado["valido"]:
        if resultado["alucinacoes"]:
            linhas.append("⚠️ **Classes não verificadas**: " + ", ".join(resultado["alucinacoes"]))
        if resultado["includes"]:
            linhas.append("⚠️ **Headers não verificados**: " + ", ".join(resultado["includes"].keys()))
        if resultado["includes_por_classe"]:
            linhas.append("⚠️ **Header faltando**: " + ", ".join(
                f"{c} → {h}" for c, h in resultado["includes_por_classe"].items()))
        if resultado["metodos_suspeitos"]:
            linhas.append("⚠️ **Métodos não encontrados**: " + ", ".join(
                f"{c}::{m}" for c, m in resultado["metodos_suspeitos"]))
        # Erro de compilador é o único que a checagem de nomes não pega (método
        # de outra classe, assinatura errada) — vale mostrar a mensagem crua,
        # que diz exatamente onde está o problema
        if compilacao["erros"]:
            linhas.append("❌ **O compilador recusou o código**:\n" + "\n".join(
                f"- `{e}`" for e in compilacao["erros"]))
    elif compilacao["status"] == "ok":
        linhas.append("✅ **Compilado** — o g++ aceitou o código: classes, métodos e "
                      "assinaturas existem de verdade (o resultado físico não é verificado)")
    else:
        linhas.append("✅ **Nomes verificados** — classes, headers e métodos existem no NeoPZ "
                      "(semântica e assinaturas não são checadas)")

    if resultado["classes_legado"]:
        dicas = [f"{c} → prefira {_renames[c]}" if c in _renames else c
                 for c in resultado["classes_legado"]]
        linhas.append("⚠️ **API antiga usada**: " + ", ".join(dicas))

    fontes = ", ".join(sorted(Path(f).name for f in resultado["fontes"]))
    linhas.append(f"📄 **Fontes** ({resultado['tentativas']} tentativa(s)): {fontes}")

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

def responder(mensagem, historico_ui):
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
            resultado = gerar_codigo(
                mensagem, _llm, _headers_db, _examples_db,
                _whitelist, _headers_whitelist, _system_base,
                _class_header_index, _collisions, _wiki_db,
                _methods_whitelist, _class_methods_index,
                _renames, _legacy_classes,
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
    yield "🔎 _Buscando documentação no NeoPZ..._"
    while True:
        item = fila.get()
        if item is None:
            break
        tipo, conteudo = item
        if tipo == "tentativa":
            texto = ""  # nova tentativa recomeça o texto
            status = "" if conteudo == "1" else f"🔁 _Tentativa {conteudo} (corrigindo problemas da anterior)..._"
            yield status or "✍️ _Gerando..._"
        elif tipo == "token":
            texto += conteudo
            yield (status + "\n\n" if status else "") + texto
        elif tipo == "status":
            status = f"_{conteudo}_"
            yield status + "\n\n" + texto
        elif tipo == "erro":
            yield f"⚠️ Erro interno: {conteudo}"
            return

    if resultado_final:
        _registrar_interacao(mensagem, resultado_final)
        yield resultado_final["resposta"] + _rodape(resultado_final)


# ── App ────────────────────────────────────────────────────────────────────────

demo = gr.ChatInterface(
    responder,
    title="🤖 Assistente LabMeC — NeoPZ",
    description=(
        "Assistente de código para a biblioteca **NeoPZ**, com validação "
        "anti-alucinação: classes, headers e métodos são conferidos contra o "
        "código-fonte real. O rodapé de cada resposta mostra o resultado da "
        "validação e as fontes usadas. *Semântica e assinaturas não são "
        "checadas — revise o código antes de usar.*"
    ),
    examples=[
        "Crie uma malha geométrica 2D usando TPZGeoMeshTools e depois uma malha computacional com TPZCompMesh para resolver um problema de Poisson. Mostre o código completo com todos os includes necessários.",
        "Escreva um código completo em C++ com NeoPZ para resolver um problema de elasticidade linear 2D, com todos os includes necessários.",
        "Escreva um código completo em C++ com NeoPZ para resolver um problema de Darcy 2D na formulação mista (fluxo e pressão), com todos os includes necessários.",
        "O que é a classe TPZGeoMesh e para que ela serve?",
    ],
)

# Habilita os botões 👍/👎 nas respostas (o listener .like faz o Gradio
# exibi-los). Precisa ser anexado DENTRO do contexto do Blocks (Gradio 6).
# Protegido: se a API mudar numa versão futura, o app sobe sem feedback em
# vez de quebrar.
try:
    with demo:
        demo.chatbot.like(_registrar_feedback)
except Exception as _e:
    print(f"⚠️  Botões de feedback indisponíveis nesta versão do Gradio: {_e}")

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="0.0.0.0", server_port=7860)
