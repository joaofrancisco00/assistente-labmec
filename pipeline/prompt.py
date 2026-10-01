import difflib
from pathlib import Path

from .correction import _sugerir_correcoes

def _formatar_contexto(h_docs: list, e_docs: list, w_docs: list = None) -> str:
    partes = []

    if h_docs:
        partes.append("=== CLASS DECLARATIONS (real NeoPZ interface) ===")
        for doc in h_docs:
            classe = doc.metadata.get("classe", "")
            label = f"[Class: {classe}]" if classe else "[Header]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== END OF DECLARATIONS ===")

    if e_docs:
        partes.append("\n=== USAGE EXAMPLES ===")
        for doc in e_docs:
            fonte = Path(doc.metadata.get("source", "")).name
            partes.append(f"[File: {fonte}]\n{doc.page_content}")
        partes.append("=== END OF EXAMPLES ===")

    if w_docs:
        partes.append("\n=== VERIFIED DOCUMENTATION (analysis wiki) ===")
        for doc in w_docs:
            titulo = doc.metadata.get("titulo", Path(doc.metadata.get("source", "")).stem)
            tipo   = doc.metadata.get("tipo", "")
            label  = f"[{titulo} | {tipo}]" if tipo else f"[{titulo}]"
            partes.append(f"{label}\n{doc.page_content}")
        partes.append("=== END OF DOCUMENTATION ===")

    return "\n\n---\n\n".join(partes)


def _formatar_historico(historico: list, max_trocas: int = 3, max_chars_resposta: int = 1200) -> str:
    if not historico:
        return ""
    partes = []
    for pergunta_ant, resposta_ant in historico[-max_trocas:]:
        resposta_ant = resposta_ant or ""
        if len(resposta_ant) > max_chars_resposta:
            resposta_ant = resposta_ant[:max_chars_resposta] + "\n[... answer truncated ...]"
        partes.append(f"Student: {pergunta_ant}\nAssistant: {resposta_ant}")
    return (
        "\n\nCONVERSATION HISTORY (context only — the current task is at the end):\n"
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
                    f"  - '{classe}' was RENAMED in the current NeoPZ. Use '{renames[classe]}' instead."
                )
            elif matches:
                linhas.append(f"  - '{classe}' does not exist. Did you mean: {', '.join(matches)}?")
            else:
                linhas.append(f"  - '{classe}' does not exist and there is no similar class.")
        instrucao_correcao += (
            "\n\n⚠️ INVALID CLASSES:\n"
            + "\n".join(linhas)
        )

    if includes_errados:
        linhas_inc = []
        for inc, sugs in includes_errados.items():
            if sugs:
                linhas_inc.append(f"  - '#include \"{inc}\"' does NOT exist. Use instead: {', '.join(sugs)}")
            else:
                linhas_inc.append(
                    f"  - '#include \"{inc}\"' does NOT exist and there is NO similar header. "
                    f"There is NO single header in NeoPZ. Include the specific header "
                    f"of each class used (e.g. \"pzgmesh.h\" for TPZGeoMesh, "
                    f"\"pzcmesh.h\" for TPZCompMesh)."
                )
        instrucao_correcao += (
            "\n\n⚠️ FIX THE HEADERS — MANDATORY:\n"
            + "\n".join(linhas_inc)
            + "\nDO NOT repeat the invalid header in the next answer."
        )

    if includes_por_classe:
        linhas_idx = [
            f"  - You used '{classe}' but did not include \"{header}\". Add: #include \"{header}\""
            for classe, header in includes_por_classe.items()
        ]
        instrucao_correcao += (
            "\n\n⚠️ MISSING HEADERS (according to the class→header index, source of truth):\n"
            + "\n".join(linhas_idx)
        )

    if metodos_suspeitos:
        linhas_met = []
        for classe, metodo in metodos_suspeitos:
            sugestoes = difflib.get_close_matches(metodo, methods_whitelist or set(), n=3, cutoff=0.6)
            if sugestoes:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' does NOT exist in NeoPZ. Did you mean: {', '.join(sugestoes)}?"
                )
            else:
                linhas_met.append(
                    f"  - '{classe}::{metodo}' does NOT exist in NeoPZ and there is no similar method. "
                    f"Use only methods that appear in the class declarations of the context."
                )
        instrucao_correcao += (
            "\n\n⚠️ INVENTED METHODS:\n"
            + "\n".join(linhas_met)
            + "\nDO NOT use a method just because it seems logical — check the class declarations in the context."
        )

    if erros_aridade:
        instrucao_correcao += (
            "\n\n⚠️ ARITY ERROR (WRONG NUMBER OF ARGUMENTS):\n"
            + "\n".join(f"  - {e}" for e in erros_aridade)
            + "\nCheck the correct method signature in the provided class declarations."
        )

    if erros_compilacao:
        instrucao_correcao += (
            "\n\n❌ THE COMPILER (g++) REJECTED THE PREVIOUS CODE:\n"
            + "\n".join(f"  - {e}" for e in erros_compilacao)
            + "\nEach line above is an API that does NOT exist the way you wrote it.\n"
            "Pay attention to 'has no member named X in Y' / 'no member named X': method X\n"
            "does NOT belong to class Y — even if it exists in ANOTHER NeoPZ class.\n"
            "Use only the methods that appear in the declaration of the class itself,\n"
            "in the context above. Do not swap the method for a 'similar' one without checking."
        )

    if erros_semanticos:
        instrucao_correcao += (
            "\n\n⚠️ SEMANTIC ERROR (NEOPZ RULES VIOLATED):\n"
            + "\n".join(f"  - {e}" for e in erros_semanticos)
            + "\nThe previous code has modeling or physics errors that the compiler did not catch.\n"
            "Follow the instructions above strictly in the next answer."
        )

    if instrucao_correcao:
        instrucao_correcao += "\nRewrite the code using the correct names."

    return f"""{system_base}

FUNDAMENTAL RULE: NEVER invent TPZ class names or header names.
Use ONLY classes and headers that appear in the context provided below.

ABSOLUTE RULE ABOUT HEADERS: NEVER write #include "NeoPZ.h" — that file
DOES NOT EXIST and breaks compilation. There is NO single header that includes everything.
For EACH class, include its specific header. Examples:
  TPZGeoMesh        → #include "pzgmesh.h"
  TPZCompMesh       → #include "pzcmesh.h"
  TPZLinearAnalysis → #include "TPZLinearAnalysis.h"

Real TPZ classes related to this task (all of them exist in NeoPZ):
{classes_reais}
{instrucao_correcao}

INSTRUCTIONS:
- Use only classes whose headers appear in the context
- Use only methods visible in the class declarations above
- ALWAYS prefer the current NeoPZ API (e.g. TPZMatPoisson, std::function in
  SetForcingFunction) over the old API (TPZDummyFunction, TPZMatPoisson3d)
- Always include the specific #include lines needed
- Follow the patterns of the usage examples
- If you are not sure about an exact name, write: // TODO: check name
- If the user asks for an EXPLANATION (e.g. "what is class X"), answer with
  didactic text; code only if it is a SHORT excerpt using the explained class
  itself. NEVER paste a complete program about another subject as an "example"
- If the user asks for code/a program, generate it with explanations of what each part does
- Combine explanatory text and code when it makes sense
- NEVER claim that the code you generated was compiled, tested or executed
  successfully — you did not compile anything. If the context documentation says
  that an example was verified, that applies to THAT example, not to yours
- Always answer in English

{contexto}{_formatar_historico(historico)}

Task: {pergunta}

Answer:"""
