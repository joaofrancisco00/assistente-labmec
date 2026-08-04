"""
Eval automático do assistente — roda as perguntas-benchmark REAIS (LLM +
retrieval de verdade) e verifica propriedades esperadas de cada resposta.

Uso:
    venv/bin/python eval_benchmark.py        # ~5-10 min (usa o Ollama)

Quando rodar: antes e depois de mexer em prompt, receitas, índice, whitelists
ou modelo — é a trava contra regressão silenciosa. Cada caso aqui nasceu de
uma falha real que já foi corrigida; se voltar a falhar, algo regrediu.

Saída: tabela ✅/❌ por verificação + resumo; cada rodada é salva em
logs/eval_<data>.json. Código de saída != 0 se qualquer verificação falhar.
"""
import datetime
import json
import re
import sys
from pathlib import Path

import pipeline
from pipeline import (
    EMBED_MODEL, NUM_CTX, OLLAMA_MODEL, TEMPERATURE,
    HuggingFaceEmbeddings, OllamaLLM, gerar_codigo,
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
    r"(compil|execut)[a-zá-úâ-ûã-õç]*(\s+\S+){0,4}\s+com\s+sucesso", re.IGNORECASE)


def _sem_alegacao_de_compilacao(resposta: str) -> bool:
    return not _ALEGACAO_COMPILACAO_RE.search(resposta)


def _exemplo_usa_a_classe(resposta: str, classe: str) -> bool:
    """Se a explicação inclui um programa (int main), ele deve usar a própria
    classe explicada — não um exemplo de outro assunto."""
    pos = resposta.find("int main(")
    if pos == -1:
        return True  # sem programa — nada a exigir
    return classe in resposta[pos:]

CASOS = [
    {
        "nome": "poisson_2d_completo",
        "pergunta": ("Crie uma malha geométrica 2D usando TPZGeoMeshTools e depois uma "
                     "malha computacional com TPZCompMesh para resolver um problema de "
                     "Poisson. Mostre o código completo com todos os includes necessários."),
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
        "pergunta": ("Escreva um código completo em C++ com NeoPZ para resolver um "
                     "problema de elasticidade linear 2D, com todos os includes necessários."),
        "checks": {
            "validacao_limpa":    lambda r: r["valido"],
            "material_2d":        lambda r: "TPZElasticity2D" in r["resposta"],
            "nao_usa_3d_em_2d":   lambda r: "TPZElasticity3D" not in r["resposta"],
            "construtor_seguro":  lambda r: "SetElasticity" in r["resposta"],  # e não o ctor bugado
            "sem_api_antiga":     lambda r: not r["classes_legado"],
            "max_2_tentativas":   lambda r: r["tentativas"] <= 2,
        },
    },
    {
        "nome": "darcy_misto_2d",
        "pergunta": ("Escreva um código completo em C++ com NeoPZ para resolver um "
                     "problema de Darcy 2D na formulação mista (fluxo e pressão), com "
                     "todos os includes necessários."),
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
        "pergunta": ("Escreva um código completo em C++ com NeoPZ para resolver um "
                     "problema de fluxo de Darcy 2D usando o espaço de aproximação H1, "
                     "com todos os includes necessários."),
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
        "pergunta": "O que é a classe TPZGeoMesh e para que ela serve?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZGeoMesh" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "exemplo_usa_a_classe": lambda r: _exemplo_usa_a_classe(r["resposta"], "TPZGeoMesh"),
        },
    },
    {
        "nome": "explicar_tpzint1d",
        "pergunta": "Explique a classe TPZInt1d do NeoPZ: o que ela faz e quais são seus principais métodos?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZInt1d" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "exemplo_usa_a_classe": lambda r: _exemplo_usa_a_classe(r["resposta"], "TPZInt1d"),
        },
    },
]


def main():
    print("Carregando modelos e banco de dados...")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )
    headers_db, examples_db, wiki_db = pipeline._carregar_bancos(embeddings)
    whitelist           = pipeline._carregar_whitelist()
    headers_whitelist   = pipeline._carregar_headers_whitelist()
    class_header_index  = pipeline._carregar_class_header_index()
    collisions          = pipeline._carregar_collisions()
    methods_whitelist   = pipeline._carregar_methods_whitelist()
    class_methods_index = pipeline._carregar_class_methods_index()
    renames             = pipeline._carregar_renames()
    legacy_classes      = pipeline._carregar_legacy_classes()
    system_base         = pipeline._carregar_system_prompt()
    llm                 = OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)

    resultados_eval = []
    total_checks = falhas = 0

    for caso in CASOS:
        print(f"\n{'=' * 60}\n▶ {caso['nome']}\n{'=' * 60}")
        resultado = gerar_codigo(
            caso["pergunta"], llm, headers_db, examples_db,
            whitelist, headers_whitelist, system_base,
            class_header_index, collisions, wiki_db,
            methods_whitelist, class_methods_index,
            renames, legacy_classes,
        )
        checks_caso = {}
        for nome_check, fn in caso["checks"].items():
            try:
                ok = bool(fn(resultado))
            except Exception:
                ok = False
            checks_caso[nome_check] = ok
            total_checks += 1
            if not ok:
                falhas += 1
            print(f"  {'✅' if ok else '❌'} {nome_check}")
        resultados_eval.append({
            "caso":       caso["nome"],
            "checks":     checks_caso,
            "tentativas": resultado["tentativas"],
            "valido":     resultado["valido"],
        })

    print(f"\n{'=' * 60}")
    print(f"  RESULTADO: {total_checks - falhas}/{total_checks} verificações OK"
          + ("" if not falhas else f"  ({falhas} FALHARAM)"))
    print("=" * 60)

    saida = Path("logs") / f"eval_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps({
        "quando":    datetime.datetime.now().isoformat(timespec="seconds"),
        "modelo":    OLLAMA_MODEL,
        "resultado": f"{total_checks - falhas}/{total_checks}",
        "casos":     resultados_eval,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rodada salva em {saida}")

    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
