"""
Compara o pipeline RAG classico (gerar_codigo) com o Agente Autonomo
(gerar_codigo_agente) para uma mesma pergunta, usando o mesmo LLM.

Uso:
    set -a; source .env; set +a; uv run compare_agente_rag.py
"""
import json
import sys
import time
from pathlib import Path

from pipeline import gerar_codigo
from pipeline.agent import gerar_codigo_agente
from pipeline.compilation import _compilar_codigo
from pipeline.context import PipelineContext

PERGUNTA = (
    "Crie uma malha geométrica 2D usando TPZGeoMeshTools e depois uma malha "
    "computacional com TPZCompMesh para resolver um problema de Poisson. "
    "Mostre o código completo com todos os includes necessários."
)

SAIDA = Path("./logs/compare_agente_rag.json")


def _resumo(nome, resultado, dt):
    comp = resultado.get("compilacao", {})
    print(f"\n{'=' * 70}\n  {nome}  ({dt:.1f}s)\n{'=' * 70}")
    print(f"  valido={resultado['valido']}  tentativas={resultado['tentativas']}")
    print(f"  compilacao (auto-relatada): {comp.get('status')}  erros={len(comp.get('erros', []))}")
    print(f"  alucinacoes={resultado['alucinacoes']}  metodos_suspeitos={resultado['metodos_suspeitos']}")
    print(f"  correcoes={resultado['correcoes_automaticas']}")
    print(f"  fontes={sorted(Path(f).name for f in resultado['fontes'])}")
    print(f"  tamanho resposta={len(resultado['resposta'])} chars")


def main():
    ctx = PipelineContext.load()
    print(f"\nLLM: {type(ctx.llm).__name__}")
    print(f"Pergunta: {PERGUNTA}\n")

    saida = {"pergunta": PERGUNTA, "llm": type(ctx.llm).__name__}

    # ── RAG ────────────────────────────────────────────────────────────────
    t0 = time.time()
    rag = gerar_codigo(PERGUNTA, ctx)
    dt_rag = time.time() - t0
    _resumo("RAG (pipeline classico)", rag, dt_rag)

    # ── Agente ─────────────────────────────────────────────────────────────
    t0 = time.time()
    ag = gerar_codigo_agente(PERGUNTA, ctx)
    dt_ag = time.time() - t0
    _resumo("AGENTE (tool use)", ag, dt_ag)

    # O agente devolve validacao mockada; compilar de forma independente
    comp_indep = _compilar_codigo(ag["resposta"])
    print(f"\n  >> compilacao INDEPENDENTE do codigo do agente: {comp_indep['status']}")
    for e in comp_indep.get("erros", []):
        print(f"     - {e}")

    for nome, r, dt in (("rag", rag, dt_rag), ("agente", ag, dt_ag)):
        r = dict(r)
        r["fontes"] = sorted(r["fontes"])
        r["tempo_s"] = round(dt, 1)
        saida[nome] = r
    saida["agente"]["compilacao_independente"] = comp_indep

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultado completo salvo em {SAIDA}")

    print(f"\n{'#' * 70}\n  RESPOSTA RAG\n{'#' * 70}\n{rag['resposta']}")
    print(f"\n{'#' * 70}\n  RESPOSTA AGENTE\n{'#' * 70}\n{ag['resposta']}")


if __name__ == "__main__":
    main()
