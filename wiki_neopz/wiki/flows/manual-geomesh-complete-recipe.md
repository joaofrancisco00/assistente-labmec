# Recipe: Manual Construction of a Geometric Mesh (TPZGeoMesh)

## When to use this pattern

Use **manual** mesh construction when you need **full control** over the
topology: irregular geometries, single-element meshes for testing, hybrid meshes, or
when none of the automatic generation tools fits.

For regular structured meshes prefer `TPZGeoMeshTools::CreateGeoMeshOnGrid`;
for external meshes use `TPZGmshReader`.

---

## Required headers

```cpp
#include "pzgmesh.h"      // TPZGeoMesh
#include "pzgnode.h"      // TPZGeoNode
#include "pzmanvector.h"  // TPZManVector
#include "pzgeoel.h"      // TPZGeoEl
#include "pzgeoelbc.h"    // TPZGeoElBC
#include "pzeltype.h"      // ETriangle, EQuadrilateral, EOned, ETetraedro, …
```

---

## Step by step

### 1. Create the mesh and set the dimension

```cpp
TPZGeoMesh *gmesh = new TPZGeoMesh();
gmesh->SetDimension(2);   // 1, 2 or 3
```

### 2. Allocate and initialize the nodes

> **NEVER** instantiate `TPZGeoNode` directly and try to push it with `PushBack` —
> `TPZAdmChunkVector` has no `PushBack`. The correct pattern is:

```cpp
TPZManVector<REAL, 3> coord(3, 0.);
coord[0] = x;  coord[1] = y;  coord[2] = z;

auto idx = gmesh->NodeVec().AllocateNewElement(); // returns int64_t
gmesh->NodeVec()[idx].Initialize(coord, *gmesh);  // registers the node
```

`Initialize(coord, mesh)` automatically generates a unique id and binds the node to the mesh.

> **Do NOT call `NodeVec().Resize(nNodes)` before `AllocateNewElement()`.** `AllocateNewElement()` grows the vector by itself (it calls `Resize(NElements() + 1)`), so `Resize` + `AllocateNewElement` creates `2*nNodes` nodes: the initialized ones get indices `nNodes..2*nNodes-1`, and elements built with indices `0..nNodes-1` point to **uninitialized** nodes. It compiles and runs without any error.

#### Example: 4 nodes of a unit square

```cpp
const int nNodes = 4;

const TPZManVector<TPZManVector<REAL,3>, 4> coords = {
    {0., 0., 0.},   // node 0
    {1., 0., 0.},   // node 1
    {1., 1., 0.},   // node 2
    {0., 1., 0.},   // node 3
};

for (int i = 0; i < nNodes; i++) {
    auto newindex = gmesh->NodeVec().AllocateNewElement();
    gmesh->NodeVec()[newindex].Initialize(coords[i], *gmesh);
}
```

### 3. Create the geometric elements

Use `gmesh->CreateGeoElement(type, nodeIndices, matId, index)`:

| Type           | NeoPZ enum        | Nodes |
|----------------|-------------------|-------|
| Triangle       | `ETriangle`       | 3     |
| Quadrilateral  | `EQuadrilateral`  | 4     |
| 1D segment     | `EOned`           | 2     |
| Tetrahedron    | `ETetraedro`      | 4     |
| Prism          | `EPrisma`         | 6     |
| Cube           | `ECube`           | 8     |
| Point          | `EPoint`          | 1     |

```cpp
int64_t index{-1};  // filled in by the function

// Quadrilateral (nodes 0-1-2-3, counter-clockwise)
TPZManVector<int64_t, 4> quadNodes = {0, 1, 2, 3};
gmesh->CreateGeoElement(EQuadrilateral, quadNodes, /*matid=*/1, index);

// Triangle (nodes 1-2-3, counter-clockwise)
TPZManVector<int64_t, 3> triNodes = {1, 2, 3};
gmesh->CreateGeoElement(ETriangle, triNodes, /*matid=*/1, index);
```

