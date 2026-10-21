# Complete recipe: 2D mixed Darcy with TPZHDivApproxCreator

Same problem as the mixed-Darcy recipe (flux + pressure on `[0,1]²`), but the
three-mesh architecture is built by the **library-side creator**
`TPZHDivApproxCreator` instead of by hand. This is how the 2026 LabMeC codes
(`Iterative-Saddle_Point`, `ErrorEstimation`, `TestHDivApproxSpaceCreator`)
do it — prefer this form when the request mentions "approximation space
creator" or when hand-wiring the atomic meshes is unnecessary.

## Step by step

1. **Geometric mesh** — same as the manual mixed recipe:
   `TPZGeoMeshTools::CreateGeoMeshOnGrid` with `dim*2 + 1` matIds.
2. **Creator** — `TPZHDivApproxCreator hdivCreator(gmesh)` (include
   `"TPZHDivApproxCreator.h"`), then:
   - `SetProbType(ProblemType::EDarcy)` — the enum lives in
     `TPZApproxCreator.h` (`ENone, EElastic, EDarcy, EStokes`).
   - `HdivFamily() = HDivFamily::EHDivStandard` — reference to the member;
     the enum (`EHDivStandard, EHDivConstant, EHDivKernel, EHDivOptimized`)
     lives in `TPZEnumApproxFamily.h`.
   - `SetDefaultOrder(pOrder)` and `SetShouldCondense(false)` — keep all
     equations visible in an intro recipe.
3. **Material and BC** — `new TPZMixedDarcyFlow(EDomain, dim)` +
   `SetConstantPermeability(1.)` + `SetForcingFunction(lambda, pOrder)`, then
   `hdivCreator.InsertMaterialObject(mat)`. The BC goes into the **creator**
   too (`InsertMaterialObject(bnd)`), not into a mesh. In the mixed
   formulation `type 0` imposes **pressure**.
4. **`hdivCreator.CreateApproximationSpace()`** — builds the flux (H(div)),
   pressure (L2) and multiphysics meshes and returns the
   `TPZMultiphysicsCompMesh *`. No `AutoBuild()` and no
   `BuildMultiphysicsSpace` calls anywhere.
5. **Analysis** — `TPZLinearAnalysis` on the multiphysics mesh +
   `SetNumThreads` on the structural matrix + `ELDLt` (saddle point —
   `ECholesky` fails).
6. **Post-processing** — `TPZVTKGenerator` on the multiphysics `cmesh` with
   the real `TPZMixedDarcyFlow` names: `"Pressure"`, `"Flux"`, `"DivFlux"`.
7. **Memory** — `~TPZMultiphysicsCompMesh` does NOT delete the atomic meshes
   in `MeshVector()`: copy the vector, `delete cmesh`, then `delete` each
   atomic mesh.

## Complete code (compilable)

```cpp
#include "pzgmesh.h"                  // TPZGeoMesh
#include "TPZGeoMeshTools.h"          // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"                // MMeshType::EQuadrilateral
#include "pzcmesh.h"                  // TPZCompMesh
#include "TPZMultiphysicsCompMesh.h"  // TPZMultiphysicsCompMesh
#include "TPZHDivApproxCreator.h"     // TPZHDivApproxCreator
#include "TPZEnumApproxFamily.h"      // HDivFamily::EHDivStandard
#include "DarcyFlow/TPZMixedDarcyFlow.h"  // TPZMixedDarcyFlow (family prefix!)
#include "TPZLinearAnalysis.h"        // TPZLinearAnalysis
#include "pzskylstrmatrix.h"          // TPZSkylineStructMatrix
#include "pzstepsolver.h"             // TPZStepSolver
#include "pzmanvector.h"              // TPZManVector
#include "pzfmatrix.h"                // TPZFMatrix
#include "pzvec.h"                    // TPZVec
#include "TPZVTKGenerator.h"          // TPZVTKGenerator (post-processing to .vtk)
#include <string>
#include <iostream>

enum EMatid { ENone, EDomain, EBC };   // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZMultiphysicsCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main() {
    constexpr int pOrder{1};
    TPZGeoMesh *gmesh = CreateGMesh(8);
    TPZMultiphysicsCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    std::cout << "NEquations: " << cmesh->NEquations() << '\n';

    TPZLinearAnalysis an(cmesh);
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "darcy_misto_hdivcreator");

    // The atomic meshes built by the creator live in MeshVector() and are
    // NOT deleted by ~TPZMultiphysicsCompMesh — delete them explicitly
    const TPZVec<TPZCompMesh *> atomics = cmesh->MeshVector();
    delete cmesh;
    for (auto *m : atomics) delete m;
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
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral,
        /*createBoundEls=*/true);
}

// ── Computational meshes — all three built by the creator ────────────────
TPZMultiphysicsCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    const int dim = gmesh->Dimension();

    TPZHDivApproxCreator hdivCreator(gmesh);
    hdivCreator.SetProbType(ProblemType::EDarcy);       // TPZApproxCreator::SetProbType
    hdivCreator.HdivFamily() = HDivFamily::EHDivStandard;
    hdivCreator.SetDefaultOrder(pOrder);
    hdivCreator.SetShouldCondense(false);  // keep all equations visible in this intro recipe

    // Material — ALWAYS on the heap (the creator transfers it to the mesh)
    auto *mat = new TPZMixedDarcyFlow(EDomain, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f = 1
        },
        pOrder);
    hdivCreator.InsertMaterialObject(mat);

    // In the mixed formulation type 0 imposes PRESSURE (different roles than H1!)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    TPZBndCondT<STATE> *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    hdivCreator.InsertMaterialObject(bnd);

    // Builds the flux (H(div)) + pressure (L2) + multiphysics meshes
    return hdivCreator.CreateApproximationSpace();
}

// ── Assemble and solve ────────────────────────────────────────────────────
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh) {
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    strmat.SetNumThreads(nThreads);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);  // saddle point — NEVER ECholesky
    an.SetSolver(solver);
    an.Assemble();  // Solve does NOT assemble
    an.Solve();
}

// ── Post-processing (VTK for Paraview) — real TPZMixedDarcyFlow names ─────
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Pressure", "Flux"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
```

## Common mistakes

- **Mixing the creator with the manual architecture** — do not create
  `TPZNullMaterial` atomic meshes, `SetAllCreateFunctionsHDiv()` or
  `BuildMultiphysicsSpace` when using `TPZHDivApproxCreator`: the creator
  does all of it. See `task_05` for the manual path.
- **Inserting the BC into a mesh** — with the creator the BC goes to
  `hdivCreator.InsertMaterialObject(bnd)`, before
  `CreateApproximationSpace()`.
- **`ECholesky` in the solver** — the mixed system is a saddle point; use
  `ELDLt` (or `ELU`).
- **`TPZHybridDarcyFlow` or `TPZDarcyFlow` as the material** — the creator
  path still uses `TPZMixedDarcyFlow` for the flux+pressure formulation.
- **Double-deleting or leaking the atomic meshes** — `delete cmesh` does
  not free `cmesh->MeshVector()` entries; copy the vector and delete them
  after deleting the multiphysics mesh.
- **`SetShouldCondense(true)` for a first run** — condensation hides the
  interface equations; keep it `false` until the plain solve works.
- **`#include "TPZMixedDarcyFlow.h"` without the `DarcyFlow/` prefix** —
  does not compile.
