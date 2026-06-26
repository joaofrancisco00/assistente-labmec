#!/usr/bin/env python3
"""
build_class_header_index.py

Varre o source tree do NeoPZ e constroi um indice deterministico
classe -> header real, para usar como guard-rail contra alucinacao
de #include em assistentes de codigo (RAG, agentes, etc).

Por que isso existe:
    Boa parte dos headers do NeoPZ NAO segue o padrao "NomeDaClasse.h"
    (ex: TPZCompMesh esta em Mesh/pzcmesh.h, nao em TPZCompMesh.h).
    LLMs tendem a "alucinar" o nome do header pelo padrao comum em
    outras libs C++. Este script extrai a localizacao real de cada
    classe/struct direto do codigo-fonte, via regex (nao precisa
    compilar nada).

Uso:
    python3 build_class_header_index.py /caminho/para/neopz [--out DIR]

Saida (em --out, default "./neopz_index"):
    class_header_index.json   -> {"TPZCompMesh": "Mesh/pzcmesh.h", ...}
                                  (apenas classes SEM ambiguidade)
    collisions.json           -> classes definidas em mais de um arquivo
                                  (raras, mas precisam revisao manual)
    forward_only.json         -> classes so vistas como forward-declaration
                                  (".h" onde aparecem so "class X;"), informativo
    report.txt                -> resumo legivel
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

HEADER_EXTS = (".h", ".hpp", ".hh")
EXCLUDE_DIR_NAMES = {"build", ".git", "neopz-build"}

# remove comentarios de bloco /* ... */ e de linha // ...
# (sem se preocupar com strings que contenham essas sequencias --
#  nao ocorre em headers de declaracao de classe nesta base de codigo)
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)

CLASS_KW_RE = re.compile(r"\b(class|struct)\b")
NAME_RE = re.compile(r"\s*([A-Za-z_]\w*)")
TPZ_API_RE = re.compile(r"\s*TPZ_API\b")


def strip_comments(text: str) -> str:
    text = BLOCK_COMMENT_RE.sub(" ", text)
    text = LINE_COMMENT_RE.sub("", text)
    return text


def find_template_spans(text: str):
    """Acha todos os trechos 'template<...>' com contagem de profundidade
    balanceada (lida com qualquer nivel de aninhamento, ex:
    template<class T = std::vector<std::pair<int,int>>>)."""
    spans = []
    for m in re.finditer(r"\btemplate\b\s*", text):
        pos = m.end()
        if pos >= len(text) or text[pos] != "<":
            continue
        depth = 0
        i = pos
        n = len(text)
        while i < n:
            if text[i] == "<":
                depth += 1
            elif text[i] == ">":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        spans.append((m.start(), i))
    return spans


def in_any_span(pos: int, spans) -> bool:
    for s, e in spans:
        if s <= pos < e:
            return True
    return False


def scan_to_terminator(text: str, start: int):
    """A partir de 'start' (logo depois do nome da classe), avanca
    respeitando profundidade de <>, (), [] e retorna ('{' ou ';', pos) do
    primeiro terminador top-level encontrado, ou (None, len(text))."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c in "<([":
            depth += 1
        elif c in ">)]":
            if depth > 0:
                depth -= 1
        elif depth == 0 and c in "{;":
            return c, i
        i += 1
    return None, n


def iter_header_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(HEADER_EXTS):
                yield os.path.join(dirpath, fn)


def preceded_by(text: str, pos: int, word: str) -> bool:
    window = text[max(0, pos - 40):pos]
    return re.search(r"\b" + word + r"\s*$", window) is not None


def extract_declarations(text: str):
    """Retorna lista de (name, kind, is_definition) encontrados no texto.

    Ignora ocorrencias de 'class'/'struct' que estao DENTRO de uma lista de
    parametros de template (ex: o 'T' em template<class T>) -- essas nunca
    sao a classe real sendo declarada, sao parametros de tipo.
    """
    template_spans = find_template_spans(text)
    out = []
    for m in CLASS_KW_RE.finditer(text):
        kw_start = m.start()
        if in_any_span(kw_start, template_spans):
            continue  # e so um parametro de template (class T), nao uma declaracao real
        if preceded_by(text, kw_start, "friend"):
            continue
        if preceded_by(text, kw_start, "enum"):
            continue
        pos = m.end()
        # pula macro de export/dllimport, se houver (ex: class TPZ_API TPZX)
        api_m = TPZ_API_RE.match(text, pos)
        if api_m:
            pos = api_m.end()
        name_m = NAME_RE.match(text, pos)
        if not name_m:
            continue
        name = name_m.group(1)
        term, _ = scan_to_terminator(text, name_m.end())
        if term is None:
            continue
        out.append((name, m.group(1), term == "{"))
    return out


def build_index(root: str):
    root = os.path.abspath(root)
    definitions = defaultdict(set)       # class_name -> set(relpath) onde tem corpo {}
    forward_only = defaultdict(set)      # class_name -> set(relpath) onde só apareceu "class X;"
    files_scanned = 0
    parse_errors = []

    for path in iter_header_files(root):
        files_scanned += 1
        relpath = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError as e:
            parse_errors.append((relpath, str(e)))
            continue

        text = strip_comments(raw)
        for name, kind, is_def in extract_declarations(text):
            if is_def:
                definitions[name].add(relpath)
            else:
                forward_only[name].add(relpath)

    # classes que só existem como forward-decl (nunca vimos o corpo em nenhum header)
    forward_only_clean = {
        name: sorted(paths)
        for name, paths in forward_only.items()
        if name not in definitions
    }

    unambiguous = {}
    collisions = {}
    for name, paths in definitions.items():
        if len(paths) == 1:
            unambiguous[name] = next(iter(paths))
        else:
            collisions[name] = sorted(paths)

    stats = {
        "files_scanned": files_scanned,
        "classes_total_with_definition": len(definitions),
        "classes_unambiguous": len(unambiguous),
        "classes_with_collisions": len(collisions),
        "classes_forward_decl_only": len(forward_only_clean),
        "parse_errors": parse_errors,
    }
    return unambiguous, collisions, forward_only_clean, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_root", help="Caminho para o clone do NeoPZ (raiz do repo)")
    ap.add_argument("--out", default="./neopz_index", help="Pasta de saida (default: ./neopz_index)")
    args = ap.parse_args()

    if not os.path.isdir(args.repo_root):
        print(f"Erro: '{args.repo_root}' nao e um diretorio valido.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)

    unambiguous, collisions, forward_only, stats = build_index(args.repo_root)

    with open(os.path.join(args.out, "class_header_index.json"), "w", encoding="utf-8") as f:
        json.dump(unambiguous, f, indent=2, sort_keys=True, ensure_ascii=False)

    with open(os.path.join(args.out, "collisions.json"), "w", encoding="utf-8") as f:
        json.dump(collisions, f, indent=2, sort_keys=True, ensure_ascii=False)

    with open(os.path.join(args.out, "forward_only.json"), "w", encoding="utf-8") as f:
        json.dump(forward_only, f, indent=2, sort_keys=True, ensure_ascii=False)

    report_lines = [
        "NeoPZ class -> header index",
        "=" * 40,
        f"Repo root: {os.path.abspath(args.repo_root)}",
        f"Headers escaneados: {stats['files_scanned']}",
        f"Classes/structs com definicao encontrada: {stats['classes_total_with_definition']}",
        f"  -> sem ambiguidade (1 unico header): {stats['classes_unambiguous']}",
        f"  -> com colisao (definidas em >1 header, revisar manualmente): {stats['classes_with_collisions']}",
        f"Classes vistas so como forward-declaration (nunca um corpo): {stats['classes_forward_decl_only']}",
    ]
    if stats["parse_errors"]:
        report_lines.append(f"Erros de leitura: {len(stats['parse_errors'])}")
        for relpath, err in stats["parse_errors"]:
            report_lines.append(f"  - {relpath}: {err}")

    report = "\n".join(report_lines)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print(report)
    print(f"\nArquivos gerados em: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
