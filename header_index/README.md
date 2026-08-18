# Índice de Headers (`header_index/`)

O **Cérebro de Correção C++** do assistente. Funciona como um dicionário (uma "lookup table") para resolver automaticamente os `#include` corretos das classes C++ do NeoPZ, impedindo que o modelo "alucine" nomes de arquivos e cause erros de compilação.

## Por que ele existe?
O modelo costuma acertar a classe (ex: `TPZGeoMesh`), mas erra feio o nome do header na hora de importar (ex: `#include "TPZGeoMesh.h"`). No NeoPZ de verdade, o arquivo se chama `"pzgeomesh.h"`. 

Para evitar que a resposta seja reprovada de cara na validação por um erro tão bobo, o pipeline passa esse corretor ortográfico: toda vez que ele vê o modelo usando uma classe conhecida, ele injeta silenciosamente o `#include` correto no topo.

## Como funciona (Arquivos gerados)
O script varre a biblioteca inteira e gera estes mapas JSON (que **já estão salvos no repositório**, não precisa gerá-los de novo):
- `class_header_index.json`: Mapeamento determinístico de 847 classes/namespaces perfeitamente unívocas (Ex: `{"TPZCompMesh": "Mesh/pzcmesh.h"}`).
- `collisions.json`: Classes com o mesmo nome em mais de um lugar (colisões que o corretor ignora pra não errar).
- `forward_only.json`: Nomes que só apareceram como declarações adiantadas, sem um corpo de verdade.

## Como atualizar o índice
Como a API principal do NeoPZ é muito estável, esse índice quase nunca precisa ser refeito. Mas, caso a equipe crie muitas pastas novas ou mova o NeoPZ de ponta-cabeça no futuro, você pode atualizar o dicionário rodando **este script isoladamente**:

```bash
cd header_index
../venv/bin/python build_class_header_index.py ../base_de_dados/neopz --out .
```
*(Não se preocupe: isso é só pra manutenção esporádica. O usuário final que baixar o assistente não precisa rodar isso, pois o dicionário `.json` já vai junto na mala!)*
