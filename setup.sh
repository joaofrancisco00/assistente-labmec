#!/usr/bin/env bash
# Setup do Assistente LabMeC — cria o venv, instala dependências, baixa o
# modelo do Ollama e confere o que falta. Idempotente: pode rodar de novo.
set -e
cd "$(dirname "$0")"

echo "=============================================="
echo "  Assistente LabMeC — setup"
echo "=============================================="

# ── Python + venv ─────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 não encontrado. Instale o Python 3.10+ e rode de novo."
    exit 1
fi

if [ ! -d venv ]; then
    echo "→ Criando ambiente virtual (venv/)..."
    python3 -m venv venv
fi

echo "→ Instalando dependências Python (pode demorar na primeira vez)..."
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
echo "✅ Dependências instaladas"

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

# ── Índice vetorial ───────────────────────────────────────────────────────────
if [ -f banco_chroma/whitelist.txt ]; then
    echo "✅ Índice (banco_chroma/) encontrado — nada a reindexar"
else
    echo "⚠️  banco_chroma/ ausente ou incompleto."
    if [ -d base_de_dados/neopz ]; then
        echo "   Snapshot do NeoPZ encontrado. Gere o índice com:"
        echo "     venv/bin/python indexer.py"
        echo "     venv/bin/python indexer_wiki.py"
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
echo "    interface web:  caffeinate -i venv/bin/python app.py"
echo "                    (http://localhost:7860)"
echo "    terminal:       venv/bin/python pipeline.py"
echo "=============================================="
