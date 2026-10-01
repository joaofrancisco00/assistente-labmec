# Complete recipe: 2D Darcy in the mixed formulation (H(div) + L2) with the current NeoPZ API

Canonical flow for the Darcy equation in the mixed formulation — flux and pressure
as simultaneous unknowns. Pattern extracted from
`UnitTest_PZ/TestHDivCollapsed` and `TPZMultiphysicsCompMesh.h`.

## The central idea: THREE computational meshes

The mixed formulation does **not** use a single `TPZCompMesh` with
`SetAllCreateFunctionsContinuous()` (that is H1!). There are three meshes:

1. **Atomic FLUX mesh** — **H(div)** space
   (`SetAllCreateFunctionsHDiv()`). Material: `TPZNullMaterial<>` (space
   marker, no physics). The **boundary needs a `TPZNullMaterial` here**
   (dimension `dim-1`): that is where the normal-flux degrees of freedom live.
2. **Atomic PRESSURE mesh** — **L2** space:
   `SetAllCreateFunctionsContinuous()` +
   `ApproxSpace().CreateDisconnectedElements(true)`. Material:
   `TPZNullMaterial<>`. **No boundary condition.** After `AutoBuild`,
   mark every connect with `SetLagrangeMultiplier(1)`.
3. **MULTIPHYSICS mesh** (`TPZMultiphysicsCompMesh`) — this is where the
   real material (`TPZMixedDarcyFlow`) and the boundary conditions live.
   It is **mandatory** to call `SetAllCreateFunctionsMultiphysicElem()` before
   building (without it: `DebugStop` inside NeoPZ — found by running
   this recipe). Instead of `AutoBuild()`, call
   `BuildMultiphysicsSpace(active, meshes)` with `meshes = {flux, pressure}`
   (flux **first**) and `active = {1, 1}`.

Before creating each mesh: `gmesh->ResetReference();`

## Material and boundary

- **Class**: `TPZMixedDarcyFlow` — include `"DarcyFlow/TPZMixedDarcyFlow.h"`
  (with the family prefix; the basename alone does not compile).
  Constructor: `TPZMixedDarcyFlow(int id, int dim)`.
- **Permeability**: `SetConstantPermeability(STATE k)`.
- **Source term**: `SetForcingFunction(lambda, pOrder)` (std::function).
- **Boundary in the mixed formulation**: `type 0` imposes **pressure**;
  `type 1` imposes **normal flux** (different roles than in H1!).
- The old name `TPZMixedPoisson` is legacy — use `TPZMixedDarcyFlow`.

## Solver — classic pitfall

The mixed system is a **saddle point (indefinite)** problem: `ECholesky` fails.
Use `solver.SetDirect(ELDLt)` (or `ELU`).

## Post-processing

Real `TPZMixedDarcyFlow` names (see `VariableIndex`): `"Pressure"`
(scalar), `"Flux"` (vector), `"DivFlux"` (scalar). `"Solution"` /
`"Derivative"` do not exist here.

## Complete code (compilable)

