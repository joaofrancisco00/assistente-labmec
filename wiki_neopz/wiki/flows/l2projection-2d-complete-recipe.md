# Complete recipe: 2D L2 projection with the current NeoPZ API

Canonical flow to project a known function `f(x,y)` onto an H1 space of
order `p`, using `TPZL2Projection`: find `u_h` such that
`(u_h, v) = (f, v)` for every `v` in the discrete space. Useful to initialize
a solution, interpolate data onto a mesh or test the convergence of an
approximation space.
(The verification status of this recipe is in the project README, not here:
that information is for the assistant maintainers, not to be copied into the answer.)

**The include carries the family prefix, and only it**:
`#include "Projection/TPZL2Projection.h"`. Neither `"TPZL2Projection.h"` nor
`"Material/Projection/TPZL2Projection.h"` compile (NeoPZ propagates the
top-level directories as include paths, and `Material/` is one of them).

## Step by step

Same `CreateGMesh` / `CreateCMesh` / `SolveProblem` / `PrintResults`
skeleton as the other recipes, with `enum EMatid { ENone, EDomain }` — a
pure L2 projection has **no boundary condition**, so there is no BC id.

1. **Geometric mesh** — `TPZGeoMeshTools::CreateGeoMeshOnGrid(dim, minX, maxX, matIds, nDivs, meshType, createBoundEls)`.
   - A pure L2 projection **has no boundary condition**: the mass matrix is already symmetric positive definite. Use `createBoundEls = false` and `matIds` with **a single id** (the domain one).
   - `minX`/`maxX` always with 3 coordinates, even in 2D; `nDivs` with size `dim`.
2. **Computational mesh** — `TPZCompMesh` + `SetDimModel` + `SetDefaultOrder(p)` + `SetAllCreateFunctionsContinuous()` (H1).
3. **Material** — `new TPZL2Projection<STATE>(EDomain, dim)` (optional third argument: `nstate`, default 1). Always with `new`: the mesh takes ownership.
4. **Function to project** — it enters through the material **forcing function**: `SetForcingFunction(func, integrationOrder)`, with `func` of type `void(const TPZVec<REAL>&, TPZVec<STATE>&)`. There is no `SetFunction`/`SetProjection` method.
5. **(Optional) Exact solution for the error** — `SetExactSol(func, integrationOrder)`, with `func` of type `void(const TPZVec<REAL>&, TPZVec<STATE>&, TPZFMatrix<STATE>&)` (value + gradient).
6. **`cmesh->AutoBuild()`**.
7. **Analysis** — `TPZLinearAnalysis` + `TPZSkylineStructMatrix<STATE>` (`SetNumThreads(nThreads)`) + `TPZStepSolver<STATE>::SetDirect(ELDLt)` (the mass matrix is symmetric; `ELDLt` is the standard direct solver). `Assemble()` before `Solve()`.
8. **Error** — `an.PostProcessError(errors, false)` with `errors` **already sized with 3 entries**: `[0]` H1 norm, `[1]` L2 norm, `[2]` H1 seminorm.
9. **Post-processing** — `TPZVTKGenerator(cmesh, fields, plotfile, vtkRes)` + `vtk.Do()`. The field names are the real variable names of `TPZL2Projection`: `"Solution"` (scalar) and `"Derivative"` (vector). `DefineGraphMesh`/`PostProcess` is the legacy path.

## Complete code (compilable)

It runs a convergence study: with `p = 2`, the L2 error of the projection should
decrease with a rate close to `p + 1 = 3` at each mesh refinement.

