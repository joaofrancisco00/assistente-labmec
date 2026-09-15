import difflib
import re
from pathlib import Path

from .cpp_parser import find_tpz_classes_in_code, find_suspicious_method_calls
from .config import (
    HEADERS_SISTEMA,
)
from .compilation import _neopz_prefix, _include_flags

def _resposta_contem_codigo(resposta: str) -> bool:
    if "```" in resposta:
        return True
    if re.search(r'#include\s*[<"]', resposta):
        return True
    if re.search(r'\bnew\s+TPZ\w+', resposta):
        return True
    if re.search(r'\bTPZ\w+\s*[\*&]?\s*\w+\s*[=;(]', resposta):
        return True
    return False

def _validar_codigo(codigo: str, whitelist: set) -> list:
    if not whitelist:
        return []
    usadas = find_tpz_classes_in_code(codigo)
    return [c for c in usadas if c not in whitelist]

_INCLUDE_RE       = re.compile(r'#include\s*[<"]([^>"]+\.h)[>"]')
_INCLUDE_ASPAS_RE = re.compile(r'#include\s*"([^"]+\.h)"')

def _extrair_includes(codigo: str, apenas_aspas: bool = False) -> list:
    regex = _INCLUDE_ASPAS_RE if apenas_aspas else _INCLUDE_RE
    return [Path(inc).name for inc in regex.findall(codigo)]

def _includes_com_caminho(codigo: str) -> dict:
    return {Path(inc).name: inc for inc in _INCLUDE_RE.findall(codigo)}

def _validar_includes(codigo: str, headers_whitelist: set) -> dict:
    if not headers_whitelist:
        return {}
    usados = _extrair_includes(codigo, apenas_aspas=True)
    problemas = {}
    for inc in usados:
        if inc in HEADERS_SISTEMA:
            continue
        if inc not in headers_whitelist:
            problemas[inc] = difflib.get_close_matches(inc, headers_whitelist, n=3, cutoff=0.5)
    return problemas

def _include_para_header(caminho: str) -> str:
    partes = Path(caminho).parts
    if len(partes) >= 3 and partes[0] == "Material":
        return "/".join(partes[1:])
    return Path(caminho).name

_DIRS_NUNCA_INSTALADOS = ("needrefactor", "PerfTests", "UnitTest_PZ",
                          "Publications", "PerfUtil")

_INDISPONIVEL_CACHE = {}

def _motivo_indisponivel(caminho: str):
    if any(p in _DIRS_NUNCA_INSTALADOS for p in Path(caminho).parts[:-1]):
        return "não faz parte do build do NeoPZ"

    prefix = _neopz_prefix()
    if prefix is None:
        return None

    chave = (str(prefix), caminho)
    if chave not in _INDISPONIVEL_CACHE:
        dirs = [Path(f[2:]) for f in _include_flags(prefix)]
        if not dirs:
            return None
        forma = _include_para_header(caminho)
        _INDISPONIVEL_CACHE[chave] = (None if any((d / forma).is_file() for d in dirs)
                                      else "não está nesta instalação do NeoPZ")
    return _INDISPONIVEL_CACHE[chave]

def _classes_indisponiveis(codigo: str, class_header_index: dict) -> dict:
    if not class_header_index:
        return {}
    indisponiveis = {}
    for classe in find_tpz_classes_in_code(codigo):
        caminho = class_header_index.get(classe)
        if not caminho:
            continue
        motivo = _motivo_indisponivel(caminho)
        if motivo:
            indisponiveis[classe] = motivo
    return indisponiveis

def _validar_includes_por_classe(codigo: str, class_header_index: dict, collisions: dict) -> dict:
    if not class_header_index:
        return {}

    usadas = find_tpz_classes_in_code(codigo)
    includes_atuais = _includes_com_caminho(codigo)

    faltando = {}
    for classe in usadas:
        if classe in collisions:
            continue
        caminho = class_header_index.get(classe)
        if not caminho:
            continue
        if _motivo_indisponivel(caminho):
            continue
        forma_certa = _include_para_header(caminho)
        if includes_atuais.get(Path(caminho).name) != forma_certa:
            faltando[classe] = forma_certa
    return faltando

def _validar_metodos(codigo: str, methods_whitelist: set, whitelist: set) -> list:
    if not methods_whitelist:
        return []
    return find_suspicious_method_calls(codigo, methods_whitelist, whitelist)
