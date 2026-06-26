# Indice classe -> header (NeoPZ)

Guard-rail deterministico contra alucinacao de `#include` no assistente RAG. Gerado por `build_class_header_index.py` a partir do clone local em `/Users/labmec/projects/neopz`.

## Arquivos

- `class_header_index.json` — 649 classes sem ambiguidade, `{"TPZCompMesh": "Mesh/pzcmesh.h", ...}`. Use como lookup table: antes do LLM emitir um `#include`, valide/substitua pelo caminho aqui.
- `collisions.json` — 10 classes definidas em mais de um header (revisar manualmente; ver notas abaixo).
- `forward_only.json` — 17 classes só vistas como forward-declaration (nunca um corpo), majoritariamente tipos externos/internos auxiliares.
- `report.txt` — resumo da última execucao.

## Caveat importante: clone desatualizado

O clone usado (`/Users/labmec/projects/neopz`) esta no commit `4c6b6d2` de **2022-03-18** — cerca de 4 anos atras da data de hoje. Antes de depender deste indice em produção:

1. `git pull` (ou re-clone) o NeoPZ.
2. Rode novamente: `python3 build_class_header_index.py /caminho/para/neopz --out ./header_index`.
3. Repita periodicamente (ex: a cada release ou mensalmente) para manter o indice sincronizado com o codigo.

Se o corpus do RAG foi montado sobre esse mesmo commit antigo, os dois estão pelo menos consistentes entre si — mas vale confirmar.

## Colisões (revisão manual)

- `TPZBlackOil2P3D`, `TPZMixedDarcyFlow`: cada um tem definição duplicada entre um caminho legado `Material/needrefactor/REAL/...` e um caminho canônico mais novo. Sintoma de um padrão maior: muitas materiais "needrefactor" coexistem com versões mais novas — vale considerar deprioritizar `needrefactor/` no retrieval, ou pelo menos marcar esses resultados como legados.
- `TPZCurve`, `TPZLine`: classes genuinamente diferentes com o mesmo nome (uma em teste, outra não; ou em módulos distintos Topology/Util).
- `SPr`, `TMem`, `TComputeSequence`, `TPlasticState`, `ThreadData`: tipos internos/aninhados reaproveitados entre headers relacionados.
- `TinyFad`: especializações de template legítimas, espalhadas por 20 arquivos em `Common/FAD/TinyFad/Specializations/`.

## Uso sugerido no pipeline

1. Antes de aceitar um `#include` gerado pelo LLM, verifique se a classe está em `class_header_index.json`; se estiver, force o caminho correto.
2. Se a classe estiver em `collisions.json`, sinalize para revisão humana ou desambiguação por contexto (módulo/namespace).
3. Se não estiver em nenhum dos três JSONs, é provável alucinação de nome de classe — não apenas de header.