> **Warning — element type:** The first argument of `CreateGeoElement` is
> always a value of the `MElementType` enum (e.g. `ETriangle`, `EQuadrilateral`,
> `EOned`, `ETetraedro`). **Never** use:
> - `new TPZTriangle` — it creates the pure topology, not a mesh element
> - `TPZTriangle::ClassId()` — it returns the serialization id, not the geometric type
> - `TPZTriangle::Type()` — correct only in a template context; prefer the enum directly
>
> The `ETriangle` enum is already available when including `pzeltype.h` (or indirectly
> via `pzgmesh.h`).

### 4. Build the connectivity

```cpp
// MANDATORY after inserting all elements.
// Without it, the neighbors are null and the numerical integration fails.
gmesh->BuildConnectivity();
```

### 5. Create boundary elements

`TPZGeoElBC` creates a child element on a `side` of a parent element and
registers it automatically in the mesh:

```cpp
TPZGeoEl *quad = gmesh->Element(0);
// 1D sides of a 4-node quadrilateral: side 4=edge 0-1, 5=1-2, 6=2-3, 7=3-0
TPZGeoElBC(quad, 4, /*matIdBC=*/-1);  // bottom boundary
TPZGeoElBC(quad, 7, /*matIdBC=*/-1);  // left boundary

TPZGeoEl *tri = gmesh->Element(1);
// 1D sides of a 3-node triangle: side 3=1-2, 4=2-3, 5=3-1
TPZGeoElBC(tri, 5, /*matIdBC=*/-1);
```

---

## Minimal complete example

```cpp
#include "pzgmesh.h"
#include "pzgnode.h"
#include "pzmanvector.h"
#include "pzgeoel.h"
#include "pzgeoelbc.h"
#include "pzeltype.h"

int main() {
    TPZGeoMesh *gmesh = new TPZGeoMesh();
    gmesh->SetDimension(2);

    // Nodes
    const int nNodes = 4;
    const TPZManVector<TPZManVector<REAL,3>,4> coords = {
        {0.,0.,0.}, {1.,0.,0.}, {1.,1.,0.}, {0.,1.,0.}
    };
    for (int i = 0; i < nNodes; i++) {
        auto idx = gmesh->NodeVec().AllocateNewElement();
        gmesh->NodeVec()[idx].Initialize(coords[i], *gmesh);
    }

    // Elements
    int64_t index{-1};
    TPZManVector<int64_t,4> quadNodes = {0,1,2,3};
    gmesh->CreateGeoElement(EQuadrilateral, quadNodes, 1, index);

    TPZManVector<int64_t,3> triNodes = {1,2,3};
    gmesh->CreateGeoElement(ETriangle, triNodes, 1, index);

    gmesh->BuildConnectivity();

    // Boundary
    TPZGeoElBC(gmesh->Element(0), 4, -1);  // edge 0-1

    delete gmesh;
    return 0;
}
```

---

## Common pitfalls

| Error                                           | Cause                                                                             | Fix                                                         |
|-------------------------------------------------|-----------------------------------------------------------------------------------|-------------------------------------------------------------|
| `TPZAdmChunkVector` has no `PushBack`           | Trying to use `NodeVec().PushBack()`                                              | Use `AllocateNewElement()` + `Initialize()`                 |
| `TPZTriangle` not declared in scope             | Included `tpztriangle.h` expecting a mesh element class                           | Use `ETriangle` (enum) in `CreateGeoElement`                |
| `no matching function` in `CreateGeoElement`    | Passed `TPZTriangle::ClassId()` (serialization int) as the element type           | Use the enum directly: `ETriangle`, `EQuadrilateral`, etc.  |
| Null neighbors at runtime                       | Forgot `BuildConnectivity()`                                                      | Always call it after all `CreateGeoElement` calls           |
| Elements on nodes with zero/garbage coordinates | `NodeVec().Resize(n)` before `AllocateNewElement()` (creates 2n nodes)            | Use only `AllocateNewElement()` + `Initialize()`            |
| Node with wrong coordinates                     | Used `SetCoord` instead of `Initialize` (does not bind the node to the mesh)      | Always use `Initialize(coord, *gmesh)` for new nodes        |
