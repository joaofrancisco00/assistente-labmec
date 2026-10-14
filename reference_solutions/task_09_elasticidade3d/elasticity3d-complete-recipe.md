# Complete recipe: 3D linear elasticity with the current NeoPZ API

Canonical flow for 3D linear elasticity with Dirichlet conditions, using the
**current API**. The skeleton (mesh → cmesh → material → boundary → AutoBuild →
Assemble → Solve) is the same as the 2D elasticity recipe — what changes is the
material, the size of the boundary-condition values and the post-processing
variable names.

## Choosing the material

- **3D → `TPZElasticity3D`** (include `"Elasticity/TPZElasticity3D.h"` —
  with the family prefix; the basename alone does not compile)
- **2D → `TPZElasticity2D`** — DO NOT use it in 3D problems; besides the wrong
  physics, the constructor is different:
  `TPZElasticity2D(id, E, nu, fx, fy, planestress)`.

## How to configure the material

**Always use the full constructor**. In 3D it takes the body force as a
3-entry `TPZVec<STATE>`:

```cpp
constexpr STATE E{1000.}, nu{0.3};
TPZManVector<STATE, 3> force = {0., 0., -1.};  // self-weight along -z
auto *mat = new TPZElasticity3D(matIdDomain, E, nu, force);
```

The 1-argument constructor `TPZElasticity3D(id)` + setters is **not** the
recommended path — pass everything to the constructor. There is **no**
`planeStress`/`fx`/`fy` argument in `TPZElasticity3D`: those belong to
`TPZElasticity2D` and writing `TPZElasticity3D(id, E, nu, planeStress)` does
not compile.

## Differences with respect to 2D elasticity

1. **3 state variables** (ux, uy, uz): in the boundary condition, `val1` is
   `TPZFMatrix<STATE>(3, 3, 0.)` and `val2` has **3 entries**
   (`{0., 0., 0.}`) — the 2D sizes (2x2 / 2 entries) are an error here.
2. **Geometric mesh**: `dim = 3`, `nDivs` has 3 entries, `matIds` has
   `dim*2 + 1 = 7` entries (1 domain + 6 faces with `createBoundEls=true`),
   and `MMeshType::EHexahedral` for a structured grid.
3. **Post-processing**: the variable names belong to the material —
   `"Displacement"` (vector), `"DisplacementX"`, `"DisplacementY"`,
   `"DisplacementZ"`, `"StressX"`, `"StressY"`, `"StressZ"`, `"VonMises"`,
   `"PrincipalStress"`, `"Stress"`, `"Strain"`. `"SigmaY"`/`"TauXY"` are
   `TPZElasticity2D` names and **do not exist** here.
4. **Problem size**: 3D systems grow fast — start with `pOrder = 1` and a
   coarse grid (e.g. 4x4x4) before refining.

## Complete code (compilable)

```cpp
#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::EHexahedral
#include "pzcmesh.h"              // TPZCompMesh
#include "Elasticity/TPZElasticity3D.h"  // TPZElasticity3D (current API — family prefix!)
#include "TPZLinearAnalysis.h"    // TPZLinearAnalysis
#include "pzskylstrmatrix.h"      // TPZSkylineStructMatrix
#include "pzstepsolver.h"         // TPZStepSolver
#include "pzmanvector.h"          // TPZManVector
#include "pzfmatrix.h"            // TPZFMatrix

int main() {
    // 1. Geometric mesh — unit cube, hexahedra
    constexpr int dim{3};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 1.};
    const TPZManVector<int, 3> nDivs = {4, 4, 4};   // size = dim
    constexpr int matIdDomain{1};
    constexpr int matIdBoundary{-1};
    // dim*2 + 1 = 7 ids in 3D (1 domain + 6 faces) when createBoundEls=true
    const TPZManVector<int, 7> matIds = {matIdDomain, matIdBoundary, matIdBoundary,
                                         matIdBoundary, matIdBoundary, matIdBoundary,
                                         matIdBoundary};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EHexahedral, true);

    // 2. Computational mesh
    constexpr int pOrder{1};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. 3D material (on the heap — the mesh takes ownership)
    // Constructor is (id, E, nu, TPZVec<STATE> &force) — the body force is a
    // 3-entry vector; there is NO fx/fy or plane-stress flag — that belongs
    // to the 2D material.
    constexpr STATE E{1000.}, nu{0.3};
    TPZManVector<STATE, 3> force = {0., 0., -1.};  // self-weight along -z
    auto *mat = new TPZElasticity3D(matIdDomain, E, nu, force);
    cmesh->InsertMaterialObject(mat);

    // 4. Clamped on the whole boundary (Dirichlet, type 0) — 3 state variables:
    //    val1 is 3x3 and val2 has 3 entries
    TPZFMatrix<STATE> val1(3, 3, 0.);
    TPZManVector<STATE, 3> val2 = {0., 0., 0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // 5. Build the mesh
    cmesh->AutoBuild();

    // 6. Assemble and solve
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 7. Post-processing (VTK) — TPZElasticity3D variable names
    const TPZManVector<std::string, 2> scalnames = {"StressX", "VonMises"};
    const TPZManVector<std::string, 1> vecnames = {"Displacement"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "elasticity3d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Common mistakes

- **`TPZElasticity3D(id, E, nu, planeStress)`** — this is the 2D signature
  transplanted to 3D; it does NOT compile. The 3D constructor takes a
  3-entry force vector: `TPZElasticity3D(id, E, nu, force)`.
- **`val1(1, 1)` or `val2` with 1 or 2 entries** in `CreateBC` — 3D
  elasticity has 3 state variables; `val1(3, 3)` and `val2 = {0., 0., 0.}`.
- **`TPZElasticity2D` in a 3D problem** — wrong physics and a constructor
  that does not match; in 3D, always `TPZElasticity3D`.
- **`#include "TPZElasticity3D.h"` without the `Elasticity/` prefix** —
  does not compile.
- **Only 5 `matIds` or 2 `nDivs` copied from the 2D recipe** — in 3D it is
  7 material ids and 3 divisions.
- **`"SigmaY"`/`"TauXY"`/`"Solution"` in `DefineGraphMesh`** — those are 2D
  elasticity / Poisson names; here it is `"StressX"`, `"VonMises"`,
  `"Displacement"` etc.
- **Material on the stack / forgetting `AutoBuild` / `Solve` without `Assemble`** —
  same pitfalls as the Poisson recipe.
