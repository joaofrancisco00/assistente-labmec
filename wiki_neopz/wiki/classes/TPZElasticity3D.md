# TPZElasticity3D — API card

Generated from `Material/Elasticity/TPZElasticity3D.h` — do not edit by hand.

Include: `"Material/Elasticity/TPZElasticity3D.h"` (no código: #include "Material/Elasticity/TPZElasticity3D.h")

Public methods (exact declarations from the header):
- `TPZElasticity3D(int nummat, STATE E, STATE poisson, TPZVec<STATE> &force, STATE preStressXX = 0., STATE preStressYY = 0., STATE preStressZZ = 0.)`
- `TPZElasticity3D(int nummat)`
- `TPZElasticity3D()`
- `TPZElasticity3D(const TPZElasticity3D &cp)`
- `virtual ~TPZElasticity3D()`
- `int Dimension() const override`
- `int NStateVariables() const override`
- `virtual int IntegrationRuleOrder(int elPMaxOrder) const override`
- `void Print(std::ostream & out) const override`
- `void SetPostProcessingDirection(TPZVec<REAL> &Direction)`
- `void SetVonMises(REAL fy)`
- `void SetMohrCoulomb(REAL fc, REAL ft)`
- `std::string Name() const override`
- `void Contribute(const TPZMaterialDataT<STATE> &data, REAL weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef) override`
- `virtual void ContributeVecShape(const TPZMaterialDataT<STATE> &data,REAL weight, TPZFMatrix<STATE> &ek,TPZFMatrix<STATE> &ef)`
- `void ContributeBC(const TPZMaterialDataT<STATE> &data, REAL weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef, TPZBndCondT<STATE> &bc) override`
- `virtual void ContributeVecShapeBC(const TPZMaterialDataT<STATE> & data, REAL weight, TPZFMatrix<STATE> & ek, TPZFMatrix<STATE> & ef, TPZBndCondT<STATE> &bc)`
- `virtual int VariableIndex(const std::string &name) const override`
- `virtual int NSolutionVariables(int var) const override`
- `void Solution(const TPZMaterialDataT<STATE> &data, int var, TPZVec<STATE> &Solout) override`
- `virtual int NEvalErrors() const override`
- `void FillDataRequirements(TPZMaterialData &data) const override`
- `void FillBoundaryConditionDataRequirements(int type,TPZMaterialData &data) const override`
- `void SetMaterialDataHook(REAL Ela, REAL poisson)`
- `void SetMaterialDataLame(REAL lambda, REAL mu)`
- `void SetC()`
- `void SetForce(TPZVec <STATE> force)`
- `STATE GetE()`
- `STATE GetPoisson()`
- `STATE GetLambda()`
- `STATE GetMU()`
- `STATE GetPrestress(int index)`
- `virtual void ComputeStressVector(TPZFMatrix<STATE> &Stress, TPZFMatrix<STATE> &DSol) const`
- `void ComputeStrainVector(TPZFMatrix<STATE> &Strain, TPZFMatrix<STATE> &DSol) const`
- `virtual void ComputeStressTensor(TPZFMatrix<STATE> &Stress, TPZMaterialDataT<STATE> &data) const`
- `void ComputeStressTensor(TPZFMatrix<STATE> &Stress, TPZFMatrix<STATE> &DSol) const`
- `void ComputeStrainTensor(TPZFMatrix<STATE> &Strain, TPZFMatrix<STATE> &DSol) const`
- `void ApplyDirection(TPZFMatrix<STATE> &StrVec, TPZVec<STATE> &Out) const`
- `void PrincipalDirection(TPZFMatrix<STATE> &DSol, TPZVec< STATE > &Solout, int direction) const`
- `virtual void Write(TPZStream &buf, int withclassid) const override`
- `virtual void Read(TPZStream &buf, void *context) override`
- `virtual int ClassId() const override`
- `virtual TPZMaterial * NewMaterial() const override`
