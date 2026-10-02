"""
Eval automático do assistente — roda as perguntas-benchmark REAIS (LLM +
retrieval de verdade) e verifica propriedades esperadas de cada resposta.

Uso:
    uv run eval_benchmark.py                        # todos os casos, pipeline RAG
    uv run eval_benchmark.py --agente               # mesmos casos, modo agente
    uv run eval_benchmark.py --grupo sem_receita    # só casos sem receita em flows/
    uv run eval_benchmark.py --casos snippet_vtk,espaco_hdiv

Quando rodar: antes e depois de mexer em prompt, receitas, índice, whitelists
ou modelo — é a trava contra regressão silenciosa. Os casos "com receita" têm
uma receita quase idêntica em wiki/flows/ e medem se o modelo a segue; os
"sem receita" medem generalização (3D, refinamento, HDiv, snippets, conceitos).

Saída: tabela ✅/❌ por verificação + placar por grupo; cada rodada é salva em
logs/eval_<data>.json (logs/eval_agente_<data>.json no modo agente), com as
respostas. Código de saída != 0 se qualquer verificação falhar.
"""
import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

import pipeline
from pipeline import (
    EMBED_MODEL, NUM_CTX, OLLAMA_MODEL, TEMPERATURE,
    HuggingFaceEmbeddings, OllamaLLM, gerar_codigo, obter_llm,
)

# ── Casos de benchmark ─────────────────────────────────────────────────────────
# Cada check recebe o dict `resultado` de gerar_codigo (a resposta final está
# em resultado["resposta"]) e devolve True se a propriedade esperada vale.
#
# Nota: TEMPERATURE=0.1 (não zero) — pequenas variações entre rodadas são
# esperadas; o sinal de regressão é a falha PERSISTENTE, não a pontual.


def _sem_receita_colada(resposta: str) -> bool:
    """
    Regressão da sobre-ancoragem: em pergunta explicativa, o modelo colava a
    receita completa do Poisson como "exemplo". Um exemplo CURTO com main é
    aceitável (até desejável); o que não pode é a receita inteira — detectada
    pela impressão digital do pipeline completo (2+ marcadores juntos).
    """
    marcadores = ("CreateGeoMeshOnGrid", "DefineGraphMesh", "SetForcingFunction")
    return sum(m in resposta for m in marcadores) < 2


# O modelo copiava o selo "compilado e executado com sucesso" das receitas e
# o aplicava ao código que ELE gerou (que nunca foi compilado) — confiança
# falsa, o pior tipo de erro para um aluno. Selo removido das receitas +
# instrução no prompt; este check protege as duas correções.
_ALEGACAO_COMPILACAO_RE = re.compile(
    r"(compil|execut)[a-zá-úâ-ûã-õç]*(\s+\S+){0,4}\s+com\s+sucesso"
    r"|\b(compil|execut|test|ran\b|run)\w*(\s+\S+){0,4}\s+successfully"
    r"|\bsuccessfully\s+(compiled|executed|tested|ran)\b"
    r"|\b(has been|have been|was)\s+(compiled|tested|executed)\b", re.IGNORECASE)


def _sem_alegacao_de_compilacao(resposta: str) -> bool:
    return not _ALEGACAO_COMPILACAO_RE.search(resposta)


def _exemplo_usa_a_classe(resposta: str, classe: str) -> bool:
    """Se a explicação inclui um programa (int main), ele deve usar a própria
    classe explicada — não um exemplo de outro assunto."""
    pos = resposta.find("int main(")
    if pos == -1:
        return True  # sem programa — nada a exigir
    return classe in resposta[pos:]


# TPZElasticity2D(id, E, nu, fx, fy, planestress) — 6 argumentos, 5 vírgulas.
# É o ÚNICO construtor que inicializa fConstitutiveLaw, o membro que calcula
# tensão. Com (id) + SetElasticity o programa compila, roda, termina com exit 0
# e grava o VTK — com SigmaX/SigmaY ZERADOS em todos os pontos e deslocamento
# errado. Nenhuma validação de nome pega: os dois nomes existem.
#
# ATENÇÃO ao histórico: até ago/2026 este check exigia exatamente o CONTRÁRIO
# ("SetElasticity" in resposta), porque na revisão de 2022 o construtor completo
# tinha o corpo vazio. O develop consertou o construtor e o padrão se inverteu.
# Por isso o check mudou de nome — comparar `construtor_seguro` de evals antigos
# com `construtor_completo` daqui pra frente seria comparar coisas opostas.
_CTOR_ELAST_COMPLETO_RE = re.compile(r"TPZElasticity2D\s*\(([^)]*,){5}[^)]*\)")


