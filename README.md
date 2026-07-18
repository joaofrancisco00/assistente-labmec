# Assistente LabMeC — NeoPZ

Assistente de código para a biblioteca de elementos finitos
[NeoPZ](https://github.com/labmec/neopz), com **validação anti-alucinação**:
toda resposta é conferida contra o código-fonte real do NeoPZ (classes,
headers e métodos), com correção automática determinística e receitas
canônicas **compiladas e executadas** contra a biblioteca de verdade.

Roda 100% local (Ollama + qwen2.5-coder:7b) — nenhum dado sai da máquina.

## Requisitos

- macOS (Apple Silicon) ou Linux (**16 GB de RAM** recomendados)
- Python 3.10+
- [Ollama](https://ollama.com/download) instalado e rodando
- ~6 GB de disco (modelo 4.7 GB + índice vetorial)

## Instalação

### Caminho A — a partir de uma cópia completa (recomendado)

Se você recebeu a pasta do projeto **com** `banco_chroma/` e `base_de_dados/`
(ex: zip/pendrive vindo de uma instalação que já funciona):

```bash
cd assistente-labmec
./setup.sh          # cria o venv, instala dependências, baixa o modelo
```

Pronto — nada precisa ser reindexado.

### Caminho B — a partir do git (reconstrução)

O código-fonte do NeoPZ vem como **git submodule** pinado na revisão validada
(`4c6b6d277`, a ponta do branch `main` do labmec/neopz). O índice vetorial
(`banco_chroma/`) não é versionado — é regenerado pelos indexadores.

```bash
git clone --recursive <repo> && cd assistente-labmec
# (se esqueceu o --recursive: git submodule update --init)
./setup.sh
venv/bin/python indexer.py        # indexa headers/exemplos + whitelists (~min)
venv/bin/python indexer_wiki.py   # indexa a wiki curada (wiki_neopz/)
```

**Importante**: whitelists e receitas foram validadas contra essa revisão.
Para migrar para outra (ex: `develop`), é preciso reindexar tudo E revalidar
as receitas compilando contra o NeoPZ novo (ver "Compilando as receitas").

## Uso

**Interface web** (recomendada — streaming, memória de conversa, validação visível):

```bash
caffeinate -i venv/bin/python app.py     # caffeinate: impede o Mac de dormir
# local:   http://localhost:7860
# na rede: http://<ip-desta-maquina>:7860
```

**Terminal**:

```bash
venv/bin/python pipeline.py
```

O rodapé de cada resposta mostra o resultado da validação:
`✅ Nomes verificados` significa que classes/headers/métodos **existem** no
NeoPZ — semântica e assinaturas **não** são checadas; revise antes de usar.

## Estrutura

| Caminho | O que é |
|---|---|
| `pipeline.py` | Pipeline RAG: recuperação → geração → validação → correção → retry |
| `app.py` | Interface web (Gradio) |
| `cpp_parser.py` | Parser heurístico dos headers C++ (whitelists, chunks) |
| `indexer.py` / `indexer_wiki.py` | Indexação (código NeoPZ / wiki curada) |
| `renames.json` | Mapa curado classe antiga → atual (editável à mão) |
| `wiki_neopz/` | Wiki curada (receitas, catálogo de materiais, conceitos) |
| `reference_solutions/` | Receitas canônicas + `CMakeLists.txt` de verificação |
| `header_index/` | Índice determinístico classe → header |
| `banco_chroma/` | Índice vetorial + whitelists (gerado; fora do git) |
| `base_de_dados/neopz/` | Código do NeoPZ (submodule pinado em `4c6b6d277`) |
| `logs/interacoes.jsonl` | Log de cada interação (dataset de avaliação futuro) |
| `tests/` | Testes de regressão (`python3 -m unittest discover -s tests`) |

## Curadoria

- **Nova receita**: escreva o `.cpp` em `reference_solutions/task_XX/`,
  **compile e execute** (ver abaixo), espelhe como `.md` em
  `wiki_neopz/wiki/flows/` e rode `venv/bin/python indexer_wiki.py`.
- **Renomeação de classe** (API antiga → atual): adicione em `renames.json`
  (só é aplicada se o destino existir na whitelist).
- **Qual receita escrever em seguida**: veja `logs/interacoes.jsonl` e os
  votos 👎 em `logs/feedback.jsonl` — indicam a demanda real.
- **Antes e depois de mudar prompt/receitas/índice**: rode
  `venv/bin/python eval_benchmark.py` (~10 min) — perguntas-benchmark reais
  com verificação automática; acusa regressão silenciosa.

## Compilando as receitas (verificação de verdade)

```bash
cmake -S reference_solutions -B reference_solutions/build \
      -DNeoPZ_DIR=/opt/neopz/lib/cmake/neopz \
      -DCMAKE_CXX_COMPILER=/opt/local/bin/g++
cmake --build reference_solutions/build -j4
```

Ajuste `NeoPZ_DIR` para a instalação local do NeoPZ. **Use o mesmo compilador
que compilou o NeoPZ** (no laboratório: g++ do MacPorts) — misturar g++ e
clang dá erro de link por incompatibilidade de biblioteca padrão.

## Solução de problemas

- **"Connection refused" / resposta não sai** — o Ollama não está rodando:
  abra o app do Ollama ou `ollama serve`.
- **`whitelist.txt não encontrada`** — rode `venv/bin/python indexer.py`.
- **Wiki não usada nas respostas** — rode `venv/bin/python indexer_wiki.py`.
- **Respostas ignorando instruções** — confira o aviso de "Prompt grande"
  no terminal (contexto estourando o `NUM_CTX` em `pipeline.py`).
- **Segundo usuário "travado" na interface web** — é a fila: uma geração por
  vez, por limitação da máquina.
