"""
gerar_heranca.py — gera o índice de herança de classes do NeoPZ.

Varre os headers .h em base_de_dados/neopz/ e grava
banco_chroma_develop/inheritance_index.json no formato
{classe: [bases diretas]}.

Por que isso existe: a whitelist global de métodos só checa se o método
existe EM ALGUM lugar do NeoPZ — `an.SetForcingFunction(...)` num
TPZLinearAnalysis passava porque o método existe... em OUTRA classe.
Com este índice, o pipeline pode conferir o método contra a classe E
seus ancestrais (a resolução transitiva é feita por BFS na consulta,
em pipeline/cpp_parser.py::_metodo_na_hierarquia — o índice guarda só
as arestas diretas, fiel ao que está declarado nos headers).

Execute UMA VEZ (ou sempre que o snapshot do NeoPZ mudar):

    cd ~/Documents/assistente-labmec
    uv run gerar_heranca.py
"""
import json
from pathlib import Path

from pipeline.cpp_parser import build_inheritance_index

NEOPZ_DIR = Path("./base_de_dados/neopz")
INDEX_DIR = Path("./banco_chroma_develop")
OUT_FILE = INDEX_DIR / "inheritance_index.json"


def main():
    print("=" * 58)
    print("  GERADOR DO ÍNDICE DE HERANÇA NEOPZ")
    print("=" * 58)

    if not NEOPZ_DIR.exists():
        print(f"\n❌ {NEOPZ_DIR} não encontrado — verifique o snapshot do NeoPZ.")
        return

    indice = build_inheritance_index(NEOPZ_DIR)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(indice, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    total_arestas = sum(len(v) for v in indice.values())
    print(f"\n✅ {len(indice)} classes com bases diretas ({total_arestas} arestas)")
    print(f"   Índice salvo em: {OUT_FILE}")
    print("=" * 58)


if __name__ == "__main__":
    main()
