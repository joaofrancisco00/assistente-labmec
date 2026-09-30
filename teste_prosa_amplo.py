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
    # Geometria e Malha Geométricas
    {
        "nome": "prosa_tpzgeonode",
        "pergunta": "O que compõe um TPZGeoNode no NeoPZ e qual a sua relação com os elementos geométricos?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZGeoNode" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzgeoel",
        "pergunta": "Qual a responsabilidade principal da classe TPZGeoEl no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZGeoEl" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzgengrid2d",
        "pergunta": "Como a classe TPZGenGrid2D simplifica a criação de malhas geométricas bidimensionais?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZGenGrid2D" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Elementos Computacionais
    {
        "nome": "prosa_tpzinterpolatedelement",
        "pergunta": "Explique a diferença entre um TPZCompEl genérico e um TPZInterpolatedElement no NeoPZ.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZInterpolatedElement" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzinterfaceelement",
        "pergunta": "Por que o NeoPZ precisa da classe TPZInterfaceElement em formulações mistas e métodos de Galerkin Descontínuo (DG)?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZInterfaceElement" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzcompeldisc",
        "pergunta": "O que caracteriza a classe TPZCompElDisc e como ela difere de elementos contínuos?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZCompElDisc" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzmaterialdata",
        "pergunta": "Explique o papel da classe TPZMaterialData (ou TPZMaterialDataT) no NeoPZ na comunicação entre os elementos computacionais e a lei constitutiva do material.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZMaterialData" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Física e Materiais
    {
        "nome": "prosa_tpzdarcyflow",
        "pergunta": "Qual a diferença principal entre o uso de TPZDarcyFlow e TPZMixedDarcyFlow no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe1":    lambda r: "TPZDarcyFlow" in r["resposta"],
            "menciona_classe2":    lambda r: "TPZMixedDarcyFlow" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzelasticity3d",
        "pergunta": "Quais são os parâmetros físicos essenciais necessários para inicializar a classe TPZElasticity3D no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZElasticity3D" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzbndcondt",
        "pergunta": "Explique como a classe TPZBndCondT utiliza templates para aplicar condições de contorno de Dirichlet, Neumann e Mista no NeoPZ.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZBndCondT" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Integração Numérica e Matemática
    {
        "nome": "prosa_tpztransform",
        "pergunta": "O que a classe TPZTransform faz no contexto do NeoPZ em relação aos mapas geométricos?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZTransform" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzintquad",
        "pergunta": "Como a classe TPZIntQuad abstrai os pontos e pesos de integração para domínios quadrilaterais no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZIntQuad" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzinttriangle",
        "pergunta": "Explique como o NeoPZ usa a classe TPZIntTriangle para integrar funções num elemento triangular.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZIntTriangle" in r["resposta"] or "TPZIntPoints" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Estruturas de Dados
    {
        "nome": "prosa_tpzmanvector",
        "pergunta": "Qual a principal vantagem de performance do TPZManVector no NeoPZ em relação ao std::vector padrão?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZManVector" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzchunkvector",
        "pergunta": "Explique o funcionamento da alocação de objetos em pedaços (chunks) pela classe TPZChunkVector no NeoPZ.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZChunkVector" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzstack",
        "pergunta": "Para que serve a classe TPZStack no NeoPZ e quando ela deve ser preferida no lugar de outras listas?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZStack" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Solvers e Matrizes
    {
        "nome": "prosa_tpzfnmatrix",
        "pergunta": "O que caracteriza a TPZFNMatrix no NeoPZ em relação à alocação de memória na stack versus heap?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZFNMatrix" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpznonlinearanalysis",
        "pergunta": "Como a classe TPZNonLinearAnalysis executa o método de Newton-Raphson no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZNonLinearAnalysis" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzsspstructmatrix",
        "pergunta": "Qual a diferença entre a classe TPZSSpStructMatrix e a matriz esparsa não simétrica no armazenamento de matrizes de rigidez globais?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZSSpStructMatrix" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzparfrontstructmatrix",
        "pergunta": "Descreva o propósito da classe TPZParFrontStructMatrix em problemas estruturais grandes no NeoPZ e como ela aproveita o processamento em paralelo.",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZParFrontStructMatrix" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    {
        "nome": "prosa_tpzblock",
        "pergunta": "Como a classe TPZBlock auxilia na estruturação de matrizes por blocos independentes no NeoPZ?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZBlock" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
    # Resultados
    {
        "nome": "prosa_tpzvtkgeomesh",
        "pergunta": "Qual o principal caso de uso para utilizar TPZVTKGeoMesh no NeoPZ ao exportar arquivos VTK?",
        "checks": {
            "validacao_limpa":     lambda r: r["valido"],
            "menciona_classe":     lambda r: "TPZVTKGeoMesh" in r["resposta"],
            "sem_receita_colada":  lambda r: _sem_receita_colada(r["resposta"]),
        },
    },
]


def main():
    from pipeline.context import PipelineContext
    ctx = PipelineContext.load()

    resultados_eval = []
    total_checks = falhas = 0

    for caso in CASOS:
        print(f"\n{'=' * 60}\n▶ {caso['nome']}\n{'=' * 60}")
        resultado = gerar_codigo(caso["pergunta"], ctx)
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
