# Complete recipe: 2D linear elasticity with the current NeoPZ API

Canonical flow for 2D linear elasticity (plane stress or plane strain) with
Dirichlet conditions, using the **current API**. The skeleton
(`CreateGMesh` → `CreateCMesh` → `SolveProblem` → `PrintResults` — the
structure real LabMeC code uses, with an `enum` for material ids) is the
same as the 2D Poisson recipe — what changes is the material and everything
that follows from the solution being a vector.

## Choosing the material — the most common mistake

- **2D → `TPZElasticity2D`** (include `"Elasticity/TPZElasticity2D.h"` —
  with the family prefix; the basename alone does not compile)
- **3D → `TPZElasticity3D`** — DO NOT use it in 2D problems; besides the wrong
  physics, the constructor is different: `TPZElasticity3D(id, E, nu, TPZVec<STATE> &force)`.

## How to configure the material — WARNING, silent error

**Always use the full constructor**. It is the only one that initializes the
constitutive law (`fConstitutiveLaw`), which is the member that actually computes stress:

```cpp
constexpr STATE E{1000.}, nu{0.3};
constexpr STATE fx{0.}, fy{-1.};   // self-weight pointing down
constexpr int planeStress{1};      // 1 = plane stress; 0 = plane strain
auto *mat = new TPZElasticity2D(EDomain, E, nu, fx, fy, planeStress);
```

Do **not** use the 1-argument constructor with `SetElasticity`: that setter only
stores `fE_def`/`fnu_def` and **does not reach the constitutive law**. The program
compiles, runs, exits with `exit 0` and writes the VTK — but `SigmaX`/`SigmaY` come out
**zero at every point** and the displacement is wrong, without any warning.
Found by running this recipe and comparing the VTK fields.

No name-based validation catches this error: `TPZElasticity2D` and
`SetElasticity` both exist, and the code compiles without a single warning.

## Differences with respect to scalar Poisson

1. **2 state variables** (ux, uy): in the boundary condition, `val1` is
   `TPZFMatrix<STATE>(2, 2, 0.)` and `val2` has **2 entries** (`{0., 0.}`) —
   size 1 is an error.
2. **Post-processing** uses `TPZVTKGenerator` and the field names belong to
   the material — `"Displacement"` (vector), `"SigmaX"`, `"SigmaY"`,
   `"TauXY"`, `"PrincipalStress1"`, `"PrincipalStress2"`, `"MaxStress"`.
   `"Solution"`/`"Derivative"` belong to Poisson and **do not exist** here —
   an unknown name makes `TPZVTKGenerator` `DebugStop` at runtime.
3. **Body force** enters as `fx`/`fy` in the constructor itself — no need
   for `SetForcingFunction` for a constant load.

## Complete code (compilable)

```cpp
#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::ETriangular
#include "pzcmesh.h"              // TPZCompMesh
#include "Elasticity/TPZElasticity2D.h"  // TPZElasticity2D (current API — family prefix!)
#include "TPZLinearAnalysis.h"    // TPZLinearAnalysis
#include "pzskylstrmatrix.h"      // TPZSkylineStructMatrix
#include "pzstepsolver.h"         // TPZStepSolver
#include "pzmanvector.h"          // TPZManVector
#include "pzfmatrix.h"            // TPZFMatrix
#include "pzvec.h"                // TPZVec
#include "TPZVTKGenerator.h"      // TPZVTKGenerator (post-processing to .vtk)
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
    PrintResults(cmesh, "elasticity2d");
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

    // 2D material — ALWAYS on the heap (the mesh takes ownership).
    // Full constructor: it is the only one that initializes the constitutive law.
    // With (id) + SetElasticity, SigmaX/SigmaY come out ZERO with no error at all.
    constexpr STATE E{1000.}, nu{0.3};
    constexpr STATE fx{0.}, fy{-1.};  // self-weight
    constexpr int planeStress{1};     // 1 = plane stress; 0 = plane strain
    auto *mat = new TPZElasticity2D(EDomain, E, nu, fx, fy, planeStress);
    cmesh->InsertMaterialObject(mat);

    // Clamped on the whole boundary (Dirichlet, type 0) — val2 with 2 entries
    TPZFMatrix<STATE> val1(2, 2, 0.);
    TPZManVector<STATE, 2> val2 = {0., 0.};
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
    TPZVec<std::string> fields = {"Displacement", "SigmaX", "SigmaY", "TauXY"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
```

## Common mistakes

- **`TPZElasticity3D` in a 2D problem** — the class exists and the name compiles,
  but it is the wrong physics and the constructor is different. In 2D, always `TPZElasticity2D`.
- **`TPZElasticity2D(id, dim)`** — this constructor does NOT exist.
- **`TPZElasticity2D(id)` + `SetElasticity(E, nu)`** — compiles and runs, but
  `SetElasticity` does not initialize the constitutive law: `SigmaX`/`SigmaY` come out
  zero at every point and the displacement is wrong, without any warning.
  Use the full constructor `(id, E, nu, fx, fy, planestress)`.
- **`#include "TPZElasticity2D.h"` without the `Elasticity/` prefix** — does not compile.
- **`val2` with 1 entry** in `CreateBC` — 2D elasticity has 2 state
  variables; `val2 = {0., 0.}`.
- **`DefineGraphMesh`/`PostProcess`** — legacy path: use `TPZVTKGenerator`.
  And the field names are per-material: `"Solution"`/`"Derivative"` are
  Poisson names — here they are `"Displacement"`, `"SigmaX"`, etc.
- **`TPZMatElasticity2D`** — old name, no longer exists; today it is
  `TPZElasticity2D`.
- **Material on the stack / forgetting `AutoBuild` / `Solve` without `Assemble`** —
  same pitfalls as the Poisson recipe.
