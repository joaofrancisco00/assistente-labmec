# TPZElasticity2D — API card

Generated from `Material/Elasticity/TPZElasticity2D.h` — do not edit by hand.

Include: `"Elasticity/TPZElasticity2D.h"` (in C++ code: `#include "Elasticity/TPZElasticity2D.h"`)

Public methods (exact declarations from the header):
- `TPZElasticity2D(int id, STATE E, STATE nu, STATE fx, STATE fy, int planestress = 1)`
- `TPZElasticity2D(int id)`
- `TPZElasticity2D(const TPZElasticity2D &copy)`
- `void SetElasticity(STATE E, STATE nu)`
- `void SetConstitutiveLaw(const TPZLinearElasticityConstitutive &constitutive)`
- `void SetElasticityFunction(ElasticityFunctionType func)`
- `void SetAnisotropicForcingFunction(AnisotropicForcingFunctionType func, int porder)`
- `void SetPlaneStrain()`
- `void SetPlaneStress()`
- `void SetStressState(MStressState state)`
- `void SetVecShapeFunctionUsage(bool usevecshape)`
- `void SetBodyForce(STATE fx, STATE fy)`
- `STATE GetLambda(STATE E, STATE nu) const`
- `STATE GetMU(STATE E, STATE nu) const`
- `STATE E()`
- `STATE Nu()`
- `void SetPreStress(STATE Sigxx, STATE Sigyy, STATE Sigxy, STATE Sigzz)`
- `int Dimension() const override`
- `int NStateVariables() const override`
- `void Print(std::ostream & out = std::cout) const override`
- `std::string Name() const override`
- `void Contribute(const TPZMaterialDataT<STATE> &data, STATE weight, TPZFMatrix<STATE> &ek,TPZFMatrix<STATE> &ef) override`
- `void ContributeBC(const TPZMaterialDataT<STATE> &data,STATE weight, TPZFMatrix<STATE> &ek,TPZFMatrix<STATE> &ef, TPZBndCondT<STATE> &bc) override`
- `void FillDataRequirements(TPZMaterialData &data) const override`
- `void FillBoundaryConditionDataRequirements(int type, TPZMaterialData &data) const override`
- `void VariableNames(TPZVec<std::string> &names) const`
- `int VariableIndex(const std::string &name) const override`
- `int NSolutionVariables(int var) const override`
- `void Solution(const TPZMaterialDataT<STATE> &data, int var, TPZVec<STATE> &Solout) override`
- `int NEvalErrors() const override`
- `void ErrorNames(TPZVec<std::string> &errornames) const override`
- `void GetSolDimensions(uint64_t &u_len, uint64_t &du_row, uint64_t &du_col) const override`
- `TPZMaterial * NewMaterial() const override`
- `int ClassId() const override`
- `void Read(TPZStream &buf, void *context) override`
- `void Write(TPZStream &buf, int withclassid) const override`
