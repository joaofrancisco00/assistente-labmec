import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .compilation import (
    _LINHA_ERRO_RE,
    _compilador_disponivel,
    _extrair_blocos_codigo,
    _include_flags,
    _montar_tu,
    _neopz_prefix,
    _programa_completo,
)
from .config import MAX_ERROS_RELATADOS, TIMEOUT_BUILD, TIMEOUT_EXECUCAO

_MAX_LINHAS_SAIDA = 20
_MAX_CHARS_SAIDA = 2000
_IMPORTED_LOCATION_RE = re.compile(r'IMPORTED_LOCATION_\w+\s+"([^"]+)"')
_DEFINICOES_RE = re.compile(r'INTERFACE_COMPILE_DEFINITIONS\s+"([^"]+)"')


def _execucao_ligada() -> bool:
    return os.environ.get("EXECUTAR_CODIGO") == "1"


def _dir_cmake(prefix: Path) -> Path:
    return prefix / "lib" / "cmake" / "neopz"


def _biblioteca_pz(prefix: Path):
    for alvo in sorted(_dir_cmake(prefix).glob("NeoPZTargets-*.cmake")):
        casado = _IMPORTED_LOCATION_RE.search(alvo.read_text(encoding="utf-8"))
        if casado:
            return Path(casado.group(1).replace("${_IMPORT_PREFIX}", str(prefix)))
    return None


def _definicoes(prefix: Path) -> list:
    alvos = _dir_cmake(prefix) / "NeoPZTargets.cmake"
    casado = _DEFINICOES_RE.search(alvos.read_text(encoding="utf-8")) if alvos.is_file() else None
    if not casado:
        return []
    return [f"-D{d}" for d in casado.group(1).split(";") if d and "$<" not in d and "\\$" not in d]


def _ultimas_linhas(texto: str) -> str:
    linhas = [l for l in texto.splitlines() if l.strip()]
    return "\n".join(linhas[-_MAX_LINHAS_SAIDA:])[-_MAX_CHARS_SAIDA:]


def _erros_de_build(stderr: str) -> list:
    erros = [m.strip() for m in _LINHA_ERRO_RE.findall(stderr)]
    if not erros:
        erros = [l.strip() for l in stderr.splitlines() if l.strip()][-MAX_ERROS_RELATADOS:]
    return erros[:MAX_ERROS_RELATADOS]


def _executar_codigo(resposta: str, timeout: int = TIMEOUT_EXECUCAO) -> dict:
    if not _programa_completo(resposta):
        return {"status": "nao_aplicavel"}

    prefix = _neopz_prefix()
    compilador = _compilador_disponivel()
    biblioteca = _biblioteca_pz(prefix) if prefix else None
    includes = _include_flags(prefix) if prefix else []
    if not (prefix and compilador and biblioteca and biblioteca.is_file() and includes):
        return {"status": "indisponivel", "motivo": "NeoPZ library or compiler not found"}

    with tempfile.TemporaryDirectory() as tmp:
        fonte, programa = Path(tmp) / "main.cpp", Path(tmp) / "programa"
        fonte.write_text(_montar_tu(_extrair_blocos_codigo(resposta)), encoding="utf-8")
        cmd = [compilador, "-std=gnu++17", "-O0", "-w", *_definicoes(prefix), *includes,
               str(fonte), "-o", str(programa),
               f"-Wl,-rpath,{biblioteca.parent}", str(biblioteca)]
        try:
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_BUILD)
        except subprocess.TimeoutExpired:
            return {"status": "timeout_build"}
        if build.returncode != 0:
            return {"status": "erro_build", "erros": _erros_de_build(build.stderr)}

        inicio = time.monotonic()
        try:
            proc = subprocess.run([str(programa)], cwd=tmp, capture_output=True, text=True,
                                  errors="replace", stdin=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            saida = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return {"status": "timeout", "saida": _ultimas_linhas(saida), "timeout_s": timeout}

        resultado = {
            "saida":        _ultimas_linhas(proc.stdout + "\n" + proc.stderr),
            "arquivos":     sorted(p.name for p in Path(tmp).iterdir()
                                   if p.name not in {"main.cpp", "programa"}),
            "tempo_s":      round(time.monotonic() - inicio, 2),
            "codigo_saida": proc.returncode,
        }
    if proc.returncode == 0:
        resultado["status"] = "ok"
    elif proc.returncode < 0:
        resultado["status"] = "crash"
        resultado["sinal"] = signal.Signals(-proc.returncode).name
    else:
        resultado["status"] = "erro_execucao"
    return resultado


def _gerar_cmakelists(nome: str = "neopz_app") -> str:
    return f"""cmake_minimum_required(VERSION 3.14)
project({nome} CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(NeoPZ REQUIRED)

add_executable({nome} main.cpp)
target_link_libraries({nome} PRIVATE NeoPZ::pz)
target_include_directories({nome} PRIVATE ${{PZ_INCLUDE_DIRS}})
"""


def _instrucoes_cmake(resposta: str, nome: str = "neopz_app") -> str:
    if not _programa_completo(resposta):
        return ""
    prefix = _neopz_prefix()
    neopz_dir = _dir_cmake(prefix) if prefix else "/path/to/neopz/lib/cmake/neopz"
    compilador = _compilador_disponivel()
    cxx = f" \\\n      -DCMAKE_CXX_COMPILER={compilador}" if compilador else ""
    return (
        "**How to build and run** — save the code as `main.cpp` and, next to it, this "
        "`CMakeLists.txt`:\n\n"
        f"```cmake\n{_gerar_cmakelists(nome)}```\n\n"
        "```bash\n"
        f"cmake -S . -B build -DNeoPZ_DIR={neopz_dir}{cxx}\n"
        "cmake --build build\n"
        f"./build/{nome}\n"
        "```\n\n"
        "Use the same compiler that built NeoPZ."
    )
