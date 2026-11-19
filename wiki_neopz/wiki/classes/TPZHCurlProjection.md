# TPZHCurlProjection — API card

Generated from `Material/Projection/TPZHCurlProjection.h` — do not edit by hand.

Include: `"Projection/TPZHCurlProjection.h"` (in C++ code: `#include "Projection/TPZHCurlProjection.h"`)

Public methods (exact declarations from the header):
- `TPZHCurlProjection()`
- `TPZHCurlProjection(int id, int dim)`
- `std::string Name() const override`
- `void SetScaleFactor(REAL scale)`
- `[[nodiscard]] REAL ScaleFactor() const`
- `inline int Dimension() const override`
- `inline void SetDimension(int dim)`
- `int NStateVariables() const override`
- `void Contribute(const TPZMaterialDataT<TVar> &data, REAL weight, TPZFMatrix<TVar> &ek, TPZFMatrix<TVar> &ef) override`
- `void ContributeBC(const TPZMaterialDataT<TVar> &data, REAL weight, TPZFMatrix<TVar> &ek, TPZFMatrix<TVar> &ef, TPZBndCondT<TVar> &bc) override`
- `TPZMaterial * NewMaterial() const override`
- `int VariableIndex(const std::string &name) const override`
- `int NSolutionVariables(int var) const override`
- `void Solution(const TPZMaterialDataT<TVar> &data, int var, TPZVec<TVar> &solOut) override`
- `void GetSolDimensions(uint64_t &u_len, uint64_t &du_row, uint64_t &du_col) const override`
- `void Errors(const TPZMaterialDataT<TVar> &data, TPZVec<REAL> &errors) override`
- `[[nodiscard]] int IntegrationRuleOrder(const int elPMaxOrder) const override`
- `virtual int ClassId() const override`
