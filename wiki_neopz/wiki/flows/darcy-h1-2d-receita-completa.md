# Receita completa: fluxo de Darcy 2D em H1 (formulação primal) com a API atual do NeoPZ

Resolve `-∇·(K ∇p) = f` com a pressão como única incógnita, em espaço de
aproximação **H1** (malha computacional única). Estruturalmente é a mesma
receita do Poisson 2D — o que muda é o material e a permeabilidade.

## Qual material de Darcy usar — a confusão mais comum

O NeoPZ tem três materiais de Darcy, um para cada formulação. Escolher o
errado é o erro nº 1 nesta família:

| Formulação | Classe | Espaço / malhas |
|---|---|---|
| **Primal (H1)** ← esta receita | `TPZDarcyFlow` | H1 contínuo, **uma** malha |
| Mista | `TPZMixedDarcyFlow` | H(div) + L2, **três** malhas (multifísica) |
| Hibridizada | `TPZHybridDarcyFlow` | espaços **combinados**; herda de `TPZDarcyFlow`, mas é para hibridização/MHM — **não** é o material de uma malha H1 simples |

Include com o prefixo da família: `#include "DarcyFlow/TPZDarcyFlow.h"`
(só `"TPZDarcyFlow.h"` não compila).

## Passo a passo

1. **Malha geométrica** — `TPZGeoMeshTools::CreateGeoMeshOnGrid`; `matIds`
   com `dim*2 + 1` ids quando `createBoundEls=true`.
2. **Malha computacional** — uma só: `TPZCompMesh` +
   `SetAllCreateFunctionsContinuous()` (H1) + `SetDefaultOrder`.
3. **Material** — `new TPZDarcyFlow(id, dim)` (sempre no heap).
4. **Permeabilidade** — `SetConstantPermeability(K)`; para K variável no
   espaço, `SetPermeabilityFunction(...)` (ambos de `TPZIsotropicPermeability`).
5. **Termo fonte** — `SetForcingFunction(lambda, pOrder)` com `std::function`.
6. **Contorno** — `mat->CreateBC(mat, matIdContorno, tipo, val1, val2)`:
   `tipo 0` = Dirichlet (**pressão** imposta), `tipo 1` = Neumann (**fluxo
   normal** imposto). Uma variável de estado → `val2` com 1 entrada.
7. **`AutoBuild()`**, depois `Assemble()` e `Solve()`.
8. **Solver** — o sistema H1 é SPD: `ECholesky` serve (diferente da
   formulação mista, que é ponto de sela e exige `ELDLt`).
9. **Pós-processamento** — nomes reais do `TPZDarcyFlow`:
   `"Pressure"`/`"Solution"` (escalar), `"Flux"`/`"MinusKGradU"` (vetor,
   `-K∇p`), `"Derivative"`/`"GradU"`, `"Divergence"`, `"NormKDu"`.

## Código completo

```cpp
#include "pzgmesh.h"                // TPZGeoMesh
#include "TPZGeoMeshTools.h"        // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"              // MMeshType::ETriangular
#include "pzcmesh.h"                // TPZCompMesh
#include "DarcyFlow/TPZDarcyFlow.h" // TPZDarcyFlow (H1 — prefixo da família!)
#include "TPZLinearAnalysis.h"      // TPZLinearAnalysis
#include "pzskylstrmatrix.h"        // TPZSkylineStructMatrix
#include "pzstepsolver.h"           // TPZStepSolver
#include "pzmanvector.h"            // TPZManVector
#include "pzfmatrix.h"              // TPZFMatrix
#include "pzvec.h"                  // TPZVec

int main() {
    // 1. Malha geométrica
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    constexpr int matIdDominio{1};
    constexpr int matIdContorno{-1};
    const TPZManVector<int, 5> matIds = {matIdDominio, matIdContorno,
                                         matIdContorno, matIdContorno,
                                         matIdContorno};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular, true);

    // 2. Malha computacional — UMA malha, espaço H1
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. Material (no heap — a malha assume a posse)
    auto *mat = new TPZDarcyFlow(matIdDominio, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // 4. Contorno: pressão nula (tipo 0 = Dirichlet; tipo 1 seria fluxo normal)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // 5. Construir a malha
    cmesh->AutoBuild();

    // 6. Montar e resolver (H1 é SPD → ECholesky)
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 7. Pós-processamento (VTK) — nomes reais do TPZDarcyFlow
    const TPZManVector<std::string, 1> scalnames = {"Pressure"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_h1_2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Erros comuns

- **`TPZHybridDarcyFlow` numa malha H1 simples** — é material de espaços
  combinados (hibridização); em H1 puro use `TPZDarcyFlow`.
- **`TPZMixedDarcyFlow` quando o pedido é H1** — é a formulação mista, exige
  três malhas e `TPZMultiphysicsCompMesh`.
- **Montar três malhas para um problema H1** — em H1 é **uma** malha só; a
  arquitetura de fluxo + pressão + multifísica é da formulação mista.
- **`ELDLt` "por segurança"** — não é necessário aqui; o sistema H1 é SPD.
  (Na formulação mista, aí sim `ECholesky` falha.)
- **`#include "TPZDarcyFlow.h"` sem o prefixo `DarcyFlow/`** — não compila.
- **`TPZMatLaplacian`, `TPZMatPoisson3d`** — API antiga; para difusão escalar
  pura existe `TPZMatPoisson`, e para Darcy com permeabilidade, `TPZDarcyFlow`.
