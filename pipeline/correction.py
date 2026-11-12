import difflib
import json
import re
from pathlib import Path

from .cpp_parser import (
    find_enum_value_uses,
    find_tpz_classes_in_code,
)
from .config import (
    CUTOFF_CLASSE_AUTOMATICA,
    CUTOFF_METODO_AUTOMATICO,
    CUTOFF_ENUM_AUTOMATICO,
    INCLUDES_LIXO_CONHECIDOS,
)
from .compilation import _BLOCO_CODIGO_RE
from .validation import (
    _motivo_indisponivel,
    _include_para_header,
    _validar_namespaces,
)

def _sugerir_correcoes(alucinadas: list, whitelist: set, cutoff: float = 0.6) -> dict:
    sugestoes = {}
    for item in alucinadas:
        sugestoes[item] = difflib.get_close_matches(item, whitelist, n=3, cutoff=cutoff)
    return sugestoes

def _whitelist_utilizavel(whitelist: set, class_header_index: dict) -> set:
    if not class_header_index:
        return whitelist
    utilizavel = set()
    for classe in whitelist:
        caminho = class_header_index.get(classe)
        if caminho is None or not _motivo_indisponivel(caminho):
            utilizavel.add(classe)
    return utilizavel

def _corrigir_classes_automaticamente(codigo: str, whitelist: set, renames: dict = None,
                                      destinos: set = None, ignorar: set = None) -> tuple:
    if not whitelist:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    alucinadas = [c for c in usadas
                  if c not in whitelist and c not in (ignorar or ())]
    if not alucinadas:
        return codigo, []

    destinos = whitelist if destinos is None else destinos
    renames = renames or {}
    correcoes = []
    for errada in alucinadas:
        if errada in renames and renames[errada] in destinos:
            certa = renames[errada]
            sufixo = " [rename]"
        else:
            candidatos = difflib.get_close_matches(errada, destinos, n=1, cutoff=CUTOFF_CLASSE_AUTOMATICA)
            if not candidatos:
                continue
            certa = candidatos[0]
            sufixo = ""
        codigo, n = re.subn(r'\b' + re.escape(errada) + r'\b', certa, codigo)
        if n:
            correcoes.append(f"{errada} → {certa}{sufixo}")
    return codigo, correcoes

def _corrigir_namespaces_automaticamente(codigo: str, namespace_index: dict) -> tuple:
    """Qualifica as classes que _validar_namespaces flagou (`TPZGeoQuad` →
    `pzgeom::TPZGeoQuad`) — só dentro dos blocos de código fenced: a prosa
    pode citar o nome da classe à vontade. A correção é determinística (o
    índice garante namespace único), então não há candidato ambíguo."""
    faltando = _validar_namespaces(codigo, namespace_index)
    if not faltando:
        return codigo, []

    def _corrigir_bloco(m):
        bloco = m.group(0)
        for classe, ns in faltando.items():
            bloco = re.sub(r'(?<![\w:])' + re.escape(classe) + r'\b',
                           f'{ns}::{classe}', bloco)
        return bloco

    corrigido = _BLOCO_CODIGO_RE.sub(_corrigir_bloco, codigo)
    correcoes = [f"{c} → {ns}::{c}" for c, ns in faltando.items()]
    return corrigido, correcoes


def _corrigir_metodos_automaticamente(codigo: str, metodos_suspeitos: list, class_methods_index: dict) -> tuple:
    if not class_methods_index or not metodos_suspeitos:
        return codigo, []

    method_aliases = {
        "GetId": "Id",
        "GetID": "Id",
        "NumID": "Id",
        "GetMatId": "Id",
        "GetIndex": "Index",
    }

    correcoes = []
    for classe, errado in metodos_suspeitos:
        candidatos_da_classe = class_methods_index.get(classe)
        if not candidatos_da_classe:
            continue
            
        certo = None
        if errado in method_aliases and method_aliases[errado] in candidatos_da_classe:
            certo = method_aliases[errado]
        else:
            candidatos = difflib.get_close_matches(errado, candidatos_da_classe, n=1, cutoff=CUTOFF_METODO_AUTOMATICO)
            if candidatos:
                certo = candidatos[0]

        if certo:
            padrao = re.compile(r'(->|\.|::)\s*' + re.escape(errado) + r'\s*\(')
            codigo, n = padrao.subn(r'\1' + certo + '(', codigo)
            if n:
                correcoes.append(f"{classe}::{errado} → {classe}::{certo}")
    return codigo, correcoes

