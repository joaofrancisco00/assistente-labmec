# TPZGeoMesh — API card

Generated from `Mesh/pzgmesh.h` — do not edit by hand.

Include: `"pzgmesh.h"` (in C++ code: `#include "pzgmesh.h"`)

Public methods (exact declarations from the header):
- `TPZGeoMesh()`
- `TPZGeoMesh(const TPZGeoMesh &cp)`
- `TPZGeoMesh & operator= (const TPZGeoMesh &cp )`
- `virtual ~TPZGeoMesh()`
- `void CleanUp()`
- `void ResetConnectivities()`
- `int ClassId() const override`
- `void Read(TPZStream &buf, void *context) override`
- `void Write(TPZStream &buf, int withclassid) const override`
- `void SetNodeIdUsed(int64_t id)`
- `void SetElementIdUsed(int64_t id)`
- `int64_t CreateUniqueNodeId()`
- `int64_t CreateUniqueElementId()`
- `void SetMaxNodeId(int64_t id)`
- `void SetMaxElementId(int64_t id)`
- `int64_t NNodes() const`
- `int64_t NElements() const`
- `int64_t ReallyNEl()`
- `void SetName(const std::string &nm)`
- `std::string &Name()`
- `TPZAdmChunkVector<TPZGeoEl *> &ElementVec()`
- `TPZGeoEl * Element(int64_t iel)`
- `TPZAdmChunkVector<TPZGeoNode> &NodeVec()`
- `const TPZAdmChunkVector<TPZGeoEl *> &ElementVec() const`
- `const TPZAdmChunkVector<TPZGeoNode> &NodeVec() const`
- `REAL Area()`
- `REAL Area(int matid)`
- `REAL Area(std::set<int> &matids)`
- `void ResetReference()`
- `void RestoreReference(TPZCompMesh *cmesh)`
- `void SetReference(TPZCompMesh *ref)`
- `TPZCompMesh *Reference() const`
- `virtual void Print(std::ostream & out = std::cout) const`
- `virtual void PrintTopologicalInfo(std::ostream & out = std::cout) const`
- `TPZGeoNode* FindNode(TPZVec<REAL> &co)`
- `TPZGeoNode* FindNode(TPZVec<REAL> &co, int64_t &nodeFoundIndex)`
- `TPZGeoEl * FindElement(TPZVec<REAL> &x, TPZVec<REAL> & qsi, int64_t & InitialElIndex, int targetDim) const`
- `TPZGeoEl * FindElementCaju(TPZVec<REAL> &x, TPZVec<REAL> & qsi, int64_t & InitialElIndex, int targetDim)`
- `TPZGeoEl *FindApproxElement(TPZVec<REAL> &x, TPZVec<REAL> & qsi, int64_t & InitialElIndex, int targetDim) const`
- `TPZGeoEl * FindSubElement(TPZGeoEl * gel, TPZVec<REAL> &x, TPZVec<REAL> & qsi, int64_t & InitialElIndex) const`
- `TPZGeoEl * FindCloseElement(TPZVec<REAL> &x, int64_t & InitialElIndex, int targetDim) const`
- `void BuildConnectivityOld()`
- `void BuildConnectivity()`
- `void GetNodePtr(TPZVec<int64_t> &nos,TPZVec<TPZGeoNode *> &nodep)`
- `void GetBoundaryElements(int64_t IndexNodeFrom,int64_t IndexNodeTo,TPZStack<TPZGeoEl *> &ElementVec,TPZStack<int> &Sides)`
- `TPZGeoEl * FindElement(int64_t elid)`
- `int64_t ElementIndex(TPZGeoEl * gel)`
- `int64_t NodeIndex(TPZGeoNode * nod)`
- `virtual TPZGeoEl *CreateGeoElementMapped(MElementType type, TPZVec<int64_t>& nodeindexes, int matid, int64_t& index, int reftype = 1)`
- `virtual TPZGeoEl *CreateGeoElement(MElementType type,TPZVec<int64_t> &cornerindexes,int matid,int64_t &index, int reftype = 1)`
- `virtual TPZGeoEl *CreateGeoBlendElement(MElementType type, TPZVec<int64_t>& nodeindexes, int matid, int64_t& index)`
- `void DeleteElement(TPZGeoEl *gel, int64_t index = -1)`
- `int AddInterfaceMaterial(int leftmaterial, int rightmaterial, int interfacematerial)`
- `int InterfaceMaterial(int leftmaterial, int rightmaterial)`
- `void ClearInterfaceMaterialsMap()`
- `void SetDimension(int dim)`
- `int Dimension()`

Does NOT exist (common mistakes):
- `NodeVec().PushBack`, `NodeVec().Append`, `ElementVec().PushBack`, `AddNode`, `AddElement` do NOT exist, and `CreateUniqueNodeId()` does NOT allocate a node in `NodeVec()`.
- To add a node: `int64_t idx = gmesh->NodeVec().AllocateNewElement(); gmesh->NodeVec()[idx].Initialize(coord, *gmesh);`.
- To create an element: `int64_t elIdx = -1; gmesh->CreateGeoElement(ETriangle, nodeIndices, matId, elIdx);` (4 args; 1st arg is `MElementType` such as `ETriangle` or `EQuadrilateral` from `pzeltype.h`, NEVER `TPZTriangle::ClassId()`; 4th arg is an `int64_t` variable by reference, NEVER `-1`).
