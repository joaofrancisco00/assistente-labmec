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

- `✅ Compilado` — o g++ aceitou o código: classes, métodos e **assinaturas**
  existem de verdade. Exige NeoPZ instalado (ver
  [Checagem de compilação no pipeline](#checagem-de-compilação-no-pipeline));
- `✅ Nomes verificados` — classes/headers/métodos **existem** no NeoPZ, mas
  semântica e assinaturas **não** foram checadas;
- `❌ O compilador recusou o código` — vem com a mensagem crua do g++.

Nenhum dos selos verifica o **resultado físico**; revise antes de usar.

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

✅ As quatro receitas em `reference_solutions/` foram recompiladas e
**executadas** contra o NeoPZ do `develop` (`~/opt/neopz-develop`,
`852a5116c`) — deixou de ser verificação por nome/assinatura e passou a ser
o binário rodando de verdade (commit `d83f80d`):

- as 4 compilam sem um único aviso e rodam com `exit 0`, gerando VTK;
- a receita de elasticidade (`task_04_elasticidade2d`) tinha um bug real que
  só **execução** pega — não compilação, não validação de nomes: em 2022 o
  construtor completo `TPZElasticity2D(id, E, nu, fx, fy, planestress)` tinha
  corpo vazio, e a receita orientava usar `(id)` + `SetElasticity(...)`. No
  `develop` esse construtor foi consertado e passou a ser o ÚNICO que
  inicializa a lei constitutiva — a recomendação antiga virou o erro. Falha
  silenciosa: compila limpo, roda com `exit 0`, grava VTK, e `SigmaX`/`SigmaY`
  saem **identicamente zero** nos 1152 pontos verificados (contra ±0,1477 e
  ±0,4434 com o construtor completo). Nem `TPZElasticity2D` nem
  `SetElasticity` são alucinação — nenhuma checagem de nome pegaria isso. A
  receita, o espelho em `wiki_neopz/`, o catálogo de materiais e o check
  `construtor_completo` do `eval_benchmark.py` foram invertidos para o padrão
  certo;
- `venv/bin/python eval_benchmark.py` roda **35/35** contra o `develop`
  (`logs/eval_20260805_203353.json`).

O que fica de fato em aberto não é desta migração — é estrutural: "compilou e
rodou" garante que o C++ é válido, não que o resultado físico está certo. A
elasticidade só foi pega porque alguém comparou `SigmaX`/`SigmaY` com o valor
esperado à mão; não existe hoje checagem automática de plausibilidade física
por família de problema.

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

## Checagem de compilação no pipeline

Se houver uma instalação do NeoPZ compilada na máquina, o pipeline **compila**
(só sintaxe/semântica, sem gerar binário) o código C++ que o modelo produz,
dentro do loop de validação. É o que fecha o buraco da whitelist de métodos,
que é **global** de propósito (não sabe a qual classe cada método pertence):

```
mat->SetElasticity(2.e3, 0.3);   // num TPZDarcyFlow
```

`SetElasticity` existe — em `TPZElasticity2D`. A validação de nomes aprovava e
carimbava `✅ Nomes verificados`. O g++ recusa em ~0,5 s, e o erro volta no
prompt da tentativa seguinte junto com a declaração da classe acusada.

Como entra no loop:

- só roda quando a validação de nomes já passou (é onde o selo seria dado) e a
  resposta tem código de fato;
- **só erro que denuncia API inexistente reprova** (método fora da classe,
  assinatura errada, header que não resolve, tipo não declarado). Erro que é
  artefato do recorte — variável definida "acima", trecho sem `main` — sai como
  `inconclusivo` e não gasta retry;
- reprovou, o retry recebe as mensagens do compilador e as declarações das
  classes citadas nelas; se as tentativas acabarem, volta a melhor delas com o
  erro do compilador no rodapé, sem selo;
- passou, o selo sobe para `✅ Compilado` — classes, métodos e assinaturas
  existem de verdade. **Compilar não verifica o resultado físico** (ver o bug
  de elasticidade em [Estado da verificação](#estado-da-verificação-das-receitas)).

Medida nas 8 respostas já registradas em `logs/interacoes.jsonl`, todas
carimbadas `✅ Nomes verificados` na época: 4 são reprovadas pelo compilador —
construtor `TPZElasticity3D(id, dim)` inexistente, `PushBack` num
`TPZAdmChunkVector` (existe em outra classe), e dois includes que não resolvem.

Por padrão procura a instalação em `~/opt/neopz-develop` ou `/opt/neopz`
(nessa ordem) e o compilador em `/opt/local/bin/g++`. Se a sua instalação
está em outro lugar, aponte com variáveis de ambiente:

```bash
export NEOPZ_PREFIX=/caminho/onde/instalou/neopz   # a raiz com lib/cmake/neopz/
export NEOPZ_CXX=/caminho/do/compilador             # o MESMO que compilou o NeoPZ
```

Sem NeoPZ instalado (Caminho A da instalação, cópia completa) a checagem fica
desligada em silêncio: o loop volta a validar só nomes e o selo volta a ser
`✅ Nomes verificados`. **Falta de compilador nunca reprova uma resposta.**

## Solução de problemas

- **"Connection refused" / resposta não sai** — o Ollama não está rodando:
  abra o app do Ollama ou `ollama serve`.
- **`whitelist.txt não encontrada`** — rode `venv/bin/python indexer.py`.
- **Wiki não usada nas respostas** — rode `venv/bin/python indexer_wiki.py`.
- **Respostas ignorando instruções** — confira o aviso de "Prompt grande"
  no terminal (contexto estourando o `NUM_CTX` em `pipeline.py`).
- **Segundo usuário "travado" na interface web** — é a fila: uma geração por
  vez, por limitação da máquina.
