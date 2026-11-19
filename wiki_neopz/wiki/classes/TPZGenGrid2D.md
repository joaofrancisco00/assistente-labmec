# TPZGenGrid2D — API card

Generated from `Pre/TPZGenGrid2D.h` — do not edit by hand.

Include: `"TPZGenGrid2D.h"` (in C++ code: `#include "TPZGenGrid2D.h"`)

Public methods (exact declarations from the header):
- `TPZGenGrid2D(const TPZVec<int> &nx, const TPZVec<REAL> &x0, const TPZVec<REAL> &x1, int numl = 1, REAL rot = 0.5)`
- `virtual ~TPZGenGrid2D()`
- `void SetData(TPZVec<int> &nx, TPZVec<REAL> &x0, TPZVec<REAL> &x1, MMeshType eltype = MMeshType::EQuadrilateral, int numl = 1, REAL rot = 0.5)`
- `void SetZigZagPattern()`
- `void SetDistortion(REAL distortion)`
- `virtual short Read(TPZGeoMesh *mesh,int matid = 1)`
- `short Read(TPZAutoPointer<TPZGeoMesh> &mesh, int matid = 1)`
- `static REAL GeometricProgression(REAL minsize, REAL size, int numdiv)`
- `void ComputeGeometricProgression(TPZVec<REAL> &minsizes, TPZVec<REAL> &progression)`
- `void SetGeometricProgression(TPZVec<REAL> &progression)`
- `virtual void SetBC(TPZGeoMesh *gr, int side, int bc)`
- `virtual void SetBC(TPZGeoMesh *gr, TPZVec<REAL> &start, TPZVec<REAL> &end, int bc)`
- `void SetBC(TPZAutoPointer<TPZGeoMesh> gr, int side, int bc)`
- `void SetBC(TPZAutoPointer<TPZGeoMesh> gr, TPZVec<REAL> &start, TPZVec<REAL> &end, int bc)`
- `void SetPointBC(TPZGeoMesh *gr, TPZVec<REAL> &x, int bc)`
- `void SetPointBC(TPZAutoPointer<TPZGeoMesh> gr, TPZVec<REAL> &x, int bc)`
- `virtual void Print( char *name = NULL, std::ostream &out = std::cout )`
- `virtual void SetElementType(MMeshType type)`
- `int64_t ElemId(int64_t iel,int64_t jel, int layer)`
- `static REAL Distance(TPZVec<REAL> &x1,TPZVec<REAL> &x2)`
- `bool ReadAndMergeGeoMesh(TPZGeoMesh * grid,TPZGeoMesh * grid2)`
- `bool ReadAndMergeGeoMesh(TPZGeoMesh* grid,TPZGeoMesh* grid2,int matid)`
- `bool MergeGeoMesh(TPZGeoMesh* grid,TPZGeoMesh* grid2,int matid = 1)`
- `void SetRefpatternElements(bool refpat)`
- `static void RotateGeomesh(TPZGeoMesh *gmesh, REAL CounterClockwiseAngle, int Axis)`