def _corrigir_includes_automaticamente(
    codigo: str,
    class_header_index: dict,
    collisions: dict,
    headers_whitelist: set,
) -> tuple:
    if not class_header_index and not headers_whitelist:
        return codigo, []

    linhas = codigo.split("\n")
    correcoes = []

    if headers_whitelist:
        por_lower = {h.lower(): h for h in headers_whitelist}
        for i, linha in enumerate(linhas):
            m = re.search(r'(#include\s*[<"])([^>"]+\.h)([>"])', linha)
            if not m:
                continue
            caminho_inc = m.group(2)
            nome = Path(caminho_inc).name
            if nome in headers_whitelist or nome.lower() not in por_lower:
                continue
            if nome.lower() in INCLUDES_LIXO_CONHECIDOS:
                continue
            nome_real = por_lower[nome.lower()]
            novo_caminho = (
                str(Path(caminho_inc).with_name(nome_real))
                if "/" in caminho_inc
                else nome_real
            )
            linhas[i] = linha[:m.start(2)] + novo_caminho + linha[m.end(2):]
            correcoes.append(f'#include "{caminho_inc}" → "{novo_caminho}"')

    if not class_header_index:
        return "\n".join(linhas), correcoes

    usadas = find_tpz_classes_in_code(codigo)
    necessarios = {
        classe: class_header_index[classe]
        for classe in usadas
        if classe not in collisions and class_header_index.get(classe)
    }

    def _includes_atuais(linhas: list) -> dict:
        atuais = {}
        for i, linha in enumerate(linhas):
            m = re.search(r'#include\s*[<"]([^>"]+\.h)[>"]', linha)
            if m:
                atuais.setdefault(Path(m.group(1)).name, (i, m.group(1)))
        return atuais

    atuais = _includes_atuais(linhas)
    candidatos_chute = set()
    for c in necessarios:
        base = c.lower()
        candidatos_chute.add(f"{base}.h")
        if base.startswith("tpz"):
            candidatos_chute.add(f"pz{base[3:]}.h")
    linhas_remover = {
        idx for nome, (idx, _caminho) in atuais.items()
        if nome.lower() in INCLUDES_LIXO_CONHECIDOS
        or (nome.lower() in candidatos_chute and nome not in headers_whitelist)
    }
    if linhas_remover:
        linhas = [l for i, l in enumerate(linhas) if i not in linhas_remover]

    if not necessarios:
        return "\n".join(linhas), correcoes

    atuais = _includes_atuais(linhas)
    faltando   = {}
    a_corrigir = {}
    obtenivel = {c: cam for c, cam in necessarios.items()
                 if not _motivo_indisponivel(cam)}
    for c, caminho in obtenivel.items():
        forma_certa = _include_para_header(caminho)
        presente = atuais.get(Path(caminho).name)
        if presente is None:
            faltando[c] = forma_certa
        elif presente[1] != forma_certa:
            a_corrigir[c] = (presente[0], presente[1], forma_certa)

    for c, (idx, caminho_errado, forma_certa) in a_corrigir.items():
        padrao_linha = re.compile(r'(#include\s*[<"])' + re.escape(caminho_errado) + r'([>"])')
        nova_linha, n = padrao_linha.subn(r'\g<1>' + forma_certa + r'\g<2>', linhas[idx], count=1)
        if n:
            linhas[idx] = nova_linha
            correcoes.append(f'{c}: #include "{caminho_errado}" → "{forma_certa}"')

    if faltando:
        posicoes_include = [i for i, l in enumerate(linhas) if re.match(r'\s*#include\b', l)]
        ultimo_include_idx = max(posicoes_include, default=-1)

        novas = [f'#include "{forma_certa}"'
                 for forma_certa in sorted(set(faltando.values()))]
        if ultimo_include_idx >= 0:
            linhas = linhas[:ultimo_include_idx + 1] + novas + linhas[ultimo_include_idx + 1:]
            correcoes += [f'{c}: + #include "{forma_certa}"' for c, forma_certa in faltando.items()]
        else:
            abre_bloco = next((i for i, l in enumerate(linhas)
                               if re.match(r'\s*```(?:cpp|c\+\+|cxx|cc|c)?[ \t]*$', l,
                                           re.IGNORECASE)), None)
            
            if abre_bloco is not None:
                corte = abre_bloco + 1
                linhas = linhas[:corte] + novas + linhas[corte:]
                correcoes += [f'{c}: + #include "{forma_certa}"' for c, forma_certa in faltando.items()]

    return "\n".join(linhas), correcoes


