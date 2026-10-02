import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import (
    NEOPZ_PREFIXES,
    NEOPZ_CXX,
    TIMEOUT_COMPILACAO,
    MAX_ERROS_RELATADOS,
)

_BLOCO_CODIGO_RE = re.compile(r"```(?:cpp|c\+\+|cxx|cc|c)?[ \t]*\n(.*?)```",
                              re.DOTALL | re.IGNORECASE)
_INCLUDE_LINHA_RE = re.compile(r'^\s*#\s*include\s*[<"]')
_MAIN_RE          = re.compile(r'\bint\s+main\s*\(')
_DEF_TOPO_RE = re.compile(
    r'^(?:template\s*<|class\s+\w|struct\s+\w|namespace\s+\w'
    r'|[A-Za-z_][\w:<>,\s\*&]*[\s\*&][A-Za-z_]\w*\s*\([^;{}]*\)\s*(?:const\s*)?\{)',
    re.MULTILINE)

def _extrair_blocos_codigo(resposta: str) -> str:
    return "\n".join(b.strip() for b in _BLOCO_CODIGO_RE.findall(resposta) if b.strip())

def _programa_completo(resposta: str) -> bool:
    blocos = [b for b in _BLOCO_CODIGO_RE.findall(resposta) if b.strip()]
    return len(blocos) == 1 and len(_MAIN_RE.findall(blocos[0])) == 1

def _montar_tu(codigo: str) -> str:
    includes, corpo = [], []
    for linha in codigo.splitlines():
        (includes if _INCLUDE_LINHA_RE.match(linha) else corpo).append(linha)

    vistos, incs = set(), []
    for inc in includes:
        chave = inc.strip()
        if chave not in vistos:
            vistos.add(chave)
            incs.append(chave)

    corpo_txt = "\n".join(corpo).strip("\n")
    if _MAIN_RE.search(corpo_txt):
        return "\n".join(incs + ["", corpo_txt, ""])
    if _DEF_TOPO_RE.search(corpo_txt):
        return "\n".join(incs + ["", corpo_txt, "", "int main() { return 0; }", ""])
    return "\n".join(incs + ["", "int main() {", corpo_txt, "    return 0;", "}", ""])


_DIAG_ALUCINACAO = (
    re.compile(r"has no member named"),
    re.compile(r"no member named '[^']+' in"),
    re.compile(r"is not a member of"),
    re.compile(r"no matching function for call to '[^']*TPZ"),
    re.compile(r"no matching constructor for initialization of '[^']*TPZ"),
    re.compile(r"No such file or directory"),
    re.compile(r"file not found"),
    re.compile(r"'TPZ\w+' was not declared in this scope"),
    re.compile(r"'TPZ\w+' does not name a type"),
    re.compile(r"unknown type name 'TPZ\w+'"),
    re.compile(r"use of undeclared identifier 'TPZ\w+'"),
)

_LINHA_ERRO_RE = re.compile(
    r'^[^\n]*?:\d+:(?:\d+:)?\s*(?:fatal\s+)?error:\s*(.+)$', re.MULTILINE)


def _erro_denuncia_alucinacao(mensagem: str) -> bool:
    return any(p.search(mensagem) for p in _DIAG_ALUCINACAO)


def _neopz_prefix():
    env = os.environ.get("NEOPZ_PREFIX")
    candidatas = [Path(env)] if env else list(NEOPZ_PREFIXES)
    for c in candidatas:
        if (c / "lib" / "cmake" / "neopz" / "NeoPZTargets.cmake").is_file():
            return c
    return None


def _compilador_disponivel():
    for cand in (os.environ.get("NEOPZ_CXX"), NEOPZ_CXX, "g++", "c++"):
        if not cand:
            continue
        caminho = shutil.which(cand) if not os.path.isabs(cand) else (
            cand if os.path.exists(cand) else None)
        if caminho:
            return caminho
    return None


_INCLUDE_FLAGS_CACHE = {}
_INTERFACE_INCLUDES_RE = re.compile(
    r'INTERFACE_INCLUDE_DIRECTORIES\s+"([^"]+)"')


def _include_flags(prefix: Path) -> list:
    chave = str(prefix)
    if chave not in _INCLUDE_FLAGS_CACHE:
        alvos = prefix / "lib" / "cmake" / "neopz" / "NeoPZTargets.cmake"
        casado = _INTERFACE_INCLUDES_RE.search(alvos.read_text(encoding="utf-8"))
        if not casado:
            return []
        dirs = [d.replace("${_IMPORT_PREFIX}", str(prefix))
                for d in casado.group(1).split(";") if d.strip()]
        _INCLUDE_FLAGS_CACHE[chave] = [f"-I{d}" for d in dirs if Path(d).is_dir()]
    return _INCLUDE_FLAGS_CACHE[chave]


def _compilar_codigo(resposta: str, timeout: int = TIMEOUT_COMPILACAO) -> dict:
    codigo = _extrair_blocos_codigo(resposta)
    if not codigo.strip():
        return {"status": "sem_codigo", "erros": [], "ignorados": 0}

    prefix = _neopz_prefix()
    compilador = _compilador_disponivel()
    if prefix is None or compilador is None:
        motivo = ("NeoPZ installation not found" if prefix is None
                  else "C++ compiler not found")
        return {"status": "indisponivel", "erros": [], "ignorados": 0, "motivo": motivo}

    flags_include = _include_flags(prefix)
    if not flags_include:
        return {"status": "indisponivel", "erros": [], "ignorados": 0,
                "motivo": "the installation include path could not be read"}

    tu = _montar_tu(codigo)
    with tempfile.TemporaryDirectory() as tmp:
        fonte = Path(tmp) / "gerado.cpp"
        fonte.write_text(tu, encoding="utf-8")
        cmd = [compilador, "-fsyntax-only", "-std=gnu++17", "-w",
               f"-fmax-errors={MAX_ERROS_RELATADOS * 2}",
               *flags_include, str(fonte)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "erros": [], "ignorados": 0}

    if proc.returncode == 0:
        return {"status": "ok", "erros": [], "ignorados": 0}

    mensagens = _LINHA_ERRO_RE.findall(proc.stderr)
    completo = _programa_completo(resposta)
    relevantes, ignorados = [], 0
    for msg in mensagens:
        msg = msg.strip()
        if completo or _erro_denuncia_alucinacao(msg):
            if msg not in relevantes:
                relevantes.append(msg)
        else:
            ignorados += 1

    if not relevantes:
        return {"status": "inconclusivo", "erros": [], "ignorados": ignorados}
    return {"status": "erros", "erros": relevantes[:MAX_ERROS_RELATADOS],
            "ignorados": ignorados}


_CLASSE_EM_DIAGNOSTICO_RE = re.compile(r"\bTPZ\w+")


def _classes_citadas_em_erros(erros: list, whitelist: set) -> set:
    citadas = set()
    for msg in erros:
        citadas.update(_CLASSE_EM_DIAGNOSTICO_RE.findall(msg))
    return {c for c in citadas if c in whitelist} if whitelist else citadas
