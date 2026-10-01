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

1. **Geometric mesh** — `TPZGeoMeshTools::CreateGeoMeshOnGrid(dim, minX, maxX, matIds, nDivs, meshType, createBoundEls)`.
   - `minX`/`maxX` **always** with 3 coordinates, even in 2D.
   - `nDivs` with size equal to `dim`.
   - `matIds` needs `dim*2 + 1` ids when `createBoundEls=true` (in 2D: 1 for the domain + 4 for the boundaries). Passing a single id hits `DebugStop`.
2. **Computational mesh** — `TPZCompMesh` + `SetDimModel` + `SetDefaultOrder` + `SetAllCreateFunctionsContinuous()` (continuous H1).
3. **Material** — `TPZMatPoisson<STATE>` (include `"Poisson/TPZMatPoisson.h"` — with the family prefix!). Always created with `new`: the mesh takes ownership of the pointer.
4. **Source term** — `SetForcingFunction(lambda, pOrder)` with `std::function<void(const TPZVec<REAL>&, TPZVec<STATE>&)>`.
5. **Boundary condition** — `mat->CreateBC(mat, matIdBoundary, type, val1, val2)` and insert the result into the mesh. Types: `0` = Dirichlet, `1` = Neumann, `2` = Robin.
6. **`cmesh->AutoBuild()`** — without it the computational mesh stays empty.
7. **Analysis** — `TPZLinearAnalysis` + `TPZSkylineStructMatrix<STATE>` + `TPZStepSolver<STATE>::SetDirect(ECholesky)`. Call `Assemble()` **before** `Solve()` — `Solve()` does not assemble the system by itself.
8. **Post-processing** — `DefineGraphMesh(dim, {"Solution"}, {"Derivative"}, "output.vtk")` + `PostProcess(resolution, dim)`. These are the real variable names of `TPZMatPoisson`.

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

    // 2. Computational mesh
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. Material (on the heap — the mesh takes ownership)
    auto *mat = new TPZMatPoisson<STATE>(matIdDomain, dim);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // 4. Homogeneous Dirichlet boundary condition (type 0)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
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

    // 7. Post-processing (VTK)
    const TPZManVector<std::string, 1> scalnames = {"Solution"};
    const TPZManVector<std::string, 1> vecnames = {"Derivative"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "poisson2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Common mistakes (old API and pitfalls)

- **`TPZMatLaplacian` no longer exists** — it was replaced by `TPZMatPoisson` in the material refactoring. For mixed/flow formulations, see `TPZDarcyFlow` and `TPZMixedDarcyFlow`.
- **`TPZDummyFunction` is the old API** — the current API uses `std::function` directly in `SetForcingFunction`/`SetExactSol`. Do not mix the two.
- **Material on the stack** — `TPZMatPoisson<STATE> material(...); cmesh->InsertMaterialObject(&material);` crashes when the mesh is destroyed. Always use `new`.
- **`matIds` with the wrong size** in `CreateGeoMeshOnGrid` — it needs `dim*2 + 1` ids with `createBoundEls=true`.
- **Forgetting `AutoBuild()`** — the computational mesh stays empty and the analysis has nothing to assemble.
- **Calling `Solve()` without `Assemble()`** — the system is never assembled.
- **`#include "NeoPZ.h"`** — there is no single header in NeoPZ; each class has its own.
- **`#include "TPZMatPoisson.h"` without the `Poisson/` prefix** — does not compile;
  the new-API materials live in subfolders of `Material/` and the include carries
  the family name.