```cpp
#include "pzgmesh.h"                  // TPZGeoMesh
#include "TPZGeoMeshTools.h"          // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"                // MMeshType::EQuadrilateral
#include "pzcmesh.h"                  // TPZCompMesh
#include "TPZMultiphysicsCompMesh.h"  // TPZMultiphysicsCompMesh
#include "TPZNullMaterial.h"          // TPZNullMaterial (atomic meshes)
#include "DarcyFlow/TPZMixedDarcyFlow.h"  // TPZMixedDarcyFlow (current API — family prefix!)
#include "TPZLinearAnalysis.h"        // TPZLinearAnalysis
#include "pzskylstrmatrix.h"          // TPZSkylineStructMatrix
#include "pzstepsolver.h"             // TPZStepSolver
#include "pzmanvector.h"              // TPZManVector
#include "pzfmatrix.h"                // TPZFMatrix
#include "pzvec.h"                    // TPZVec

constexpr int matIdDomain{1};
constexpr int matIdBoundary{-1};

// Atomic FLUX mesh: H(div) space — the boundary HAS a material here
TPZCompMesh *CreateFluxMesh(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDomain, dim, nstate));
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdBoundary, dim - 1, nstate));
    cmesh->SetAllCreateFunctionsHDiv();
    cmesh->SetDefaultOrder(pOrder);
    cmesh->AutoBuild();
    return cmesh;
}

// Atomic PRESSURE mesh: L2 space, no boundary, connects = multiplier
TPZCompMesh *CreatePressureMesh(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDomain, dim, nstate));
    cmesh->SetAllCreateFunctionsContinuous();
    cmesh->ApproxSpace().CreateDisconnectedElements(true);  // L2
    cmesh->AutoBuild();
    for (int64_t i = 0; i < cmesh->NConnects(); i++) {
        cmesh->ConnectVec()[i].SetLagrangeMultiplier(1);
    }
    return cmesh;
}

int main() {
    // 1. Geometric mesh
    constexpr int dim{2};
    constexpr int pOrder{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    const TPZManVector<int, 5> matIds = {matIdDomain, matIdBoundary,
                                         matIdBoundary, matIdBoundary,
                                         matIdBoundary};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, true);

    // 2. Atomic meshes
    TPZCompMesh *cmeshFlux     = CreateFluxMesh(gmesh, dim, pOrder);
    TPZCompMesh *cmeshPressure = CreatePressureMesh(gmesh, dim, pOrder);

    // 3. Multiphysics mesh — physics and boundary live here
    gmesh->ResetReference();
    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    auto *mat = new TPZMixedDarcyFlow(matIdDomain, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);  // pressure = 0
    cmesh->InsertMaterialObject(bnd);

    // Multiphysics style BEFORE building — without it: DebugStop
    cmesh->SetAllCreateFunctionsMultiphysicElem();

    TPZManVector<TPZCompMesh *, 2> meshes = {cmeshFlux, cmeshPressure};
    TPZManVector<int, 2> active = {1, 1};
    cmesh->BuildMultiphysicsSpace(active, meshes);

    // 4. Assemble and solve — saddle point: ELDLt, NEVER ECholesky
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 5. Post-processing — real TPZMixedDarcyFlow names
    const TPZManVector<std::string, 2> scalnames = {"Pressure", "DivFlux"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_mixed2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete cmeshFlux;
    delete cmeshPressure;
    delete gmesh;
    return 0;
}
```

## Common mistakes

- **Using a single mesh with `SetAllCreateFunctionsContinuous()`** — that is H1,
  not the mixed formulation. Mixed = 3 meshes (H(div) flux, L2 pressure,
  multiphysics).
- **`TPZHybridDarcyFlow` instead of `TPZMixedDarcyFlow`** — hybrid is another
  formulation; for classic flux+pressure, use `TPZMixedDarcyFlow`.
- **`TPZFlowCompMesh`** — this is a mesh for CFD (compressible flow), nothing to
  do with Darcy.
- **`ECholesky` in the solver** — the mixed system is indefinite; use `ELDLt`.
- **Forgetting the boundary `TPZNullMaterial` in the flux mesh** — without it
  there are no flux degrees of freedom on the boundary and the boundary condition does not work.
- **Forgetting `SetLagrangeMultiplier(1)` on the pressure connects** — the
  assembly/condensation order is wrong.
- **Forgetting `gmesh->ResetReference()`** before creating each mesh — the
  computational elements point to the wrong mesh.
- **Calling `AutoBuild()` on the multiphysics mesh** — what builds it is
  `BuildMultiphysicsSpace(active, meshes)`.
- **Forgetting `SetAllCreateFunctionsMultiphysicElem()` before
  `BuildMultiphysicsSpace`** — immediate `DebugStop` inside NeoPZ.
- **`#include "TPZMixedDarcyFlow.h"` without the `DarcyFlow/` prefix** — does not compile.
- **`TPZMixedPoisson`** — legacy; use `TPZMixedDarcyFlow`.
