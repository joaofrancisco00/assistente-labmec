import difflib
from pathlib import Path

from .correction import _sugerir_correcoes

def _formatar_contexto(h_docs: list, e_docs: list, w_docs: list = None) -> str:
    partes = []

    if h_docs:
        partes.append("=== DECLARAÇÕES DE CLASSE (interface real do NeoPZ) ===")
        for doc in h_docs:
            classe = doc.metadata.get("classe", "")
            label = f"[Classe: {classe}]" if classe else "[Header]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== FIM DAS DECLARAÇÕES ===")

    if e_docs:
        partes.append("\n=== EXEMPLOS DE USO ===")
        for doc in e_docs:
            fonte = Path(doc.metadata.get("source", "")).name
            partes.append(f"[Arquivo: {fonte}]\n{doc.page_content}")
        partes.append("=== FIM DOS EXEMPLOS ===")

    if w_docs:
        partes.append("\n=== DOCUMENTAÇÃO VERIFICADA (wiki de análise) ===")
        for doc in w_docs:
            titulo = doc.metadata.get("titulo", Path(doc.metadata.get("source", "")).stem)
            tipo   = doc.metadata.get("tipo", "")
            label  = f"[{titulo} | {tipo}]" if tipo else f"[{titulo}]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== FIM DA DOCUMENTAÇÃO ===")

    return "\n\n---\n\n".join(partes)


def _formatar_historico(historico: list, max_trocas: int = 3, max_chars_resposta: int = 1200) -> str:
    if not historico:
        return ""
    partes = []
    for pergunta_ant, resposta_ant in historico[-max_trocas:]:
        resposta_ant = resposta_ant or ""
        if len(resposta_ant) > max_chars_resposta:
            resposta_ant = resposta_ant[:max_chars_resposta] + "\n[... resposta truncada ...]"
        partes.append(f"Aluno: {pergunta_ant}\nAssistente: {resposta_ant}")
    return (
        "\n\nHISTÓRICO DA CONVERSA (só contexto — a tarefa atual está no fim):\n"
        + "\n---\n".join(partes)
    )


def _classes_do_contexto(h_docs: list, e_docs: list, w_docs: list = None) -> set:
    classes = set()
    for doc in h_docs or []:
        c = doc.metadata.get("classe", "") or ""
        if c:
            classes.add(c)
    for doc in (e_docs or []) + (w_docs or []):
        valor = doc.metadata.get("classes_usadas", "") or ""
        classes.update(x.strip() for x in valor.split(",") if x.strip())
    return classes


