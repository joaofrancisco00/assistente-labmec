---
type: code
status: draft
updated: 2026-07-02
confidence: high
evidence-commit: 6ffd38b12
tags:
  - neopz
  - mesh
  - approximation
---

# TPZCompMesh — computational mesh

## Responsibility
The discretization object: computational elements (`TPZCompEl`), connects (DOF bundles), materials, the block structure of the solution, and the solution vector itself. Built *over* a [[TPZGeoMesh]]; the approximation space flavor is decided by an embedded factory ([[approx-space-creators]]).

## Key files
- `Mesh/pzcmesh.h` / `.cpp` [repo]: members `TPZGeoMesh* fReference` (+ optional owning `TPZAutoPointer<TPZGeoMesh> fGMesh` — *dual raw/smart reference*, pzcmesh.h:49-54), `TPZAdmChunkVector<TPZCompEl*> fElementVec`, `TPZAdmChunkVector<TPZConnect> fConnectVec`, `std::map<int,TPZMaterial*> fMaterialVec`, `TPZBlock fSolutionBlock`, `TPZSolutionMatrix fSolution` (pzcmesh.h:59-72). Includes `pzcreateapproxspace.h` (Pre/) at pzcmesh.h:18 — Mesh↔Pre coupling.
- `Mesh/pzconnect.h` — `TPZConnect`: order, number of state vars, sequence number into the block structure, dependency matrices (hanging-node constraints), Lagrange multiplier level. Central to [[assembly]] and [[static-condensation]]. *(field list [agent]; re-verify Phase 2)*
- `Mesh/pzcompel.h` — abstract `TPZCompEl`; `Mesh/pzinterpolationspace.h` + `Mesh/pzintel.h` — interpolation-space layer (`TPZInterpolatedElement`) implementing p-orders, side connects, constraints.
- `Mesh/TPZMultiphysicsCompMesh.h` — combines several atomic cmeshes (flux, pressure, …) into one multiphysics space → [[mixed-methods]].
- `Mesh/pzsubcmesh.h` — `TPZSubCompMesh`: a cmesh that *is* a computational element of a parent mesh (substructuring / [[mhm]]).
- `Mesh/pzcondensedcompel.h`, `Mesh/pzelementgroup.h` — element grouping + static condensation wrappers → [[static-condensation]].
- `Mesh/pzelmat.h` / `TPZElementMatrixT.h` — element matrices (`ek`, `ef`) produced during [[assembly]].

## Notable design facts
- Connects (not nodes) are the DOF unit: an H(div) element has face connects + an internal connect; continuity is imposed by *sharing connects* across elements. [repo pattern; detailed verification in Phase 2/4]
- `TPZConnect` carries hanging-node dependency matrices (`TPZDepend`) — constraints are resolved at assembly time, not by modifying shape functions. *(mechanism [agent]; verify in [[refinement-hanging-nodes]] trace)*
- The mesh owns an `ApproxSpace()` (`TPZCreateApproximationSpace`) that stamps which element type gets created per geometry → [[approx-space-creators]].
- `NEquations()` reflects condensed system size vs `Solution().Rows()` full size (used by divfreebubbles `iter_elast.cpp:257-272` [repo]).

## Creating an H(div) or H1 computational mesh
To build an $H(\text{div})$ approximation space of order `pOrder` on a 2D quadrilateral `TPZGeoMesh`, call `SetDefaultOrder(pOrder)` and `SetAllCreateFunctionsHDiv()` (never `SetAllCreateFunctionsContinuous()`, which builds $H^1$), insert a `TPZNullMaterial<>(matId, dim)` (or physical material), and call `AutoBuild()`:

```cpp
#include "pzgmesh.h"
#include "TPZGeoMeshTools.h"
#include "MMeshType.h"
#include "pzcmesh.h"
#include "TPZNullMaterial.h"
#include "pzmanvector.h"

int main() {
    constexpr int dim = 2;
    constexpr int matId = 1;

    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {4, 4};
    const TPZManVector<int, 1> matIds = {matId};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, false);

    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(2);
    cmesh->SetAllCreateFunctionsHDiv();

    auto *mat = new TPZNullMaterial<>(matId, dim);
    cmesh->InsertMaterialObject(mat);
    cmesh->AutoBuild();

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Related
[[TPZGeoMesh]] · [[approx-space-creators]] · [[material-system]] · [[assembly]] · [[static-condensation]] · [[structural-matrices]] · [[persistence]]

## Open questions
- Semantics of `fSolutionBlock` vs `fBlock`(?) and `TPZSolutionMatrix` real/complex duality — Phase 2.
- Who owns materials? (`fMaterialVec` holds raw pointers; `TPZCompMesh` destructor behavior → Phase 5 ownership review.)