def _valor_enum_provavel(errado: str, validos: list):
    por_prefixo = [v for v in validos if v.startswith(errado)]
    if len(por_prefixo) == 1:
        return por_prefixo[0]
    if por_prefixo:
        return None
    parecidos = difflib.get_close_matches(errado, validos, n=2, cutoff=CUTOFF_ENUM_AUTOMATICO)
    if len(parecidos) == 1 or (len(parecidos) == 2 and
            difflib.SequenceMatcher(None, errado, parecidos[0]).ratio()
            > difflib.SequenceMatcher(None, errado, parecidos[1]).ratio()):
        return parecidos[0]
    return None


def _corrigir_enums_automaticamente(codigo: str, enum_index: dict) -> tuple:
    if not enum_index:
        return codigo, []
    correcoes = []
    for enum, errado in dict.fromkeys(find_enum_value_uses(codigo, enum_index)):
        validos = [v for v, _ in enum_index[enum]]
        if errado in validos:
            continue
        certo = _valor_enum_provavel(errado, validos)
        if certo:
            padrao = re.compile(r'(?<![\w:])(' + re.escape(enum) + r'\s*::\s*)' + re.escape(errado) + r'\b')
            codigo, n = padrao.subn(r'\g<1>' + certo, codigo)
            if n:
                correcoes.append(f"{enum}::{errado} → {enum}::{certo}")
    return codigo, correcoes


_PADROES_API_FILE = Path(__file__).resolve().parent.parent / "patches" / "padroes_api.json"
_padroes_api_cache = None

_TOPO_CLASSID_RE = re.compile(
    r'(?:[A-Za-z_]\w*\s*::\s*)*\b(TPZ\w+)\s*::\s*(?:ClassId|Type)\s*\(\s*\)')
_AUTOPTR_VAL_RE = re.compile(
    r'\b(TPZAutoPointer\s*<\s*(TPZ\w+)\s*>\s+\w+\s*=\s*)\2\s*\(')
_CREATE_EL_ASSIGN_LIT_RE = re.compile(
    r'^([ \t]*)(?:int64_t|int|auto)\s+(\w+)\s*=\s*'
    r'(\w+\s*(?:->|\.)\s*CreateGeoElement\s*\([^,;\n]+,[^,;\n]+,[^,;\n]+),\s*-?\d+\s*\)\s*;',
    re.MULTILINE)
_CREATE_EL_ASSIGN_3ARGS_RE = re.compile(
    r'^([ \t]*)(?:int64_t|int|auto)\s+(\w+)\s*=\s*'
    r'(\w+\s*(?:->|\.)\s*CreateGeoElement\s*\([^,;\n()]+,[^,;\n()]+,[^,;\n()]+)\)\s*;',
    re.MULTILINE)
_CREATE_EL_BARE_LIT_RE = re.compile(
    r'^([ \t]*)(\w+\s*(?:->|\.)\s*CreateGeoElement\s*\([^,;\n]+,[^,;\n]+,[^,;\n]+),\s*-?\d+\s*\)\s*;',
    re.MULTILINE)
_CREATE_EL_BARE_3ARGS_RE = re.compile(
    r'^([ \t]*)(\w+\s*(?:->|\.)\s*CreateGeoElement\s*\([^,;\n()]+,[^,;\n()]+,[^,;\n()]+)\)\s*;',
    re.MULTILINE)


def _carregar_padroes_api() -> dict:
    global _padroes_api_cache
    if _padroes_api_cache is None:
        try:
            _padroes_api_cache = json.loads(_PADROES_API_FILE.read_text(encoding="utf-8"))
        except Exception:
            _padroes_api_cache = {}
    return _padroes_api_cache


