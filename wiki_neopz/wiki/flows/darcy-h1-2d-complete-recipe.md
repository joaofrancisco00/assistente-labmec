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

Same `CreateGMesh` / `CreateCMesh` / `SolveProblem` / `PrintResults`
skeleton as the Poisson recipe, with `enum EMatid { ENone, EDomain, EBC }`.

1. **Geometric mesh** — `TPZGeoMeshTools::CreateGeoMeshOnGrid`; `matIds`
   with `dim*2 + 1` ids when `createBoundEls=true`.
2. **Computational mesh** — just one: `TPZCompMesh` +
   `SetAllCreateFunctionsContinuous()` (H1) + `SetDefaultOrder`.
3. **Material** — `new TPZDarcyFlow(id, dim)` (always on the heap).
4. **Permeability** — `SetConstantPermeability(K)`; for a spatially varying K,
   `SetPermeabilityFunction(...)` (both from `TPZIsotropicPermeability`).
5. **Source term** — `SetForcingFunction(lambda, pOrder)` with `std::function`.
6. **Boundary** — `mat->CreateBC(mat, EBC, type, val1, val2)`:
   `type 0` = Dirichlet (imposed **pressure**), `type 1` = Neumann (imposed **normal
   flux**). One state variable → `val2` with 1 entry.
7. **`AutoBuild()`**, then `Assemble()` and `Solve()`.
8. **Solver** — the H1 system is symmetric positive definite: `ELDLt` is the
   standard direct solver (unlike the mixed formulation, which is a saddle
   point where `ECholesky` fails).
9. **Post-processing** — `TPZVTKGenerator(cmesh, fields, plotfile, vtkRes)` +
   `vtk.Do()`; real `TPZDarcyFlow` names:
   `"Pressure"`/`"Solution"` (scalar), `"Flux"`/`"MinusKGradU"` (vector,
   `-K∇p`), `"Derivative"`/`"GradU"`, `"Divergence"`, `"NormKDu"`.
   `DefineGraphMesh`/`PostProcess` is the legacy path.

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
#include "TPZVTKGenerator.h"        // TPZVTKGenerator (post-processing to .vtk)
#include <string>

enum EMatid { ENone, EDomain, EBC };   // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main() {
    constexpr int pOrder{2};
    TPZGeoMesh *gmesh = CreateGMesh(8);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    TPZLinearAnalysis an(cmesh);
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "darcy_h1_2d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh ────────────────────────────────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    // minX/maxX ALWAYS have 3 coordinates, even in 2D
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};  // size = dim

    // matIds needs dim*2 + 1 ids with createBoundEls=true (5 in 2D)
    const TPZManVector<int, 5> matIds = {EDomain, EBC, EBC, EBC, EBC};

    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular,
        /*createBoundEls=*/true);
}

// ── Computational mesh + material + boundary — ONE mesh, H1 space ────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership)
    auto *mat = new TPZDarcyFlow(EDomain, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Zero pressure (type 0 = Dirichlet; type 1 would be normal flux)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    cmesh->AutoBuild();  // without it the computational mesh stays empty
    return cmesh;
}

// ── Assemble and solve ────────────────────────────────────────────────────
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh) {
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    strmat.SetNumThreads(nThreads);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);  // symmetric system — the standard direct solver
    an.SetSolver(solver);
    an.Assemble();  // Solve does NOT assemble
    an.Solve();
}

// ── Post-processing (VTK for Paraview) — real TPZDarcyFlow names ──────────
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Pressure", "Flux"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
```

## Common mistakes

- **`TPZHybridDarcyFlow` in a simple H1 mesh** — it is a material for combined
  spaces (hybridization); in pure H1 use `TPZDarcyFlow`.
- **`TPZMixedDarcyFlow` when H1 is requested** — that is the mixed formulation; it requires
  three meshes and `TPZMultiphysicsCompMesh`.
- **Building three meshes for an H1 problem** — in H1 there is **only one** mesh; the
  flux + pressure + multiphysics architecture belongs to the mixed formulation.
- **`DefineGraphMesh`/`PostProcess` for the VTK output** — legacy path: use
  `TPZVTKGenerator` with the real `TPZDarcyFlow` names (`"Pressure"`, `"Flux"`).
- **`#include "TPZDarcyFlow.h"` without the `DarcyFlow/` prefix** — does not compile.
- **`TPZMatLaplacian`, `TPZMatPoisson3d`** — old API; for pure scalar diffusion
  there is `TPZMatPoisson`, and for Darcy with permeability, `TPZDarcyFlow`.
