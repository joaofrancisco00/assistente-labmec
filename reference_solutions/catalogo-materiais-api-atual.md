# Catálogo: qual material da API atual usar para cada problema

Guia de seleção de material do NeoPZ (API atual, pós-refatoração). Todos os
construtores e headers abaixo foram conferidos contra o código-fonte real e
**validados por compilação/execução** (reference_solutions/).
Regra geral: os materiais atuais vivem em `Material/<Família>/`; tudo que
está em `Material/needrefactor/` é API antiga — não usar em código novo.

**REGRA DE INCLUDE**: material da API nova inclui-se COM o prefixo da
família — `#include "Poisson/TPZMatPoisson.h"`,
`#include "Elasticity/TPZElasticity2D.h"`,
`#include "DarcyFlow/TPZMixedDarcyFlow.h"`. Só o basename
(`"TPZMatPoisson.h"`) NÃO compila.

## Poisson / Laplace / difusão escalar (H1)

- **Classe**: `TPZMatPoisson<STATE>` — include `"Poisson/TPZMatPoisson.h"`
- **Construtor**: `TPZMatPoisson<STATE>(int id, int dim)`
- **Termo fonte**: `SetForcingFunction(lambda, pOrder)` com
  `std::function<void(const TPZVec<REAL>&, TPZVec<STATE>&)>`
- **Pós-processamento**: `"Solution"` (escalar), `"Derivative"` (vetor)
- 1 variável de estado → `val2` do contorno com 1 entrada
- Nomes antigos que NÃO existem mais: `TPZMatLaplacian`, `TPZMatPoisson3d` (legado)

## Darcy H1 (pressão)

- **Classe**: `TPZDarcyFlow` — include `"DarcyFlow/TPZDarcyFlow.h"`
- **Construtor**: `TPZDarcyFlow(int id, int dim)`
- **Permeabilidade**: `SetConstantPermeability(STATE k)` ou
  `SetPermeabilityFunction(...)` (herdados de `TPZIsotropicPermeability`)

## Darcy misto / H(div) (fluxo + pressão)

- **Classe**: `TPZMixedDarcyFlow` — include `"DarcyFlow/TPZMixedDarcyFlow.h"`
- **Construtor**: `TPZMixedDarcyFlow(int id, int dim)`
- Requer espaços de aproximação H(div) + L2 (malha multifísica — ver a
  receita completa do Darcy misto)
- Nome antigo que é legado: `TPZMixedPoisson` → usar `TPZMixedDarcyFlow`

## Elasticidade linear 2D

- **Classe**: `TPZElasticity2D` — include `"Elasticity/TPZElasticity2D.h"`
- **Configuração**: usar `TPZElasticity2D(id)` + `SetElasticity(E, nu)` +
  `SetBodyForce(fx, fy)` + `SetPlaneStress()`/`SetPlaneStrain()`.
  **NÃO usar** o construtor `(id, E, nu, fx, fy, planestress)`: tem o corpo
  vazio nesta revisão do NeoPZ (bug) — id fica -666 e a malha sai vazia sem
  nenhum erro.
- **Pós-processamento**: `"Displacement"`, `"SigmaX"`, `"SigmaY"`, `"TauXY"`,
  `"PrincipalStress1"`, `"PrincipalStress2"`
- 2 variáveis de estado → `val1` 2×2 e `val2` com 2 entradas no contorno
- Nome antigo que NÃO existe mais: `TPZMatElasticity2D`

## Elasticidade linear 3D

- **Classe**: `TPZElasticity3D` — include `"Elasticity/TPZElasticity3D.h"`
- **Construtor**: `TPZElasticity3D(int id, STATE E, STATE poisson, TPZVec<STATE> &force, ...)`
  (a força de corpo é um `TPZVec` de 3 entradas — assinatura DIFERENTE da 2D)
- **Pós-processamento**: `"Displacement"`, `"StressX"`, `"PrincipalStress"`
- 3 variáveis de estado → `val2` com 3 entradas
- **Só para 3D** — em problema 2D usar `TPZElasticity2D`

## Regras que valem para todos

- Material sempre no **heap** (`new`) — `InsertMaterialObject` assume a posse.
- Contorno: `mat->CreateBC(mat, matIdContorno, tipo, val1, val2)` com tipo
  `0` = Dirichlet, `1` = Neumann, `2` = Robin; `val2` tem tantas entradas
  quantas variáveis de estado do material.
- Funções (fonte, solução exata) via `std::function`/lambda — a classe
  `TPZDummyFunction` é da API antiga, não usar.
- Sequência obrigatória: `InsertMaterialObject` → `AutoBuild()` →
  `Assemble()` → `Solve()`.
