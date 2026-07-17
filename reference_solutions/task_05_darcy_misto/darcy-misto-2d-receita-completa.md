# Receita completa: Darcy 2D na formulação mista (H(div) + L2) com a API atual do NeoPZ

Fluxo canônico para a equação de Darcy na formulação mista — fluxo e pressão
como incógnitas simultâneas. Padrão extraído e verificado do código real do
NeoPZ (`UnitTest_PZ/TestHDivCollapsed`, `TPZMultiphysicsCompMesh.h`).

## A ideia central: TRÊS malhas computacionais

A formulação mista **não** usa uma `TPZCompMesh` única com
`SetAllCreateFunctionsContinuous()` (isso é H1!). São três malhas:

1. **Malha atômica de FLUXO** — espaço **H(div)**
   (`SetAllCreateFunctionsHDiv()`). Material: `TPZNullMaterial<>` (marcador
   de espaço, sem física). O **contorno precisa de `TPZNullMaterial` aqui**
   (dimensão `dim-1`): é onde vivem os graus de liberdade de fluxo normal.
2. **Malha atômica de PRESSÃO** — espaço **L2**:
   `SetAllCreateFunctionsContinuous()` +
   `ApproxSpace().CreateDisconnectedElements(true)`. Material:
   `TPZNullMaterial<>`. **Sem condição de contorno.** Depois do `AutoBuild`,
   marcar todos os connects com `SetLagrangeMultiplier(1)`.
3. **Malha MULTIFÍSICA** (`TPZMultiphysicsCompMesh`) — é aqui que moram o
   material de verdade (`TPZMixedDarcyFlow`) e as condições de contorno.
   Em vez de `AutoBuild()`, chama-se
   `BuildMultiphysicsSpace(ativas, malhas)` com `malhas = {fluxo, pressao}`
   (fluxo **primeiro**) e `ativas = {1, 1}`.

Antes de criar cada malha: `gmesh->ResetReference();`

## Material e contorno

- **Classe**: `TPZMixedDarcyFlow` — header `TPZMixedDarcyFlow.h`
  (`Material/DarcyFlow/`). Construtor: `TPZMixedDarcyFlow(int id, int dim)`.
- **Permeabilidade**: `SetConstantPermeability(STATE k)`.
- **Termo fonte**: `SetForcingFunction(lambda, pOrder)` (std::function).
- **Contorno na formulação mista**: `tipo 0` impõe **pressão**;
  `tipo 1` impõe **fluxo normal** (papéis diferentes do H1!).
- O nome antigo `TPZMixedPoisson` é do legado — usar `TPZMixedDarcyFlow`.

## Solver — armadilha clássica

O sistema misto é de **ponto de sela (indefinido)**: `ECholesky` falha.
Usar `solver.SetDirect(ELDLt)` (ou `ELU`).

## Pós-processamento

Nomes reais do `TPZMixedDarcyFlow` (ver `VariableIndex`): `"Pressure"`
(escalar), `"Flux"` (vetor), `"DivFlux"` (escalar). `"Solution"` /
`"Derivative"` não existem aqui.

## Código completo (compilável)

