import math
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
_RAIZ_FONTE_NEOPZ = Path(__file__).resolve().parent.parent / "base_de_dados" / "neopz"
_DEBUGSTOP_RE = re.compile(r"breakpoint at (\S+?):(\d+)")
_FALHAS_EXECUCAO = {"crash", "erro_execucao", "timeout", "erro_build", "resultado_inconsistente"}
_MAX_VTKS, _MAX_BYTES_VTK = 5, 50_000_000
_PEDE_VTK_RE = re.compile(r'\bPostProcess\s*\(|\bTPZVTKGenerator\b')
_LINHAS_ANTES, _LINHAS_DEPOIS = 8, 2
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


def _ler_vtk(caminho: Path) -> dict:
    linhas = caminho.read_text(encoding="utf-8", errors="replace").split("\n")
    pontos, campos, i = 0, {}, 0
    while i < len(linhas):
        tokens = linhas[i].split()
        if tokens[:1] == ["POINT_DATA"]:
            pontos = int(tokens[1])
        elif tokens[:1] in (["SCALARS"], ["VECTORS"]) and pontos:
            nome, n = tokens[1], pontos * (1 if tokens[0] == "SCALARS" else 3)
            i += 1
            if i < len(linhas) and linhas[i].startswith("LOOKUP_TABLE"):
                i += 1
            valores = []
            while len(valores) < n and i < len(linhas):
                valores += [float(x) for x in linhas[i].split()]
                i += 1
            finitos = [abs(v) for v in valores if math.isfinite(v)]
            campos[nome] = {"nao_finitos": len(valores) - len(finitos),
                            "max_abs": max(finitos, default=0.0)}
            continue
        i += 1
    return {"pontos": pontos, "campos": campos}


def _analisar_vtks(pasta: Path) -> dict:
    resumo = {}
    for vtk in sorted(pasta.glob("*.vtk"))[:_MAX_VTKS]:
        if vtk.stat().st_size <= _MAX_BYTES_VTK:
            try:
                resumo[vtk.name] = _ler_vtk(vtk)
            except (ValueError, IndexError):
                continue
    return resumo


def _checar_resultado(codigo: str, vtks: dict) -> list:
    if not vtks:
        return (["The code calls PostProcess/TPZVTKGenerator, but no .vtk file was written."]
                if _PEDE_VTK_RE.search(codigo) else [])
    problemas = []
    for arquivo, info in vtks.items():
        if info["pontos"] == 0:
            problemas.append(f"{arquivo} has 0 points: the computational mesh is empty "
                             "(missing AutoBuild()? material ids that do not match the geometric mesh?).")
            continue
        for nome, campo in info["campos"].items():
            if campo["nao_finitos"]:
                problemas.append(f"Field {nome} in {arquivo} has {campo['nao_finitos']} NaN/Inf values: "
                                 "the system is probably singular (missing boundary condition, "
                                 "wrong solver or material parameters).")
        zerados = [n for n, c in info["campos"].items() if c["max_abs"] == 0 and not c["nao_finitos"]]
        nao_zerados = [n for n, c in info["campos"].items() if c["max_abs"] > 0]
        if zerados and nao_zerados:
            problemas.append(f"Field(s) {', '.join(zerados)} in {arquivo} are zero at all "
                             f"{info['pontos']} points, while {', '.join(nao_zerados)} are not. "
                             "Check how the material is constructed (constitutive parameters, "
                             "constructor arguments).")
    return problemas


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

        vtks = _analisar_vtks(Path(tmp)) if proc.returncode == 0 else {}
        resultado = {
            "saida":        _ultimas_linhas(proc.stdout + "\n" + proc.stderr),
            "arquivos":     sorted(p.name for p in Path(tmp).iterdir()
                                   if p.name not in {"main.cpp", "programa"}),
            "tempo_s":      round(time.monotonic() - inicio, 2),
            "codigo_saida": proc.returncode,
        }
    problemas = _checar_resultado(_extrair_blocos_codigo(resposta), vtks) if proc.returncode == 0 else []
    if problemas:
        resultado["status"] = "resultado_inconsistente"
        resultado["problemas_resultado"] = problemas
    elif proc.returncode == 0:
        resultado["status"] = "ok"
    elif proc.returncode < 0:
        resultado["status"] = "crash"
        resultado["sinal"] = signal.Signals(-proc.returncode).name
    else:
        resultado["status"] = "erro_execucao"
    return resultado


def _execucao_falhou(execucao: dict) -> bool:
    return execucao.get("status") in _FALHAS_EXECUCAO


def _trecho_fonte_neopz(caminho: str, linha: int):
    partes = Path(caminho).parts
    for i in range(len(partes)):
        candidato = _RAIZ_FONTE_NEOPZ.joinpath(*partes[i:])
        if candidato.is_file():
            break
    else:
        return None, None
    linhas = candidato.read_text(encoding="utf-8", errors="replace").splitlines()
    inicio, fim = max(0, linha - 1 - _LINHAS_ANTES), min(len(linhas), linha + _LINHAS_DEPOIS)
    trecho = "\n".join(f"{n + 1:5d}  {linhas[n]}" for n in range(inicio, fim))
    return str(candidato.relative_to(_RAIZ_FONTE_NEOPZ)), trecho


def _descrever_falha_execucao(execucao: dict) -> str:
    status = execucao.get("status")
    if status not in _FALHAS_EXECUCAO:
        return ""
    partes = [{
        "crash":         f"The program crashed ({execucao.get('sinal', 'signal')}).",
        "erro_execucao": f"The program exited with exit code {execucao.get('codigo_saida')}.",
        "timeout":       (f"The program did not finish within {execucao.get('timeout_s')}s "
                          "(mesh too large, or a loop that never ends)."),
        "erro_build":    "The program compiled but failed to link against libpz.",
        "resultado_inconsistente": "The program ran and exited with code 0, but its result is "
                                   "inconsistent:",
    }[status]]
    partes.extend(f"  - {p}" for p in execucao.get("problemas_resultado", []))
    saida = execucao.get("saida") or "\n".join(execucao.get("erros", []))
    if saida:
        partes.append("Program output (last lines):\n" + saida)
    paradas = list(_DEBUGSTOP_RE.finditer(saida))
    if paradas:
        caminho, linha = paradas[-1].group(1), int(paradas[-1].group(2))
        relativo, trecho = _trecho_fonte_neopz(caminho, linha)
        if trecho:
            partes.append(f"NeoPZ stopped (DebugStop) at {relativo}:{linha}. The check that "
                          f"failed is in this NeoPZ source excerpt:\n{trecho}")
    return "\n".join(partes)


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
