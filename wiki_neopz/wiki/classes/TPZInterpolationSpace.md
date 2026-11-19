# TPZInterpolationSpace — API card

Generated from `Mesh/pzinterpolationspace.h` — do not edit by hand.

Include: `"pzinterpolationspace.h"` (in C++ code: `#include "pzinterpolationspace.h"`)

Public methods (exact declarations from the header):
- `virtual int ClassId() const override`
- `TPZInterpolationSpace()`
- `virtual ~TPZInterpolationSpace()`
- `TPZInterpolationSpace(TPZCompMesh &mesh, const TPZInterpolationSpace &copy)`
- `TPZInterpolationSpace(TPZCompMesh &mesh, const TPZInterpolationSpace &copy, std::map<int64_t,int64_t> &gl2lcElMap)`
- `TPZInterpolationSpace(TPZCompMesh &mesh, TPZGeoEl *gel)`
- `virtual void Print(std::ostream &out = std::cout) const override`
- `virtual void ShortPrint(std::ostream &out = std::cout) const override`
- `int NSideShapeF(int side) const`
- `virtual int NSideConnects(int iside) const = 0`
- `virtual int SideConnectLocId(int icon,int is) const = 0`
- `int64_t SideConnectIndex(int icon,int is) const`
- `TPZConnect &SideConnect(int icon,int is) const`
- `virtual int NShapeF() const = 0`
- `virtual int NConnectShapeF(int icon, int order) const = 0`
- `virtual int MaxOrder()`
- `virtual void AdjustIntegrationRule(bool isMeshBuilt = true, int meshPreferredOrder=-1)`
- `virtual int ComputeIntegrationOrder() const override`
- `virtual void SetIntegrationRule(int order) override`
- `virtual void Shape(TPZVec<REAL> &qsi,TPZFMatrix<REAL> &phi,TPZFMatrix<REAL> &dphidxi) = 0`
- `virtual void ComputeShape(TPZVec<REAL> &intpoint, TPZVec<REAL> &X, TPZFMatrix<REAL> &jacobian, TPZFMatrix<REAL> &axes, REAL &detjac, TPZFMatrix<REAL> &jacinv, TPZFMatrix<REAL> &phi, TPZFMatrix<REAL> &dphi, TPZFMatrix<REAL> &dphidx)`
- `static void Convert2Axes(const TPZFMatrix<REAL> &dphi, const TPZFMatrix<REAL> &jacinv, TPZFMatrix<REAL> &dphidx)`
- `virtual void SideShapeFunction(int side, TPZVec<REAL> &point, TPZFMatrix<REAL> &phi, TPZFMatrix<REAL> &dphi)`
- `void ComputeSolution(TPZVec<REAL> &qsi, TPZMaterialDataT<CSTATE> &data, bool hasPhi)`
- `void ComputeSolution(TPZVec<REAL> &qsi, TPZMaterialDataT<STATE> &data, bool hasPhi)`
- `virtual void ComputeShape(TPZVec<REAL> &intpoint, TPZMaterialData &data)`
- `virtual void InitMaterialData(TPZMaterialData &data)`
- `virtual void CleanupMaterialData(TPZMaterialData &data)`
- `virtual void ComputeRequiredData(TPZMaterialDataT<STATE> &data, TPZVec<REAL> &qsi)`
- `virtual void ComputeRequiredData(TPZMaterialDataT<CSTATE> &data, TPZVec<REAL> &qsi)`
- `virtual void ComputeRequiredData(TPZVec<REAL> &intpointtemp, TPZVec<TPZTransform<REAL> > &trvec, TPZVec<TPZMaterialData> &datavec)`
- `virtual void ComputeNormal(TPZMaterialData & data)`
- `void VectorialProd(TPZVec<REAL> & ivec, TPZVec<REAL> & jvec, TPZVec<REAL> & kvec, bool unitary = false)`
- `virtual void CalcStiff(TPZElementMatrixT<STATE> &ek, TPZElementMatrixT<STATE> &ef) override`
- `virtual void CalcStiff(TPZElementMatrixT<CSTATE> &ek, TPZElementMatrixT<CSTATE> &ef) override`
- `virtual void CalcResidual(TPZElementMatrixT<STATE> &ef) override`
- `virtual void CalcResidual(TPZElementMatrixT<CSTATE> &ef) override`
- `virtual void InitializeElementMatrix(TPZElementMatrix &ek, TPZElementMatrix &ef) override`
- `virtual void InitializeElementMatrix(TPZElementMatrix &ef) override`
- `void MinMaxSolutionValues(TPZVec<STATE> &min, TPZVec<STATE> &max)`
- `virtual const TPZIntPoints &GetIntegrationRule() const override = 0`
- `virtual TPZIntPoints &GetIntegrationRule() = 0`
- `virtual REAL InnerRadius()`
- `void Solution(TPZVec<REAL> &qsi,int var,TPZVec<STATE> &sol) override`
- `void Solution(TPZVec<REAL> &qsi,int var,TPZVec<CSTATE> &sol) override`
- `void InterpolateSolution(TPZInterpolationSpace &coarsel)`
- `void CreateInterfaces(bool BetweenContinuous = false)`
- `TPZInterfaceElement * CreateInterface(int side, bool BetweenContinuous = false)`
- `int ExistsInterface(TPZGeoElSide geosd)`
- `void RemoveInterfaces()`
- `void RemoveInterface(int side)`
- `void EvaluateError(TPZVec<REAL> &errors, bool store_error ) override`
- `virtual TPZVec<STATE> IntegrateSolution(int variable) const override`
- `virtual void Integrate(int variable, TPZVec<STATE> & value) override`
- `virtual void SetPreferredOrder ( int order ) = 0`
- `virtual int GetPreferredOrder ()`
- `virtual void PRefine ( int order ) = 0`
- `virtual int GetSideOrient(int side)`
- `virtual void SetSideOrient(int side, int sideorient)`
- `virtual void Write(TPZStream &buf, int withclassid) const override`
- `virtual void Read(TPZStream &buf, void *context) override`
- `void BuildTransferMatrix(TPZInterpolationSpace &coarsel, TPZTransform<> &t, TPZTransfer<STATE> &transfer)`
