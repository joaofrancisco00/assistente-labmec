# Assistente LabMeC — NeoPZ

> **Branch `neopz-develop`** — valida contra o NeoPZ do branch `develop`
> (`852a5116c`, 2026-06-19). A branch `main` valida contra `4c6b6d277`
> (2022-03-18). Detalhes e o estado da verificação em
> [Qual NeoPZ esta branch valida](#qual-neopz-esta-branch-valida).

Assistente de código para a biblioteca de elementos finitos
[NeoPZ](https://github.com/labmec/neopz), com **validação anti-alucinação**:
toda resposta é conferida contra o código-fonte real do NeoPZ (classes,
headers e métodos), com correção automática determinística e receitas
canônicas verificadas por compilação contra a biblioteca de verdade
(nesta branch, ver o [estado da verificação](#estado-da-verificação-das-receitas)).

Roda 100% local (Ollama + qwen2.5-coder:7b) — nenhum dado sai da máquina.

## Requisitos

- macOS (Apple Silicon) ou Linux (**16 GB de RAM** recomendados)
- Python 3.10+
- [Ollama](https://ollama.com/download) instalado e rodando
- ~6 GB de disco (modelo 4.7 GB + índice vetorial)

## Instalação

### Caminho A — a partir de uma cópia completa (recomendado)

Se você recebeu a pasta do projeto **com** `banco_chroma_develop/` e `base_de_dados/`
(ex: zip/pendrive vindo de uma instalação que já funciona):

```bash
cd assistente-labmec
./setup.sh          # cria o venv, instala dependências, baixa o modelo
```

Pronto — nada precisa ser reindexado.

### Caminho B — a partir do git (reconstrução)

O código-fonte do NeoPZ vem como **git submodule** pinado na revisão validada
(`852a5116c`, do branch `develop` do labmec/neopz). O índice vetorial
(`banco_chroma_develop/`) não é versionado — é regenerado pelos indexadores.

```bash
git clone --recursive <repo> && cd assistente-labmec
# (se esqueceu o --recursive: git submodule update --init)
./setup.sh
venv/bin/python indexer.py        # indexa headers/exemplos + whitelists (~min)
venv/bin/python indexer_wiki.py   # indexa a wiki curada (wiki_neopz/)
```

**Importante**: ao migrar para outra revisão, é preciso reindexar tudo E
revalidar as receitas compilando contra o NeoPZ novo (ver
"Compilando as receitas"). Sobre o estado atual dessa revalidação nesta
branch, ver [Qual NeoPZ esta branch valida](#qual-neopz-esta-branch-valida).

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

## Qual NeoPZ esta branch valida

O branch `main` do labmec/neopz está **congelado em `4c6b6d277` desde
2022-03-18**; o desenvolvimento real acontece no `develop`. A branch `main`
deste projeto acompanha aquele commit de 2022 — o que fazia o assistente
tratar como alucinação classes que existem de verdade hoje. Esta branch
acompanha o `develop` (`852a5116c`, 2026-06-19, 1273 commits à frente).

**Use uma instalação do NeoPZ compatível com a revisão desta branch.** A
whitelist só diz que um nome existe *naquela* revisão.

### O que a migração mudou

| | main (2022) | develop (2026) |
|---|---|---|
| Classes/namespaces/enums | 596 | 658 |
| Headers `.h` | 638 | 690 |
| Métodos (whitelist global) | 4028 | 4384 |
| Classe→header sem ambiguidade | 770 | 847 |

A API é estável: **99,2%** das classes de 2022 ainda existem. O problema não
era o que envelheceu, e sim o que faltava — 67 classes novas fora da
whitelist. Dessas, 30 eram **silenciosamente reescritas** pela correção
automática (cutoff 0.80) para um nome antigo parecido, com o rodapé dizendo
`✅ Nomes verificados`. Exemplos reais:

```
TPZHybridElasticity2D → TPZElasticity2D    (perde a formulação híbrida)
TPZMixedElasticityND  → TPZElasticity3D    (mista → primal, ND → 3D)
TPZL2ProjectionHDiv   → TPZL2Projection    (perde o espaço HDiv)
```

As outras 37 viravam falso positivo + retries desperdiçados. E 21 delas são
citadas pela própria `wiki_neopz/` (`TPZHDivApproxCreator` em 11 páginas,
`TPZHybridElasticity2D` em 10): a wiki ensinava a classe certa e o validador
a desfazia. Além disso, 4 classes mudaram de header — o `#include` injetado
não compilava (ver `header_index/report.txt`).

### Estado da verificação das receitas

⚠️ As receitas em `reference_solutions/` foram compiladas e executadas contra
o NeoPZ de **2022**. Contra o `develop` elas foram conferidas **por nome e
assinatura, não recompiladas**:

- todas as classes, includes e métodos que elas usam ainda existem no
  `develop` (o único nome que sumiu, `TPZMatLaplacian`, aparece só num
  comentário do `poisson.cpp`);
- `TPZMatPoisson.h` e `TPZMixedDarcyFlow.h` não mudaram uma linha entre as
  duas revisões;
- as assinaturas chamadas continuam compatíveis — `TPZElasticity2D(...)` e
  `SetElasticity(...)` idênticas; `BuildMultiphysicsSpace` ganhou um `const`
  num parâmetro, que é compatível para quem chama.

A evidência é forte, mas **não substitui compilar**. Pendências antes de
considerar esta branch verificada de ponta a ponta:

1. Build e instalação do NeoPZ a partir do `develop`.
2. Recompilar as receitas (ver "Compilando as receitas") — em especial
   conferir `_include_para_header` em `pipeline.py`, que codifica quais
   diretórios a instalação propaga como include path; se o `develop` mudou
   esse layout, os `#include` injetados saem errados.
3. `venv/bin/python eval_benchmark.py`.

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
| `banco_chroma_develop/` | Índice vetorial + whitelists (gerado; fora do git) |
| `base_de_dados/neopz/` | Código do NeoPZ (submodule pinado em `852a5116c`) |
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
