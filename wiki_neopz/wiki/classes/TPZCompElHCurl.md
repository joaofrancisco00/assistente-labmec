# TPZCompElHCurl — API card

Generated from `Mesh/TPZCompElHCurl.h` — do not edit by hand.

Include: `"TPZCompElHCurl.h"` (in C++ code: `#include "TPZCompElHCurl.h"`)

Public methods (exact declarations from the header):
- `TPZCompElHCurl(TPZCompMesh &mesh, TPZGeoEl *gel, const HCurlFamily hcurlfam = DefaultFamily::fHCurlDefaultValue)`
- `TPZCompElHCurl(TPZCompMesh &mesh, const TPZCompElHCurl<TSHAPE> &copy)`
- `TPZCompElHCurl(TPZCompMesh &mesh, const TPZCompElHCurl<TSHAPE> &copy, std::map<int64_t,int64_t> & gl2lcConMap, std::map<int64_t,int64_t> & gl2lcElMap)`
- `TPZCompElHCurl()`
- `TPZCompEl *Clone(TPZCompMesh &mesh) const override`
- `void SetFamily(HCurlFamily f)`
- `virtual TPZCompEl *ClonePatchEl(TPZCompMesh &mesh,std::map<int64_t,int64_t> & gl2lcConMap,std::map<int64_t,int64_t>&gl2lcElMap) const override`
- `~TPZCompElHCurl()`
- `int ClassId() const override`
- `void SetCreateFunctions(TPZCompMesh *mesh) override`
- `MElementType Type() override`
- `int NConnects() const override`
- `int SideConnectLocId(int con, int side) const override`
- `int NSideConnects(int side) const override`
- `int NCornerConnects() const override`
- `void GetInterpolationOrder(TPZVec<int> &ord) override`
- `int64_t ConnectIndex(int con) const override`
- `void SetConnectIndex(int i, int64_t connectindex) override`
- `const TPZVec<int64_t> & ConnectVec() const override`
- `int NConnectShapeF(int connect, int order) const override`
- `int ConnectOrder(int connect) const override`
- `int EffectiveSideOrder(int side) const override`
- `void SetSideOrder(int side, int order) override`
- `void RestrainSide(int side, TPZInterpolatedElement *large, int neighbourside) override`
- `void InitMaterialData(TPZMaterialData &data) override`
- `void ComputeShape(TPZVec<REAL> &qsi, TPZMaterialData &data) override`
- `void Shape(TPZVec<REAL> &pt, TPZFMatrix<REAL> &phi, TPZFMatrix<REAL> &dphi) override`
- `void SideShapeFunction(int side,TPZVec<REAL> &point,TPZFMatrix<REAL> &phi,TPZFMatrix<REAL> &dphi) override`
