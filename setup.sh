#!/usr/bin/env bash
# Setup do Assistente LabMeC — cria o venv, instala dependências, baixa o
# modelo do Ollama e confere o que falta. Idempotente: pode rodar de novo.
set -e
cd "$(dirname "$0")"

echo "=============================================="
echo "  Assistente LabMeC — setup"
echo "=============================================="

# ── uv + dependências ──────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "→ Instalando gerenciador de pacotes uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "→ Resolvendo dependências (uv sync)..."
uv sync
echo "✅ Dependências instaladas no .venv"

# ── Ollama + modelo ───────────────────────────────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Ollama não encontrado."
    echo "   Instale em https://ollama.com/download e rode ./setup.sh de novo."
    exit 1
fi

if ! ollama list >/dev/null 2>&1; then
    echo "❌ O servidor do Ollama não está rodando."
    echo "   Abra o aplicativo do Ollama (ou rode 'ollama serve') e tente de novo."
    exit 1
fi

if ! ollama list | grep -q "qwen2.5-coder:7b"; then
    echo "→ Baixando o modelo qwen2.5-coder:7b (~4.7 GB, só na primeira vez)..."
    ollama pull qwen2.5-coder:7b
fi
echo "✅ Ollama OK (qwen2.5-coder:7b disponível)"

# ── Submodule do NeoPZ ────────────────────────────────────────────────────────
if [ -f .gitmodules ] && [ ! -f base_de_dados/neopz/CMakeLists.txt ]; then
    echo "→ Baixando o código do NeoPZ (submodule, ~210 MB, só na primeira vez)..."
    git submodule update --init
fi

# ── Índice vetorial ───────────────────────────────────────────────────────────
if [ -f banco_chroma_develop/whitelist.txt ]; then
    echo "✅ Índice (banco_chroma_develop/) encontrado — nada a reindexar"
else
    echo "⚠️  banco_chroma_develop/ ausente ou incompleto."
    if [ -d base_de_dados/neopz ]; then
        echo "   Snapshot do NeoPZ encontrado. Gere o índice com:"
        echo "     uv run indexer.py"
        echo "     uv run indexer_wiki.py"
    else
        echo "   E base_de_dados/neopz/ também não existe. Ou copie as duas"
        echo "   pastas de uma instalação pronta (Caminho A do README), ou"
        echo "   coloque o snapshot do NeoPZ em base_de_dados/neopz/ e rode"
        echo "   os indexadores (Caminho B do README)."
    fi
fi

echo
echo "=============================================="
echo "  Setup concluído! Para usar:"
echo "    interface web:  caffeinate -i uv run app.py"
echo "                    (http://localhost:7860)"
echo "    terminal:       uv run pipeline.py"
echo "=============================================="