def _elasticidade_bem_construida(resposta: str) -> bool:
    return (_CTOR_ELAST_COMPLETO_RE.search(resposta) is not None
            and "SetElasticity" not in resposta)


def _compilou(r: dict) -> bool:
    return r["compilacao"]["status"] == "ok"


def _sem_main(resposta: str) -> bool:
    return "int main(" not in resposta


_DIM_3_RE = re.compile(r"\bdim\w*\s*(=\s*3\b|\{\s*3\s*\})"
                       r"|TPZMatPoisson\s*<\s*\w*\s*>\s*\(\s*\w+\s*,\s*3\s*\)")

_BC_TIPO_RE = re.compile(r"CreateBC\s*\([^,()]+,[^,()]+,\s*(\w+)\s*,")


def _bc_neumann(resposta: str) -> bool:
    tipo = _BC_TIPO_RE.search(resposta)
    if tipo is None:
        return False
    if tipo.group(1) == "1":
        return True
    return re.search(rf"\b{tipo.group(1)}\s*(=\s*1\b|\{{\s*1\s*\}})", resposta) is not None


def _refina_uniformemente(resposta: str) -> bool:
    return "UniformRefinement" in resposta or "Divide" in resposta


def _exporta_vtk(resposta: str) -> bool:
    return (("DefineGraphMesh" in resposta and "PostProcess" in resposta)
            or "TPZVTKGenerator" in resposta)


_API_CONDENSACAO = ("CreatedCondensedElements", "CondenseElements",
                    "GroupAndCondenseElements", "TPZCondensedCompEl")