def _montar_prompt(
    pergunta: str,
    contexto: str,
    system_base: str,
    whitelist: set,
    headers_whitelist: set,
    classes_alucinadas: list = None,
    includes_errados: dict = None,
    includes_por_classe: dict = None,
    metodos_suspeitos: list = None,
    methods_whitelist: set = None,
    erros_aridade: list = None,
    erros_compilacao: list = None,
    erros_semanticos: list = None,
    classes_contexto: set = None,
    renames: dict = None,
    historico: list = None,
    destinos: set = None,
) -> str:
    destinos = whitelist if destinos is None else destinos

    referencia = classes_contexto or destinos
    classes_reais = ", ".join(sorted(referencia)[:40]) if referencia else "—"

    instrucao_correcao = ""

    if classes_alucinadas:
        renames = renames or {}
        sugestoes = _sugerir_correcoes(classes_alucinadas, destinos)
        linhas = []
        for classe, matches in sugestoes.items():
            if classe in renames and renames[classe] in destinos:
                linhas.append(
                    f"  - '{classe}' foi RENOMEADA no NeoPZ atual. Use '{renames[classe]}' no lugar."
                )
            elif matches:
                linhas.append(f"  - '{classe}' não existe. Você quis dizer: {', '.join(matches)}?")
            else:
                linhas.append(f"  - '{classe}' não existe e não há classe parecida.")
        instrucao_correcao += (
            "\n\n⚠️ CLASSES INVÁLIDAS:\n"
            + "\n".join(linhas)
        )

    if includes_errados:
        linhas_inc = []
        for inc, sugs in includes_errados.items():
            if sugs:
                linhas_inc.append(f"  - '#include \"{inc}\"' NÃO existe. Use no lugar: {', '.join(sugs)}")
            else:
                linhas_inc.append(
                    f"  - '#include \"{inc}\"' NÃO existe e NÃO há header parecido. "
                    f"NÃO existe header único no NeoPZ. Inclua os headers específicos "
                    f"de cada classe usada (ex: \"pzgmesh.h\" para TPZGeoMesh, "
                    f"\"pzcmesh.h\" para TPZCompMesh)."
                )
        instrucao_correcao += (
            "\n\n⚠️ CORRIJA OS HEADERS — OBRIGATÓRIO:\n"
            + "\n".join(linhas_inc)
            + "\nNÃO repita o header inválido na próxima resposta."
        )

    if includes_por_classe:
        linhas_idx = [
            f"  - Você usou '{classe}' mas não incluiu \"{header}\". Adicione: #include \"{header}\""
            for classe, header in includes_por_classe.items()
        ]
        instrucao_correcao += (
            "\n\n⚠️ HEADERS FALTANDO (segundo índice classe→header, fonte de verdade):\n"
            + "\n".join(linhas_idx)
        )

    if metodos_suspeitos:
        linhas_met = []
        for classe, metodo in metodos_suspeitos:
            sugestoes = difflib.get_close_matches(metodo, methods_whitelist or set(), n=3, cutoff=0.6)
            if sugestoes:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' NÃO existe no NeoPZ. Você quis dizer: {', '.join(sugestoes)}?"
                )
            else:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' NÃO existe no NeoPZ e não há método parecido. "
                    f"Use apenas métodos que aparecem nas declarações de classe do contexto."
                )
        instrucao_correcao += (
            "\n\n⚠️ MÉTODOS INVENTADOS:\n"
            + "\n".join(linhas_met)
            + "\nNÃO use um método só porque parece lógico — confira nas declarações de classe do contexto."
        )

    if erros_aridade:
        instrucao_correcao += (
            "\n\n⚠️ ERRO DE ARIDADE (NÚMERO DE ARGUMENTOS ERRADO):\n"
            + "\n".join(f"  - {e}" for e in erros_aridade)
            + "\nVerifique a assinatura correta do método nas declarações de classe fornecidas."
        )

    if erros_compilacao:
        instrucao_correcao += (
            "\n\n❌ O COMPILADOR (g++) RECUSOU O CÓDIGO ANTERIOR:\n"
            + "\n".join(f"  - {e}" for e in erros_compilacao)
            + "\nCada linha acima é uma API que NÃO existe do jeito que você escreveu.\n"
            "Atenção a 'has no member named X in Y' / 'no member named X': o método X\n"
            "NÃO pertence à classe Y — mesmo que exista em OUTRA classe do NeoPZ.\n"
            "Use somente os métodos que aparecem na declaração da própria classe,\n"
            "no contexto acima. Não troque o método por outro 'parecido' sem conferir."
        )

    if erros_semanticos:
        instrucao_correcao += (
            "\n\n⚠️ ERRO SEMÂNTICO (REGRAS DO NEOPZ VIOLADAS):\n"
            + "\n".join(f"  - {e}" for e in erros_semanticos)
            + "\nO código anterior possui erros de modelagem ou física, que não foram pegos pelo compilador.\n"
            "Siga rigorosamente as instruções acima na próxima resposta."
        )

    if instrucao_correcao:
        instrucao_correcao += "\nReescreva o código usando os nomes corretos."

    return f"""{system_base}

REGRA FUNDAMENTAL: NUNCA invente nomes de classes TPZ nem de headers.
Use SOMENTE classes e headers que aparecem no contexto fornecido abaixo.

REGRA ABSOLUTA SOBRE HEADERS: NUNCA escreva #include "NeoPZ.h" — esse arquivo
NÃO EXISTE e quebra a compilação. NÃO existe header único que inclui tudo.
Para CADA classe, inclua o header específico. Exemplos:
  TPZGeoMesh        → #include "pzgmesh.h"
  TPZCompMesh       → #include "pzcmesh.h"
  TPZLinearAnalysis → #include "TPZLinearAnalysis.h"

Classes TPZ reais relacionadas a esta tarefa (todas existem no NeoPZ):
{classes_reais}
{instrucao_correcao}

INSTRUÇÕES:
- Use apenas classes cujos headers aparecem no contexto
- Use apenas métodos visíveis nas declarações de classe acima
- Prefira SEMPRE a API atual do NeoPZ (ex: TPZMatPoisson, std::function em
  SetForcingFunction) em vez da API antiga (TPZDummyFunction, TPZMatPoisson3d)
- Sempre inclua os #include específicos necessários
- Siga os padrões dos exemplos de uso
- Se não tiver certeza do nome exato, escreva: // TODO: verificar nome
- Se o usuário pedir uma EXPLICAÇÃO (ex: "o que é a classe X"), responda com
  texto didático; código só se for um trecho CURTO usando a própria classe
  explicada. NUNCA cole um programa completo de outro assunto como "exemplo"
- Se o usuário pedir código/programa, gere com explicações do que cada parte faz
- Combine texto explicativo e código quando fizer sentido
- NUNCA afirme que o código que você gerou foi compilado, testado ou executado
  com sucesso — você não compilou nada. Se a documentação do contexto disser
  que um exemplo foi verificado, isso vale para AQUELE exemplo, não para o seu

{contexto}{_formatar_historico(historico)}

Tarefa: {pergunta}

Resposta:"""
