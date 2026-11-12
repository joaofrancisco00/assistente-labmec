---
type: code
status: draft
updated: 2026-07-02
confidence: high
evidence-commit: 6ffd38b12
tags:
  - neopz
  - mesh
  - geometry
---

# TPZGeoMesh — geometric mesh

## Responsibility
Container for the *geometry and topology* of the discretization: geometric elements, nodes, and elementwise/nodal BC identifiers — no degrees of freedom (those live in [[TPZCompMesh]]). Holds the refinement genealogy (father/son element trees) that underpins [[refinement-hanging-nodes]].

## Key files
- `Mesh/pzgmesh.h` / `.cpp` — `#include "pzgmesh.h"` declares `TPZGeoMesh`: `NodeVec()` (`TPZAdmChunkVector<TPZGeoNode>`), `ElementVec()` (`TPZAdmChunkVector<TPZGeoEl*>`), `SetDimension(dim)`, `CreateGeoElement(...)`, and `BuildConnectivity()`.
- `Mesh/pzgnode.h` — `#include "pzgnode.h"` declares `TPZGeoNode` (`Initialize(coord, mesh)`, `SetCoord(coord)`).
- `Mesh/pzeltype.h` — `#include "pzeltype.h"` defines `MElementType` (`ETriangle`, `EQuadrilateral`, `EOned`, `ETetraedro`, `ECube`, `EPrisma`, `EPiramide`, `EPoint`).

## Canonical manual node & element creation
Never use `NodeVec().PushBack`, `NodeVec().Append`, `ElementVec().PushBack`, `SetNodes` (none of them exist), or `CreateUniqueNodeId()` without allocating space in `NodeVec()`. Always allocate nodes via `NodeVec().AllocateNewElement()` + `Initialize(coord, *gmesh)` (or `SetCoord`), and create elements via `CreateGeoElement(MElementType, nodeIndices, matId, elIndex)` (4 arguments, where `elIndex` is an `int64_t` output variable):

```cpp
#include "pzgmesh.h"
#include "pzgnode.h"
#include "pzmanvector.h"
#include "pzeltype.h"

int main() {
    TPZGeoMesh *gmesh = new TPZGeoMesh();
    gmesh->SetDimension(2);

    const REAL coords[4][3] = {
        {0., 0., 0.}, {1., 0., 0.}, {1., 1., 0.}, {0., 1., 0.}
    };
    TPZManVector<int64_t, 4> nodeIndexes(4);
    for (int i = 0; i < 4; i++) {
        TPZManVector<REAL, 3> coord = {coords[i][0], coords[i][1], coords[i][2]};
        int64_t idx = gmesh->NodeVec().AllocateNewElement();
        gmesh->NodeVec()[idx].Initialize(coord, *gmesh);
        nodeIndexes[i] = idx;
    }

    int64_t elIndex = -1;
    // Use EQuadrilateral (4 nodes) or ETriangle (3 nodes)
    gmesh->CreateGeoElement(EQuadrilateral, nodeIndexes, /*matId=*/1, elIndex);
    gmesh->BuildConnectivity();

    delete gmesh;
    return 0;
}
```

## Notable design facts [repo]
- `GMESHNOMATERIAL -9999` sentinel for "no material" (pzgmesh.h:24).
- Interface-material map keyed by material-id pairs (pzgmesh.h:72-75) — supports DG/interface constructions.
- Mutual raw-pointer reference with the computational mesh (`fReference` both ways; pzcmesh.h:49) — the "reference" mechanism used to associate geo↔comp elements. Lifetime/ownership implications → Phase 5.
- Storage is chunked (`TPZAdmChunkVector`) so element/node pointers survive vector growth; free slots are recycled.

## Related
[[TPZCompMesh]] · [[geometric-mappings]] · [[refinement-hanging-nodes]] · [[topology-module]] · [[mesh-io-generators]]

## Open questions
- Exact semantics of `ResetReference/LoadReferences` in multi-cmesh (multiphysics) workflows — needed for the Phase 2 flow traces.
- Ownership: who deletes `TPZGeoEl*` — mesh destructor? (Phase 5 lifetime review.)
