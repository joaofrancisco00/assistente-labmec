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

CASOS = [
    {
        "nome": "snippet_tpzfmatrix",
        "pergunta": "Escreva um snippet de código em C++ que instancia uma matriz TPZFMatrix de tamanho 3x3 e preenche a diagonal principal com o valor 1.0.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZFMatrix" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
            "exemplo_usa_a_classe": lambda r: _exemplo_usa_a_classe(r["resposta"], "TPZFMatrix"),
        },
    },
    {
        "nome": "snippet_tpzcompel",
        "pergunta": "Escreva um snippet em C++ mostrando como criar um elemento computacional genérico (TPZCompEl) associado a um elemento geométrico (TPZGeoEl) já existente dentro de uma malha computacional.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZCompEl" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "snippet_tpzmaterial",
        "pergunta": "Gere um código em C++ que mostre como extrair o mapa de materiais (MaterialVec) de um ponteiro para TPZCompMesh e itere sobre eles imprimindo o ID de cada material.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "MaterialVec" in r["resposta"] or "TPZMaterial" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "snippet_tpzanalysis",
        "pergunta": "Forneça o snippet de código exato para rodar o método Run() de um objeto TPZLinearAnalysis e, em seguida, extrair a matriz solução chamando Solution().",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZLinearAnalysis" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "snippet_tpzgeomeshtools",
        "pergunta": "Mostre como usar o método CreateGeoMeshOnGrid da classe TPZGeoMeshTools para construir uma malha retangular simples. Não escreva um programa inteiro, apenas o bloco de criação.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_a_classe":   lambda r: "TPZGeoMeshTools" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
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
    llm                 = obter_llm()

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
