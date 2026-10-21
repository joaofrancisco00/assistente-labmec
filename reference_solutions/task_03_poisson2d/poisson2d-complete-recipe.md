# Complete recipe: 2D Poisson with the current NeoPZ API

Canonical flow to solve `-∇²u = f` on a rectangle with a Dirichlet
condition, using the **current API** (post-material-refactoring). Use this
example as the skeleton for any scalar H1 problem.
(The verification status of this recipe is in the project README, not here:
that information is for the assistant maintainers, not to be copied into the answer.)

**Includes of new-API materials carry the family prefix**:
`#include "Poisson/TPZMatPoisson.h"` — plain `"TPZMatPoisson.h"` does NOT compile
(NeoPZ only propagates the top-level directories as include paths, and the
new materials live in subfolders of `Material/`).

## Step by step

Organize the program into `CreateGMesh` / `CreateCMesh` / `SolveProblem` /
`PrintResults` functions (the skeleton real LabMeC code uses), with an
`enum EMatid { ENone, EDomain, EBC }` for the material ids — id `0` is never
used.

1. **Geometric mesh** — `TPZGeoMeshTools::CreateGeoMeshOnGrid(dim, minX, maxX, matIds, nDivs, meshType, createBoundEls)`.
   - `minX`/`maxX` **always** with 3 coordinates, even in 2D.
   - `nDivs` with size equal to `dim`.
   - `matIds` needs `dim*2 + 1` ids when `createBoundEls=true` (in 2D: 1 for the domain + 4 for the boundaries). Passing a single id hits `DebugStop`.
2. **Computational mesh** — `TPZCompMesh` + `SetDimModel` + `SetDefaultOrder` + `SetAllCreateFunctionsContinuous()` (continuous H1).
3. **Material** — `TPZMatPoisson<STATE>` (include `"Poisson/TPZMatPoisson.h"` — with the family prefix!). Always created with `new`: the mesh takes ownership of the pointer.
4. **Source term** — `SetForcingFunction(lambda, pOrder)` with `std::function<void(const TPZVec<REAL>&, TPZVec<STATE>&)>`.
5. **Boundary condition** — `mat->CreateBC(mat, EBC, type, val1, val2)` and insert the result into the mesh. Types: `0` = Dirichlet, `1` = Neumann, `2` = Robin.
6. **`cmesh->AutoBuild()`** — without it the computational mesh stays empty.
7. **Analysis** — `TPZLinearAnalysis` + `TPZSkylineStructMatrix<STATE>` (call `strmat.SetNumThreads(nThreads)`) + `TPZStepSolver<STATE>::SetDirect(ELDLt)` — the standard direct solver for symmetric systems. Call `Assemble()` **before** `Solve()` — `Solve()` does not assemble the system by itself.
8. **Post-processing** — `TPZVTKGenerator(cmesh, fields, plotfile, vtkRes)` + `vtk.Do()` writes `<plotfile>.0.vtk`. The field names are the real variable names of `TPZMatPoisson`: `"Solution"` (scalar) and `"Derivative"` (vector). `DefineGraphMesh`/`PostProcess` is the legacy path.

## Complete code (compilable)

```cpp
#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::ETriangular
#include "pzcmesh.h"            // TPZCompMesh
#include "Poisson/TPZMatPoisson.h"  // TPZMatPoisson<STATE> (current API — family prefix!)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix
#include "pzvec.h"              // TPZVec
#include "TPZVTKGenerator.h"    // TPZVTKGenerator (post-processing to .vtk)
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
    PrintResults(cmesh, "poisson2d");
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

// ── Computational mesh + material + boundary ─────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership)
    auto *mat = new TPZMatPoisson<STATE>(EDomain, dim);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Homogeneous Dirichlet boundary condition (type 0)
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

// ── Post-processing (VTK for Paraview) ────────────────────────────────────
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Solution", "Derivative"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
```

## Common mistakes (old API and pitfalls)

- **`TPZMatLaplacian` no longer exists** — it was replaced by `TPZMatPoisson` in the material refactoring. For mixed/flow formulations, see `TPZDarcyFlow` and `TPZMixedDarcyFlow`.
- **`TPZDummyFunction` is the old API** — the current API uses `std::function` directly in `SetForcingFunction`/`SetExactSol`. Do not mix the two.
- **Material on the stack** — `TPZMatPoisson<STATE> material(...); cmesh->InsertMaterialObject(&material);` crashes when the mesh is destroyed. Always use `new`.
- **`matIds` with the wrong size** in `CreateGeoMeshOnGrid` — it needs `dim*2 + 1` ids with `createBoundEls=true`.
- **Forgetting `AutoBuild()`** — the computational mesh stays empty and the analysis has nothing to assemble.
- **Calling `Solve()` without `Assemble()`** — the system is never assembled.
- **`DefineGraphMesh`/`PostProcess` for the VTK output** — legacy path: use `TPZVTKGenerator(cmesh, fields, plotfile, vtkRes)` + `vtk.Do()`. And the field names are per-material: an unknown name (e.g. `"Displacement"` on a Poisson material) hits `DebugStop` at runtime.
- **`#include "NeoPZ.h"`** — there is no single header in NeoPZ; each class has its own.
- **`#include "TPZMatPoisson.h"` without the `Poisson/` prefix** — does not compile;
  the new-API materials live in subfolders of `Material/` and the include carries
  the family name.