CASOS = [
    {
        "nome": "poisson_2d_completo",
        "receita": True,
        "pergunta": ("Create a 2D geometric mesh using TPZGeoMeshTools and then a "
                     "computational mesh with TPZCompMesh to solve a Poisson "
                     "problem. Show the complete code with all the necessary includes."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "material_correto":    lambda r: "TPZMatPoisson" in r["resposta"],
            "include_qualificado": lambda r: "Poisson/TPZMatPoisson.h" in r["resposta"],
            "sem_api_antiga":      lambda r: ("TPZDummyFunction" not in r["resposta"]
                                              and "TPZMatPlaca2" not in r["resposta"]
                                              and not r["classes_legado"]),
            "esqueleto_completo":  lambda r: ("AutoBuild" in r["resposta"]
                                              and "Assemble" in r["resposta"]),
            "max_2_tentativas":    lambda r: r["tentativas"] <= 2,
        },
    },
    {
        "nome": "elasticidade_2d",
        "receita": True,
        "pergunta": ("Write complete C++ code with NeoPZ to solve a "
                     "2D linear elasticity problem, with all the necessary includes."),
        "checks": {
            "validacao_limpa":    lambda r: r["valido"],
            "material_2d":        lambda r: "TPZElasticity2D" in r["resposta"],
            "nao_usa_3d_em_2d":   lambda r: "TPZElasticity3D" not in r["resposta"],
            "construtor_completo": lambda r: _elasticidade_bem_construida(r["resposta"]),
            "sem_api_antiga":     lambda r: not r["classes_legado"],
            "max_2_tentativas":   lambda r: r["tentativas"] <= 2,
        },
    },
    {
        "nome": "darcy_misto_2d",
        "receita": True,
        "pergunta": ("Write complete C++ code with NeoPZ to solve a "
                     "2D Darcy problem in the mixed formulation (flux and pressure), with "
                     "all the necessary includes."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "material_misto":      lambda r: "TPZMixedDarcyFlow" in r["resposta"],
            "malha_multifisica":   lambda r: ("TPZMultiphysicsCompMesh" in r["resposta"]
                                              and "BuildMultiphysicsSpace" in r["resposta"]),
            "solver_ponto_de_sela": lambda r: "ELDLt" in r["resposta"],
            "sem_cfd":             lambda r: "TPZFlowCompMesh" not in r["resposta"],
            "max_2_tentativas":    lambda r: r["tentativas"] <= 2,
            "sem_alegacao_falsa":  lambda r: _sem_alegacao_de_compilacao(r["resposta"]),
        },
    },
    {
        # Família SEM receita até jul/2026: o modelo escolhia TPZHybridDarcyFlow
        # (espaços combinados) porque o catálogo — único doc que aponta
        # TPZDarcyFlow — era espremido do retrieval pelas receitas.
        "nome": "darcy_h1_2d",
        "receita": True,
        "pergunta": ("Write complete C++ code with NeoPZ to solve a "
                     "2D Darcy flow problem using the H1 approximation space, "
                     "with all the necessary includes."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "material_h1":         lambda r: "TPZDarcyFlow" in r["resposta"],
            "nao_usa_hibrido":     lambda r: "TPZHybridDarcyFlow" not in r["resposta"],
            "nao_usa_misto":       lambda r: ("TPZMixedDarcyFlow" not in r["resposta"]
                                              and "TPZMultiphysicsCompMesh" not in r["resposta"]),
            "include_qualificado": lambda r: "DarcyFlow/TPZDarcyFlow.h" in r["resposta"],
            "permeabilidade":      lambda r: "SetConstantPermeability" in r["resposta"],
            "sem_alegacao_falsa":  lambda r: _sem_alegacao_de_compilacao(r["resposta"]),
            "max_2_tentativas":    lambda r: r["tentativas"] <= 2,
        },
    },
    {
        "nome": "prosa_tpzgeomesh",
        "receita": False,
        "pergunta": "What is the TPZGeoMesh class and what is it for?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZGeoMesh" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "exemplo_usa_a_classe": lambda r: _exemplo_usa_a_classe(r["resposta"], "TPZGeoMesh"),
        },
    },
    {
        "nome": "explicar_tpzint1d",
        "receita": False,
        "pergunta": "Explain the NeoPZ TPZInt1d class: what does it do and what are its main methods?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZInt1d" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "exemplo_usa_a_classe": lambda r: _exemplo_usa_a_classe(r["resposta"], "TPZInt1d"),
        },
    },
    {
        "nome": "poisson_3d_hexaedros",
        "receita": False,
        "pergunta": ("Write complete C++ code with NeoPZ to solve a 3D Poisson problem "
                     "on a unit cube meshed with hexahedra, with all the necessary includes."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "compilou":            _compilou,
            "material_correto":    lambda r: "TPZMatPoisson" in r["resposta"],
            "malha_hexaedrica":    lambda r: "EHexahedral" in r["resposta"],
            "dimensao_3d":         lambda r: _DIM_3_RE.search(r["resposta"]) is not None,
            "sem_api_antiga":      lambda r: not r["classes_legado"],
        },
    },
    {
        "nome": "refinamento_uniforme",
        "receita": False,
        "pergunta": ("Write complete C++ code with NeoPZ that creates a 2D quadrilateral "
                     "geometric mesh with TPZGeoMeshTools and refines it uniformly twice, "
                     "printing the number of elements before and after the refinement."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "compilou":            _compilou,
            "malha_por_ferramenta": lambda r: "CreateGeoMeshOnGrid" in r["resposta"],
            "refina":              lambda r: _refina_uniformemente(r["resposta"]),
            "sem_api_antiga":      lambda r: not r["classes_legado"],
        },
    },
    {
        "nome": "snippet_vtk",
        "receita": False,
        "pergunta": ("Show a short snippet that exports the solution of an already solved "
                     "TPZLinearAnalysis to a VTK file to be opened in Paraview."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "exporta_vtk":         lambda r: _exporta_vtk(r["resposta"]),
            "e_snippet":           lambda r: _sem_main(r["resposta"]),
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "snippet_bc_neumann",
        "receita": False,
        "pergunta": ("Give me a snippet that adds a Neumann boundary condition with a "
                     "prescribed flux of 2.0 to an existing TPZMatPoisson material."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "usa_createbc":        lambda r: "CreateBC" in r["resposta"],
            "tipo_neumann":        lambda r: _bc_neumann(r["resposta"]),
            "e_snippet":           lambda r: _sem_main(r["resposta"]),
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "espaco_hdiv",
        "receita": False,
        "pergunta": ("Write C++ code with NeoPZ that creates a computational mesh with an "
                     "H(div) approximation space of order 2 on a 2D quadrilateral "
                     "geometric mesh."),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "espaco_hdiv":         lambda r: ("SetAllCreateFunctionsHDiv" in r["resposta"]
                                              or "TPZHDivApproxCreator" in r["resposta"]),
            "nao_usa_continuo":    lambda r: "SetAllCreateFunctionsContinuous" not in r["resposta"],
            "ordem_2":             lambda r: re.search(r"SetDefaultOrder\s*\(\s*2\s*\)",
                                                       r["resposta"]) is not None,
            "sem_api_antiga":      lambda r: not r["classes_legado"],
        },
    },
    {
        "nome": "explicar_condensacao",
        "receita": False,
        "pergunta": ("What is static condensation and how is it applied to a computational "
                     "mesh in NeoPZ?"),
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "cita_api_real":       lambda r: any(a in r["resposta"] for a in _API_CONDENSACAO),
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "sem_alegacao_falsa":  lambda r: _sem_alegacao_de_compilacao(r["resposta"]),
        },
    },
]


