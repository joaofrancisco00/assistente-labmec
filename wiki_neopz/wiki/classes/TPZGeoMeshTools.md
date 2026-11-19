# TPZGeoMeshTools — API card

Generated from `Mesh/TPZGeoMeshTools.h` — do not edit by hand.

Include: `"TPZGeoMeshTools.h"` (in C++ code: `#include "TPZGeoMeshTools.h"`)

Public methods (exact declarations from the header):
- `void DividePyramidsIntoTetra(TPZGeoMesh *gmesh)`
- `TPZGeoMesh * CreateGeoMeshOnGrid(int dim, const TPZVec<REAL>& minX, const TPZVec<REAL>& maxX, const TPZVec<int> &matids, const TPZVec<int> nDivs, MMeshType meshType, bool createBoundEls)`
- `TPZGeoMesh * CreateGeoMesh1D(const REAL minX, const REAL maxX, const int nEls, const TPZVec<int> &matids, bool createBoundEls)`
- `TPZGeoMesh * CreateGeoMeshSingleEl(const MMeshType meshType, const int matid, const bool createBoundEls, const int matidbc = -1)`
- `template<class TGEO> TPZGeoMesh * CreateGeoMeshSingleElT(const int matid, const bool createBoundEls, const int matidbc = -1)`
- `TPZGeoEl* FindElementByMatId(TPZGeoMesh* gmesh, TPZVec<REAL> &x, TPZVec<REAL> & qsi, int64_t & InitialElIndex, const std::set<int>& matids)`
- `TPZGeoEl* FindCloseElement(TPZGeoMesh* gmesh, TPZVec<REAL> &x, int64_t & InitialElIndex, const std::set<int>& matids)`

Does NOT exist (common mistakes):
- `CreateGeoMeshOnGrid` ONLY supports `dim = 2` or `dim = 3` (calling it with `dim = 1` triggers `DebugStop()` at runtime). For 1D meshes, allocate nodes with `gmesh->NodeVec().AllocateNewElement()` and create `EOned` elements with `gmesh->CreateGeoElement(EOned, nodeIndices, matId, elIndex)`.
