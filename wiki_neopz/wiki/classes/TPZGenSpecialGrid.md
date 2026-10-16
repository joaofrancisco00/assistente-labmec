# TPZGenSpecialGrid — API card

Generated from `Pre/TPZGenSpecialGrid.h` — do not edit by hand.

Include: `"Pre/TPZGenSpecialGrid.h"` (no código: #include "Pre/TPZGenSpecialGrid.h")

Public methods (exact declarations from the header):
- `static TPZGeoMesh *GeneratePolygonalSphereFromOctahedron(TPZVec<REAL> &center,REAL radius, int nUniformRefs)`
- `static TPZGeoMesh *GeneratePolygonalSphereFromOctahedron(TPZVec<REAL> &center,REAL radius, REAL tol)`
- `static void UniformRefinement(const int nUniformRefs, TPZGeoMesh *gmesh, const int dimelfordivision,bool allmaterial=true, const int matidtodivided=0)`
- `static TPZGeoMesh *CreateGeoMesh2D_Circle(int nDiv)`
- `static TPZGeoMesh *CreateArcMesh(REAL inner, REAL outer, REAL alpha0 = 0, REAL alpha1 = M_PI_2)`
- `static TPZGeoMesh *CreateGeoMesh3D_DividedSphere(int nDiv)`