def _argumentos():
    parser = argparse.ArgumentParser(description="Benchmark de regressão do assistente NeoPZ")
    parser.add_argument("--agente", action="store_true",
                        help="roda o modo agente (tool use) em vez do pipeline RAG")
    parser.add_argument("--grupo", choices=("com_receita", "sem_receita"),
                        help="só os casos com (ou sem) receita equivalente em wiki/flows/")
    parser.add_argument("--casos", help="nomes dos casos separados por vírgula")
    args = parser.parse_args()

    casos = CASOS
    if args.grupo:
        casos = [c for c in casos if c["receita"] == (args.grupo == "com_receita")]
    if args.casos:
        pedidos = [n.strip() for n in args.casos.split(",") if n.strip()]
        desconhecidos = set(pedidos) - {c["nome"] for c in CASOS}
        if desconhecidos:
            parser.error(f"casos desconhecidos: {', '.join(sorted(desconhecidos))}")
        casos = [c for c in casos if c["nome"] in pedidos]
    return args, casos


def main():
    args, casos = _argumentos()
    modo = "agente" if args.agente else "rag"

    from pipeline.context import PipelineContext
    ctx = PipelineContext.load()
    llm = ctx.llm
    if args.agente:
        from pipeline.agent import gerar_codigo_agente
        gerar = lambda pergunta: gerar_codigo_agente(pergunta, ctx)
    else:
        gerar = lambda pergunta: gerar_codigo(pergunta, ctx)

    resultados_eval = []
    placar = {True: [0, 0], False: [0, 0]}

    for caso in casos:
        print(f"\n{'=' * 60}\n▶ {caso['nome']} ({modo})\n{'=' * 60}")
        start_time = time.time()
        resultado = gerar(caso["pergunta"])
        elapsed = time.time() - start_time
        print(f"⏱️ Tempo da resposta: {elapsed:.2f}s")
        checks_caso = {}
        for nome_check, fn in caso["checks"].items():
            try:
                ok = bool(fn(resultado))
            except Exception:
                ok = False
            checks_caso[nome_check] = ok
            placar[caso["receita"]][0] += ok
            placar[caso["receita"]][1] += 1
            print(f"  {'✅' if ok else '❌'} {nome_check}")
        resultados_eval.append({
            "caso":       caso["nome"],
            "receita":    caso["receita"],
            "checks":     checks_caso,
            "tentativas": resultado["tentativas"],
            "valido":     resultado["valido"],
            "compilacao": resultado["compilacao"]["status"],
            "tempo_s":    round(elapsed, 1),
            "resposta":   resultado["resposta"],
        })

        # Respiro de 4s para evitar bater no limite de requisições da API gratuita do Gemini
        time.sleep(4)

    ok_total = placar[True][0] + placar[False][0]
    total = placar[True][1] + placar[False][1]
    print(f"\n{'=' * 60}")
    print(f"  RESULTADO ({modo}): {ok_total}/{total} verificações OK"
          + ("" if ok_total == total else f"  ({total - ok_total} FALHARAM)"))
    for com_receita, rotulo in ((True, "com receita"), (False, "sem receita")):
        if placar[com_receita][1]:
            print(f"    {rotulo}: {placar[com_receita][0]}/{placar[com_receita][1]}")
    print("=" * 60)

    sufixo = "_agente" if args.agente else ""
    saida = Path("logs") / f"eval{sufixo}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps({
        "quando":      datetime.datetime.now().isoformat(timespec="seconds"),
        "modelo":      getattr(llm, "model", "desconhecido"),
        "modo":        modo,
        "resultado":   f"{ok_total}/{total}",
        "com_receita": "{}/{}".format(*placar[True]),
        "sem_receita": "{}/{}".format(*placar[False]),
        "casos":       resultados_eval,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rodada salva em {saida}")

    sys.exit(1 if ok_total != total else 0)


if __name__ == "__main__":
    main()
