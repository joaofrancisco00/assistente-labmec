// manual_geomesh.cpp — Reference solution: MANUAL construction of a geometric
// mesh with triangular and quadrilateral elements.
//
// Teaches the canonical NeoPZ pattern to create nodes and elements without the
// helpers (TPZGeoMeshTools::CreateGeoMeshOnGrid, TPZGmshReader, etc.).
// Use this pattern when you need full control over the mesh topology.
//
// Flow:
//   1. new TPZGeoMesh()  →  SetDimension
//   2. NodeVec().AllocateNewElement()  →  [i].Initialize(coords, *gmesh)
//   3. CreateGeoElement(type, nodeindices, matid, index)
//   4. BuildConnectivity()
//   5. TPZGeoElBC to create boundary elements

#include "pzgmesh.h"        // TPZGeoMesh
#include "pzgnode.h"        // TPZGeoNode
#include "pzmanvector.h"    // TPZManVector
#include "pzgeoel.h"        // TPZGeoEl
#include "pzgeoelbc.h"      // TPZGeoElBC
#include "pzeltype.h"       // ETriangle, EQuadrilateral, EOned (MElementType)
#include <iostream>

int main() {
    // ── 1. Create the geometric mesh and set the dimension ────────────────
    TPZGeoMesh *gmesh = new TPZGeoMesh();
    gmesh->SetDimension(2);

    // ── 2. Allocate and initialize the nodes ─────────────────────────────
    // Canonical pattern: AllocateNewElement() reserves space in the ChunkVector
    // and returns the index; Initialize() fills in the coordinates and
    // registers the node.
    // DO NOT call NodeVec().Resize(nNodes) before: AllocateNewElement() grows
    // the vector by itself, so Resize + AllocateNewElement creates 2*nNodes nodes
    // and the elements end up pointing to the uninitialized ones.
    //
    // Simple mesh: 4 nodes, 1 quadrilateral + 1 triangle sharing an edge.
    //
    //  3───2
    //  │ \ │
    //  0───1
    //
    //  Element 1 (EQuadrilateral): nodes 0-1-2-3
    //  Element 2 (ETriangle):      nodes 1-2-3   ← triangle in the upper corner

    const int nNodes = 4;
    const TPZManVector<TPZManVector<REAL, 3>, 4> coords = {
        {0., 0., 0.},  // node 0
        {1., 0., 0.},  // node 1
        {1., 1., 0.},  // node 2
        {0., 1., 0.},  // node 3
    };

    for (int i = 0; i < nNodes; i++) {
        auto newindex = gmesh->NodeVec().AllocateNewElement();
        gmesh->NodeVec()[newindex].Initialize(coords[i], *gmesh);
    }

    // ── 3. Create the geometric elements ─────────────────────────────────
    constexpr int matIdDom{1};
    constexpr int matIdBC{-1};
    int64_t index{-1};

    // Quadrilateral: 4 nodes in counter-clockwise order
    TPZManVector<int64_t, 4> quadNodes = {0, 1, 2, 3};
    gmesh->CreateGeoElement(EQuadrilateral, quadNodes, matIdDom, index);

    // Triangle: 3 nodes in counter-clockwise order
    // (shares edge 1-2 with the quadrilateral above)
    TPZManVector<int64_t, 3> triNodes = {1, 2, 3};
    gmesh->CreateGeoElement(ETriangle, triNodes, matIdDom, index);

    // ── 4. Build the connectivity ────────────────────────────────────────
    // MANDATORY after inserting all elements — without it the neighbors are
    // null and the numerical integration does not work.
    gmesh->BuildConnectivity();

    // ── 5. Create boundary elements via TPZGeoElBC ───────────────────────
    // TPZGeoElBC creates a 1D boundary element on a side of an existing
    // element. The 1D sides of a quadrilateral (4 nodes) are 4, 5, 6 and 7.
    // The 1D sides of a triangle (3 nodes) are 3, 4 and 5.
    {
        TPZGeoEl *quad = gmesh->Element(0);
        // 1D sides of the quadrilateral: 4=edge 0-1, 5=1-2, 6=2-3, 7=3-0
        TPZGeoElBC(quad, 4, matIdBC);  // bottom boundary
        TPZGeoElBC(quad, 7, matIdBC);  // left boundary
    }
    {
        TPZGeoEl *tri = gmesh->Element(1);
        // 1D sides of the triangle: 3=edge 1-2, 4=2-3, 5=3-1
        TPZGeoElBC(tri, 5, matIdBC);   // diagonal boundary
    }

    // ── 6. Simple check ──────────────────────────────────────────────────
    std::cout << "Nodes:    " << gmesh->NNodes()    << std::endl;
    std::cout << "Elements: " << gmesh->NElements() << std::endl;

    delete gmesh;
    return 0;
}