def _corrigir_padroes_conhecidos(codigo: str) -> tuple:
    """Reescreve anti-padrões recorrentes de API sem chamar o LLM (0 ms):
    - chamadas no-op inventadas (ex: TPZVTKGenerator::SetSolution)
    - TPZTriangle::ClassId() em CreateGeoElement → ETriangle
    - CreateGeoElement com literal no 4º arg ou com 3 args → int64_t &index
    - TPZAutoPointer<T> x = T() → new T()
    """
    regras = _carregar_padroes_api()
    mapa_topo = regras.get("topology_class_to_element_type", {})
    noops = regras.get("removed_noop_calls", [])
    correcoes = []

    def _corrigir_trecho(bloco: str) -> str:
        # 1. Chamadas no-op inventadas (ex: vtk.SetSolution(...);)
        for item in noops:
            cls = item.get("class", "")
            metodo = item.get("method", "")
            if cls and metodo and cls in bloco:
                padrao = re.compile(
                    r'^[ \t]*\w+\s*(?:\.|->)\s*' + re.escape(metodo)
                    + r'\s*\([^;\n]*\)\s*;[ \t]*\n?', re.MULTILINE)
                bloco, n = padrao.subn("", bloco)
                if n:
                    msg = item.get("reason") or f"{cls}::{metodo} removed"
                    if msg not in correcoes:
                        correcoes.append(msg)

        # 3. TPZTriangle::ClassId() → ETriangle
        def _sub_topo(m):
            cls = m.group(1)
            if cls in mapa_topo:
                 enum_val = mapa_topo[cls]
                 msg = f"{m.group(0)} → {enum_val}"
                 if msg not in correcoes:
                     correcoes.append(msg)
                 return enum_val
            return m.group(0)

        if mapa_topo:
            bloco = _TOPO_CLASSID_RE.sub(_sub_topo, bloco)

        # 4. CreateGeoElement: 4º arg literal ou 3 args → int64_t &index
        bloco, n1 = _CREATE_EL_ASSIGN_LIT_RE.subn(
            r'\1int64_t \2 = -1;\n\1\3, \2);', bloco)
        bloco, n2 = _CREATE_EL_ASSIGN_3ARGS_RE.subn(
            r'\1int64_t \2 = -1;\n\1\3, \2);', bloco)
        if n1 or n2:
            msg = "CreateGeoElement → 4 args with int64_t &index"
            if msg not in correcoes:
                correcoes.append(msg)

        for regex_bare in (_CREATE_EL_BARE_LIT_RE, _CREATE_EL_BARE_3ARGS_RE):
            if regex_bare.search(bloco):
                ja_tem_elidx = bool(re.search(r'\bint64_t\s+elIndex\b', bloco))
                def _sub_bare(m):
                    nonlocal ja_tem_elidx
                    indent, prefixo = m.group(1), m.group(2)
                    if not ja_tem_elidx:
                        ja_tem_elidx = True
                        return f"{indent}int64_t elIndex = -1;\n{indent}{prefixo}, elIndex);"
                    return f"{indent}{prefixo}, elIndex);"
                bloco, n_b = regex_bare.subn(_sub_bare, bloco)
                if n_b:
                    msg = "CreateGeoElement → 4 args with int64_t &index"
                    if msg not in correcoes:
                        correcoes.append(msg)

        # 5. TPZAutoPointer<TPZFoo> x = TPZFoo( → new TPZFoo(
        def _sub_autoptr(m):
            cls = m.group(2)
            msg = f"TPZAutoPointer<{cls}> = {cls}() → new {cls}()"
            if msg not in correcoes:
                correcoes.append(msg)
            return f"{m.group(1)}new {cls}("

        bloco = _AUTOPTR_VAL_RE.sub(_sub_autoptr, bloco)

        # 6. gmesh.CreateUniqueNodeId() → gmesh.NodeVec().AllocateNewElement()
        bloco, n_node = re.subn(
            r'\b(\w+)\s*(->|\.)\s*CreateUniqueNodeId\s*\(\s*\)',
            r'\1\2NodeVec().AllocateNewElement()',
            bloco,
        )
        if n_node:
            msg = "CreateUniqueNodeId() → NodeVec().AllocateNewElement()"
            if msg not in correcoes:
                correcoes.append(msg)
        return bloco

    if _BLOCO_CODIGO_RE.search(codigo):
        corrigido = _BLOCO_CODIGO_RE.sub(lambda m: _corrigir_trecho(m.group(0)), codigo)
    else:
        corrigido = _corrigir_trecho(codigo)
    return corrigido, correcoes
