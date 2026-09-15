import difflib
import re
from pathlib import Path

from .cpp_parser import find_tpz_classes_in_code
from .config import (
    CUTOFF_CLASSE_AUTOMATICA,
    CUTOFF_METODO_AUTOMATICO,
    INCLUDES_LIXO_CONHECIDOS,
)
from .validation import _motivo_indisponivel, _include_para_header

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
                                      destinos: set = None) -> tuple:
    if not whitelist:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    alucinadas = [c for c in usadas if c not in whitelist]
    if not alucinadas:
        return codigo, []

    destinos = whitelist if destinos is None else destinos
    renames = renames or {}
    correcoes = []
    for errada in alucinadas:
        if errada in renames and renames[errada] in destinos:
            certa = renames[errada]
            sufixo = " [renomeação]"
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
    if not class_header_index:
        return codigo, []

    usadas = find_tpz_classes_in_code(codigo)
    necessarios = {
        classe: class_header_index[classe]
        for classe in usadas
        if classe not in collisions and class_header_index.get(classe)
    }

    linhas = codigo.split("\n")

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
        return "\n".join(linhas), []

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

    correcoes = []
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
