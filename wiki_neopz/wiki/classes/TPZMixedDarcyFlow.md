# TPZMixedDarcyFlow — API card

Generated from `Material/DarcyFlow/TPZMixedDarcyFlow.h` — do not edit by hand.

Include: `"DarcyFlow/TPZMixedDarcyFlow.h"` (in C++ code: `#include "DarcyFlow/TPZMixedDarcyFlow.h"`)

Public methods (exact declarations from the header):
- `TPZMixedDarcyFlow()`
- `[[maybe_unused]] TPZMixedDarcyFlow(int id, int dim)`
- `TPZMixedDarcyFlow(const TPZMixedDarcyFlow &copy)`
- `TPZMixedDarcyFlow &operator=(const TPZMixedDarcyFlow &copy)`
- `[[nodiscard]] std::string Name() const override`
- `[[nodiscard]] int Dimension() const override`
- `[[nodiscard]] int NStateVariables() const override`
- `int NEvalErrors() const override`
- `virtual void SetDimension(int dim)`
- `void Contribute(const TPZVec<TPZMaterialDataT<STATE>> &datavec, REAL weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef) override`
- `void ContributeBC(const TPZVec<TPZMaterialDataT<STATE>> &datavec, REAL weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef, TPZBndCondT<STATE> &bc) override`
- `[[nodiscard]] int VariableIndex(const std::string &name) const override`
- `[[nodiscard]] int NSolutionVariables(int var) const override`
- `void Solution(const TPZVec<TPZMaterialDataT<STATE>> &datavec, int var, TPZVec<STATE> &solOut) override`
- `void Errors(const TPZVec<TPZMaterialDataT<STATE>> &data, TPZVec<REAL> &errors) override`
- `void FillDataRequirements(TPZVec<TPZMaterialDataT<STATE> > &datavec) const override`
- `void FillBoundaryConditionDataRequirements(int type, TPZVec<TPZMaterialDataT<STATE> > &datavec) const override`
- `[[nodiscard]] int ClassId() const override`
- `[[nodiscard]] TPZMaterial *NewMaterial() const override`
- `void Print(std::ostream & out) const override`