```cpp
#include <cmath>
#include <iostream>
#include <string>

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::EQuadrilateral
#include "pzcmesh.h"            // TPZCompMesh
#include "Projection/TPZL2Projection.h"  // TPZL2Projection<STATE> (family prefix!)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix
#include "pzvec.h"              // TPZVec
#include "TPZVTKGenerator.h"    // TPZVTKGenerator (post-processing to .vtk)

enum EMatid { ENone, EDomain };   // material ids: 0 is never used; no BC here
constexpr int nThreads{4};        // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);
REAL ProjectL2(int nDiv, int pOrder, bool exportVTK);

// Function to project: f(x,y) = sin(πx)·sin(πy)
static void TargetFunction(const TPZVec<REAL> &x, TPZVec<STATE> &f) {
    f[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
}

// Same function + gradient, for the error computation (ExactSolType signature)
static void ExactSolution(const TPZVec<REAL> &x, TPZVec<STATE> &u,
                          TPZFMatrix<STATE> &du) {
    u[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(0, 0) = M_PI * std::cos(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(1, 0) = M_PI * std::sin(M_PI * x[0]) * std::cos(M_PI * x[1]);
}

int main() {
    constexpr int pOrder{2};
    const int divisions[] = {4, 8, 16};

    REAL previousError = -1.;
    for (int nDiv : divisions) {
        const REAL error = ProjectL2(nDiv, pOrder, nDiv == 16);
        std::cout << "mesh " << nDiv << "x" << nDiv << "  L2 error = " << error;
        if (previousError > 0.)
            std::cout << "  rate = " << std::log2(previousError / error);
        std::cout << '\n';
        previousError = error;
    }
    return 0;
}

// ── Geometric mesh ────────────────────────────────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    // minX/maxX ALWAYS have 3 coordinates, even in 2D
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};  // size = dim

    // No boundary condition: createBoundEls=false and a SINGLE matId
    const TPZManVector<int, 1> matIds = {EDomain};

    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral,
        /*createBoundEls=*/false);
}

// ── Computational mesh + projection material ──────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership)
    auto *mat = new TPZL2Projection<STATE>(EDomain, dim);
    mat->SetForcingFunction(TargetFunction, pOrder + 2);  // function to project
    mat->SetExactSol(ExactSolution, pOrder + 2);          // only for the error
    cmesh->InsertMaterialObject(mat);

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

// ── Projects f onto an nDiv×nDiv mesh and returns the L2 error ────────────
REAL ProjectL2(int nDiv, int pOrder, bool exportVTK) {
    TPZGeoMesh *gmesh = CreateGMesh(nDiv);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    TPZLinearAnalysis an(cmesh);
    SolveProblem(an, cmesh);

    // Error: [0] = H1 norm, [1] = L2 norm, [2] = H1 seminorm
    // (the vector MUST arrive with size 3)
    TPZManVector<REAL, 3> errors(3, 0.);
    an.PostProcessError(errors, false);
    const REAL errorL2 = errors[1];

    if (exportVTK) {
        PrintResults(cmesh, "l2projection");
    }
    delete cmesh;
    delete gmesh;
    return errorL2;
}
```

## Common mistakes (pitfalls)

- **`#include "Material/Projection/TPZL2Projection.h"`** — does not compile: the prefix is only the family, `"Projection/TPZL2Projection.h"`.
- **Creating a boundary condition unnecessarily** — the L2 projection does not need a BC. If you still use `createBoundEls = true`, `matIds` then needs `dim*2 + 1` ids (in 2D: 1 for the domain + 4 for the boundaries).
- **Looking for a method to "pass the function"** — the function to project is the forcing function (`SetForcingFunction`). Without it, the material projects the constant solution passed to the constructor (zero by default).
- **`PostProcessError` with an empty vector** — `TPZManVector<REAL,3> errors;` has size 0 and aborts with *"error vector incompatible with material"*. Size it with `errors(3, 0.)`.
- **`DefineGraphMesh`/`PostProcess`** — legacy path: use `TPZVTKGenerator`, and the field names are per-material (`"Solution"`, `"Derivative"` here; an unknown name hits `DebugStop` at runtime).
- **Confusing it with `TPZMatPoisson`** — the L2 projection solves the mass matrix `(u, v)`, not the stiffness `(∇u, ∇v)`. For `-∇²u = f`, see the Poisson recipe.
- **Material on the stack** — `TPZL2Projection<STATE> mat(...); cmesh->InsertMaterialObject(&mat);` crashes when the mesh is destroyed. Always use `new`.
