# TPZDarcyFlow — API card

Generated from `Material/DarcyFlow/TPZDarcyFlow.h` — do not edit by hand.

Include: `"DarcyFlow/TPZDarcyFlow.h"` (in C++ code: `#include "DarcyFlow/TPZDarcyFlow.h"`)

Public methods (exact declarations from the header):
- `TPZDarcyFlow()`
- `TPZDarcyFlow(int id, int dim)`
- `TPZDarcyFlow(const TPZDarcyFlow &copy)`
- `TPZDarcyFlow& operator=(const TPZDarcyFlow &copy)`
- `[[nodiscard]] std::string Name() const override`
- `[[nodiscard]] int Dimension() const override`
- `[[nodiscard]] int NStateVariables() const override`
- `int NEvalErrors() const override`
- `virtual void SetDimension(int dim)`
- `void Contribute(const TPZMaterialDataT<STATE> &data, STATE weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef) override`
- `void ContributeBC(const TPZMaterialDataT<STATE> &data, STATE weight, TPZFMatrix<STATE> &ek, TPZFMatrix<STATE> &ef, TPZBndCondT<STATE> &bc) override`
- `[[nodiscard]] int VariableIndex(const std::string &name) const override`
- `[[nodiscard]] int NSolutionVariables(int var) const override`
- `void Solution(const TPZMaterialDataT<STATE> &data, int var, TPZVec<STATE> &solOut) override`
- `void GetSolDimensions(uint64_t &u_len, uint64_t &du_row, uint64_t &du_col) const override`
- `void Errors(const TPZMaterialDataT<STATE> &data, TPZVec<REAL> &errors) override`
- `virtual void ErrorNames(TPZVec<std::string> &names) const override`
- `void FillDataRequirements(TPZMaterialData &data) const override`
- `void FillBoundaryConditionDataRequirements(int type, TPZMaterialData &data) const override`
- `[[nodiscard]] int ClassId() const override`
- `[[nodiscard]] TPZMaterial *NewMaterial() const override`
- `void Print(std::ostream & out) const override`
