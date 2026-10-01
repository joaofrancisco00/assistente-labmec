# Complete recipe: 2D Darcy flow in H1 (primal formulation) with the current NeoPZ API

Solves `-∇·(K ∇p) = f` with the pressure as the only unknown, in an **H1**
approximation space (single computational mesh). Structurally it is the same
recipe as 2D Poisson — what changes is the material and the permeability.

## Which Darcy material to use — the most common confusion

NeoPZ has three Darcy materials, one for each formulation. Choosing the
wrong one is the #1 mistake in this family:

| Formulation | Class | Space / meshes |
|---|---|---|
| **Primal (H1)** ← this recipe | `TPZDarcyFlow` | continuous H1, **one** mesh |
| Mixed | `TPZMixedDarcyFlow` | H(div) + L2, **three** meshes (multiphysics) |
| Hybridized | `TPZHybridDarcyFlow` | **combined** spaces; inherits from `TPZDarcyFlow`, but it is for hybridization/MHM — it is **not** the material of a simple H1 mesh |

Include with the family prefix: `#include "DarcyFlow/TPZDarcyFlow.h"`
(plain `"TPZDarcyFlow.h"` does not compile).

## Step by step

1. **Geometric mesh** — `TPZGeoMeshTools::CreateGeoMeshOnGrid`; `matIds`
   with `dim*2 + 1` ids when `createBoundEls=true`.
2. **Computational mesh** — just one: `TPZCompMesh` +
   `SetAllCreateFunctionsContinuous()` (H1) + `SetDefaultOrder`.
3. **Material** — `new TPZDarcyFlow(id, dim)` (always on the heap).
4. **Permeability** — `SetConstantPermeability(K)`; for a spatially varying K,
   `SetPermeabilityFunction(...)` (both from `TPZIsotropicPermeability`).
5. **Source term** — `SetForcingFunction(lambda, pOrder)` with `std::function`.
6. **Boundary** — `mat->CreateBC(mat, matIdBoundary, type, val1, val2)`:
   `type 0` = Dirichlet (imposed **pressure**), `type 1` = Neumann (imposed **normal
   flux**). One state variable → `val2` with 1 entry.
7. **`AutoBuild()`**, then `Assemble()` and `Solve()`.
8. **Solver** — the H1 system is SPD: `ECholesky` works (unlike the
   mixed formulation, which is a saddle point and requires `ELDLt`).
9. **Post-processing** — real `TPZDarcyFlow` names:
   `"Pressure"`/`"Solution"` (scalar), `"Flux"`/`"MinusKGradU"` (vector,
   `-K∇p`), `"Derivative"`/`"GradU"`, `"Divergence"`, `"NormKDu"`.

## Complete code

```cpp
#include "pzgmesh.h"                // TPZGeoMesh
#include "TPZGeoMeshTools.h"        // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"              // MMeshType::ETriangular
#include "pzcmesh.h"                // TPZCompMesh
#include "DarcyFlow/TPZDarcyFlow.h" // TPZDarcyFlow (H1 — family prefix!)
#include "TPZLinearAnalysis.h"      // TPZLinearAnalysis
#include "pzskylstrmatrix.h"        // TPZSkylineStructMatrix
#include "pzstepsolver.h"           // TPZStepSolver
#include "pzmanvector.h"            // TPZManVector
#include "pzfmatrix.h"              // TPZFMatrix
#include "pzvec.h"                  // TPZVec

int main() {
    // 1. Geometric mesh
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    constexpr int matIdDomain{1};
    constexpr int matIdBoundary{-1};
    const TPZManVector<int, 5> matIds = {matIdDomain, matIdBoundary,
                                         matIdBoundary, matIdBoundary,
                                         matIdBoundary};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular, true);

    // 2. Computational mesh — ONE mesh, H1 space
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. Material (on the heap — the mesh takes ownership)
    auto *mat = new TPZDarcyFlow(matIdDomain, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // 4. Boundary: zero pressure (type 0 = Dirichlet; type 1 would be normal flux)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // 5. Build the mesh
    cmesh->AutoBuild();

    // 6. Assemble and solve (H1 is SPD → ECholesky)
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 7. Post-processing (VTK) — real TPZDarcyFlow names
    const TPZManVector<std::string, 1> scalnames = {"Pressure"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_h1_2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Common mistakes

- **`TPZHybridDarcyFlow` in a simple H1 mesh** — it is a material for combined
  spaces (hybridization); in pure H1 use `TPZDarcyFlow`.
- **`TPZMixedDarcyFlow` when H1 is requested** — that is the mixed formulation; it requires
  three meshes and `TPZMultiphysicsCompMesh`.
- **Building three meshes for an H1 problem** — in H1 there is **only one** mesh; the
  flux + pressure + multiphysics architecture belongs to the mixed formulation.
- **`ELDLt` "just to be safe"** — not needed here; the H1 system is SPD.
  (In the mixed formulation, then yes, `ECholesky` fails.)
- **`#include "TPZDarcyFlow.h"` without the `DarcyFlow/` prefix** — does not compile.
- **`TPZMatLaplacian`, `TPZMatPoisson3d`** — old API; for pure scalar diffusion
  there is `TPZMatPoisson`, and for Darcy with permeability, `TPZDarcyFlow`.
