# Indice classe -> header (NeoPZ)

Guard-rail deterministico contra alucinacao de `#include` no assistente RAG. Gerado por `build_class_header_index.py` a partir de `../base_de_dados/neopz` (o mesmo clone local usado pelo `indexer.py` para montar o corpus do RAG — antes este índice era gerado contra um clone separado em `/Users/labmec/projects/neopz`, que gerava o risco de os dois ficarem fora de sincronia entre si; agora os dois sempre apontam para a mesma fonte).

## Arquivos

- `class_header_index.json` — 847 classes/namespaces/enums/aliases sem ambiguidade, `{"TPZCompMesh": "Mesh/pzcmesh.h", ...}`. Use como lookup table: antes do LLM emitir um `#include`, valide/substitua pelo caminho aqui.
- `collisions.json` — 62 nomes definidos em mais de um header (revisar manualmente; ver notas abaixo).
- `forward_only.json` — 18 nomes só vistos como forward-declaration (nunca um corpo), majoritariamente tipos externos/internos auxiliares.
- `report.txt` — resumo da última execucao.

**2026-07-03**: `build_class_header_index.py` foi corrigido para reconhecer não só `class`/`struct`, mas também `namespace`, `using X = ...`, `typedef ... X;` e `enum`/`enum class`. Antes disso, `TPZGeoMeshTools`, `TPZCompMeshTools`, `TPZPersistenceManagerNS` (todos `namespace`) e vários enums/aliases (`TPZDrawStyle`, `TPZResidualType`, `TPZTimeDiscr`, etc.) eram completamente invisíveis a este índice e à whitelist do pipeline — o que fazia o assistente marcar código correto usando essas APIs como "alucinação". `TPZGeoMeshTools::CreateGeoMeshOnGrid` em particular é a forma padrão de criar uma malha no NeoPZ, ou seja, isso afetava perguntas bem básicas. Ver `cpp_parser.py` para a mesma correção do lado da whitelist/indexação Chroma.

## Revisão do NeoPZ (branch `neopz-develop`)

Gerado contra `852a5116c` (**develop**, 2026-06-19). A branch `main` deste projeto
usa `4c6b6d277` (2022-03-18) — que é de fato a ponta do branch `main` do
labmec/neopz, congelado desde 2022; o desenvolvimento real do NeoPZ acontece
no `develop`.

Ao atualizar a revisão do submodule, rode **sempre os dois juntos**, contra a
mesma pasta, pra não voltarem a divergir:

```bash
venv/bin/python indexer.py                                    # whitelists + base Chroma
cd header_index && ../venv/bin/python build_class_header_index.py \
    ../base_de_dados/neopz --out .                            # este índice
```

Depois disso, revalide as receitas (ver "Compilando as receitas" no README
principal) — o índice e a whitelist conferem *nomes*, não se o código compila.

## Colisões (revisão manual)

- `TPZBlackOil2P3D`, `TPZMixedDarcyFlow`: cada um tem definição duplicada entre um caminho legado `Material/needrefactor/REAL/...` e um caminho canônico mais novo. Sintoma de um padrão maior: muitas materiais "needrefactor" coexistem com versões mais novas — vale considerar deprioritizar `needrefactor/` no retrieval, ou pelo menos marcar esses resultados como legados.
- `TPZCurve`, `TPZLine`: classes genuinamente diferentes com o mesmo nome (uma em teste, outra não; ou em módulos distintos Topology/Util).
- `SPr`, `TMem`, `TComputeSequence`, `TPlasticState`, `ThreadData`: tipos internos/aninhados reaproveitados entre headers relacionados.
- `TinyFad`: especializações de template legítimas, espalhadas por 20 arquivos em `Common/FAD/TinyFad/Specializations/`.
- **Novidade (após reconhecer `using`/`typedef`)**: nomes de alias genéricos que cada classe redefine internamente com o mesmo nome curto — `TBase`, `TFAD`, `EState`, `ESolutionVars`, `SOLUTIONVARS`, `MProblemType` etc. Não é ambiguidade real da API pública, é `using TBase = AlgumaCoisaEspecificaDaClasse;` dentro de várias classes de material diferentes — corretamente marcado como colisão porque não existe *um* header certo para esses nomes fora do contexto da classe que os declara. Não tente auto-corrigir `#include` para esses nomes.

## Uso sugerido no pipeline

1. Antes de aceitar um `#include` gerado pelo LLM, verifique se a classe está em `class_header_index.json`; se estiver, force o caminho correto.
2. Se a classe estiver em `collisions.json`, sinalize para revisão humana ou desambiguação por contexto (módulo/namespace).
3. Se não estiver em nenhum dos três JSONs, é provável alucinação de nome de classe — não apenas de header.
