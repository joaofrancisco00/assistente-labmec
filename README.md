# Assistente LabMeC — NeoPZ

> **Branch `neopz-develop`** — valida contra o NeoPZ do branch `develop`
> (`852a5116c`, 2026-06-19). A branch `main` valida contra `4c6b6d277`
> (2022-03-18). Detalhes e o estado da verificação em
> [Qual NeoPZ esta branch valida](#qual-neopz-esta-branch-valida).

Assistente de código para a biblioteca de elementos finitos
[NeoPZ](https://github.com/labmec/neopz), com **validação anti-alucinação**:
toda resposta é conferida contra o código-fonte real do NeoPZ (classes,
headers e métodos), com correção automática e receitas verificadas por
compilação.

Roda 100% local (Ollama + qwen2.5-coder:7b) — nenhum dado sai da máquina.

---

## Como baixar e fazer funcionar

### 1. Pré-requisitos

Antes de tudo, instale na sua máquina:

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **Ollama** — [ollama.com/download](https://ollama.com/download) (abra o app após instalar)
- **Git** — já vem no macOS; no Linux: `sudo apt install git`
- **16 GB de RAM** recomendados (o modelo consome ~5 GB)

### 2. Clonar o repositório

```bash
git clone --recursive https://github.com/joaofrancisco00/assistente-labmec.git
cd assistente-labmec
git checkout neopz-develop
```

> O `--recursive` é essencial: ele baixa o código-fonte do NeoPZ como
> submodule na pasta `base_de_dados/neopz/`.

### 3. Instalar dependências e baixar o modelo

```bash
./setup.sh
```

Esse script cria o ambiente virtual Python (`venv/`), instala as bibliotecas
necessárias e baixa o modelo `qwen2.5-coder:7b` no Ollama.

### 4. Indexar o banco de dados

```bash
venv/bin/python indexer.py        # indexa headers e exemplos do NeoPZ (~1 min)
venv/bin/python indexer_wiki.py   # indexa a wiki curada (receitas e conceitos)
```

> Se você recebeu a pasta do projeto **com** `banco_chroma_develop/` já
> pronto (ex: zip/pendrive), pode pular este passo.

### 5. Rodar o assistente

**Terminal** (modo direto):

```bash
venv/bin/python pipeline.py
```

**Interface web**:

```bash
caffeinate -i venv/bin/python app.py
```

Acesse no navegador: `http://localhost:7860`

### Entendendo os selos de validação

Toda resposta vem com um selo no rodapé:

| Selo | Significado |
|---|---|
| ✅ Compilado | O g++ aceitou o código — classes, métodos e assinaturas existem de verdade |
| ✅ Nomes verificados | Classes/headers/métodos existem no NeoPZ, mas assinaturas não foram checadas |
| ❌ O compilador recusou | Vem com a mensagem do g++ — o modelo errou algo |

> Nenhum selo verifica o **resultado físico** da simulação; revise antes de usar.

---

## Estrutura do projeto

| Caminho | O que é |
|---|---|
| `pipeline.py` | Pipeline RAG: recuperação → geração → validação → correção → retry |
| `app.py` | Interface web (Gradio) |
| `cpp_parser.py` | Parser heurístico dos headers C++ (whitelists, chunks) |
| `indexer.py` / `indexer_wiki.py` | Indexação (código NeoPZ / wiki curada) |
| `renames.json` | Mapa curado classe antiga → atual (editável à mão) |
| `wiki_neopz/` | Wiki curada (receitas, catálogo de materiais, conceitos) |
| `reference_solutions/` | Receitas canônicas + `CMakeLists.txt` de verificação |
| `banco_chroma_develop/` | Índice vetorial + whitelists (gerado; fora do git) |
| `base_de_dados/neopz/` | Código do NeoPZ (submodule pinado em `852a5116c`) |
| `eval_benchmark.py` | Benchmark automático de qualidade (6 perguntas, 35 checks) |
| `logs/` | Logs de interações e resultados de benchmark |
| `tests/` | Testes de regressão (`python3 -m unittest discover -s tests`) |

## Curadoria

A qualidade do assistente depende da wiki curada em `wiki_neopz/wiki/`. Ela
está organizada em 3 categorias:

| Pasta | Conteúdo | Prioridade |
|---|---|---|
| `flows/` | Receitas completas com código compilável | ⭐ Alta |
| `concepts/` | Conceitos teóricos e catálogo de materiais | Média |
| `code/` | Descrições de classes e módulos | Média |

### Como adicionar uma receita nova

1. Escreva o `.cpp` em `reference_solutions/task_XX/`
2. **Compile e execute** contra o NeoPZ (ver seção abaixo)
3. Espelhe como `.md` em `wiki_neopz/wiki/flows/`
4. Rode `venv/bin/python indexer_wiki.py`

### Como adicionar uma renomeação de classe

Edite `renames.json` (API antiga → atual). Só é aplicada se o destino existir
na whitelist.

### Como rodar o benchmark

Antes e depois de mudar prompt, receitas ou índice, rode:

```bash
venv/bin/python eval_benchmark.py    # benchmark de código (~10 min)
```

Acusa regressão silenciosa se a nota cair.

## Compilando as receitas (verificação)

```bash
cmake -S reference_solutions -B reference_solutions/build \
      -DNeoPZ_DIR=/opt/neopz/lib/cmake/neopz \
      -DCMAKE_CXX_COMPILER=/opt/local/bin/g++
cmake --build reference_solutions/build -j4
```

Ajuste `NeoPZ_DIR` para a instalação local do NeoPZ. **Use o mesmo compilador
que compilou o NeoPZ.**

## Checagem de compilação no pipeline

Se houver uma instalação do NeoPZ na máquina, o pipeline **compila**
(só sintaxe, sem gerar binário) o código C++ que o modelo produz.

Por padrão, procura a instalação em `~/opt/neopz-develop` ou `/opt/neopz`
e o compilador em `/opt/local/bin/g++`. Para apontar outro local:

```bash
export NEOPZ_PREFIX=/caminho/onde/instalou/neopz
export NEOPZ_CXX=/caminho/do/compilador
```

Sem NeoPZ instalado, a checagem fica desligada em silêncio: o selo volta a
ser `✅ Nomes verificados`. **Falta de compilador nunca reprova uma resposta.**

## Solução de problemas

| Problema | Solução |
|---|---|
| "Connection refused" / resposta não sai | O Ollama não está rodando: abra o app ou `ollama serve` |
| `whitelist.txt não encontrada` | Rode `venv/bin/python indexer.py` |
| Wiki não usada nas respostas | Rode `venv/bin/python indexer_wiki.py` |
| Respostas ignorando instruções | Confira o aviso de "Prompt grande" no terminal |
| Respostas muito lentas | Feche aplicativos pesados para liberar RAM (ver Monitor de Atividade) |
| Segundo usuário "travado" na web | É a fila: uma geração por vez |