```cpp
#include "pzgmesh.h"                  // TPZGeoMesh
#include "TPZGeoMeshTools.h"          // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"                // MMeshType::EQuadrilateral
#include "pzcmesh.h"                  // TPZCompMesh
#include "TPZMultiphysicsCompMesh.h"  // TPZMultiphysicsCompMesh
#include "TPZNullMaterial.h"          // TPZNullMaterial (malhas atômicas)
#include "TPZMixedDarcyFlow.h"        // TPZMixedDarcyFlow (API atual)
#include "TPZLinearAnalysis.h"        // TPZLinearAnalysis
#include "pzskylstrmatrix.h"          // TPZSkylineStructMatrix
#include "pzstepsolver.h"             // TPZStepSolver
#include "pzmanvector.h"              // TPZManVector
#include "pzfmatrix.h"                // TPZFMatrix
#include "pzvec.h"                    // TPZVec

constexpr int matIdDominio{1};
constexpr int matIdContorno{-1};

// Malha atômica de FLUXO: espaço H(div) — contorno TEM material aqui
TPZCompMesh *CriarMalhaFluxo(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDominio, dim, nstate));
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdContorno, dim - 1, nstate));
    cmesh->SetAllCreateFunctionsHDiv();
    cmesh->SetDefaultOrder(pOrder);
    cmesh->AutoBuild();
    return cmesh;
}

// Malha atômica de PRESSÃO: espaço L2, sem contorno, connects = multiplicador
TPZCompMesh *CriarMalhaPressao(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDominio, dim, nstate));
    cmesh->SetAllCreateFunctionsContinuous();
    cmesh->ApproxSpace().CreateDisconnectedElements(true);  // L2
    cmesh->AutoBuild();
    for (int64_t i = 0; i < cmesh->NConnects(); i++) {
        cmesh->ConnectVec()[i].SetLagrangeMultiplier(1);
    }
    return cmesh;
}

int main() {
    // 1. Malha geométrica
    constexpr int dim{2};
    constexpr int pOrder{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    const TPZManVector<int, 5> matIds = {matIdDominio, matIdContorno,
                                         matIdContorno, matIdContorno,
                                         matIdContorno};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, true);

    // 2. Malhas atômicas
    TPZCompMesh *cmeshFluxo   = CriarMalhaFluxo(gmesh, dim, pOrder);
    TPZCompMesh *cmeshPressao = CriarMalhaPressao(gmesh, dim, pOrder);

    // 3. Malha multifísica — física e contorno moram aqui
    gmesh->ResetReference();
    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    auto *mat = new TPZMixedDarcyFlow(matIdDominio, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);  // pressão = 0
    cmesh->InsertMaterialObject(bnd);

    TPZManVector<TPZCompMesh *, 2> malhas = {cmeshFluxo, cmeshPressao};
    TPZManVector<int, 2> ativas = {1, 1};
    cmesh->BuildMultiphysicsSpace(ativas, malhas);

    // 4. Montar e resolver — ponto de sela: ELDLt, NUNCA ECholesky
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 5. Pós-processamento — nomes reais do TPZMixedDarcyFlow
    const TPZManVector<std::string, 2> scalnames = {"Pressure", "DivFlux"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_misto2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete cmeshFluxo;
    delete cmeshPressao;
    delete gmesh;
    return 0;
}
```

## Erros comuns

- **Usar uma malha só com `SetAllCreateFunctionsContinuous()`** — isso é H1,
  não é formulação mista. Mista = 3 malhas (fluxo H(div), pressão L2,
  multifísica).
- **`TPZHybridDarcyFlow` no lugar de `TPZMixedDarcyFlow`** — híbrida é outra
  formulação; para fluxo+pressão clássico, `TPZMixedDarcyFlow`.
- **`TPZFlowCompMesh`** — é malha para CFD (escoamento compressível), nada a
  ver com Darcy.
- **`ECholesky` no solver** — o sistema misto é indefinido; usar `ELDLt`.
- **Esquecer o `TPZNullMaterial` de contorno na malha de fluxo** — sem ele
  não há graus de liberdade de fluxo na fronteira e o contorno não funciona.
- **Esquecer `SetLagrangeMultiplier(1)` nos connects da pressão** — a ordem
  de montagem/condensação fica errada.
- **Esquecer `gmesh->ResetReference()`** antes de criar cada malha — os
  elementos computacionais apontam para a malha errada.
- **Chamar `AutoBuild()` na multifísica** — quem constrói é
  `BuildMultiphysicsSpace(ativas, malhas)`.
- **`TPZMixedPoisson`** — legado; usar `TPZMixedDarcyFlow`.
