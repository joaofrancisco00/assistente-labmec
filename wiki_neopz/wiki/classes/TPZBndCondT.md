# TPZBndCondT — API card

Generated from `Material/TPZBndCondT.h` — do not edit by hand.

Include: `"TPZBndCondT.h"` (in C++ code: `#include "TPZBndCondT.h"`)

Public methods (exact declarations from the header):
- `void SetForcingFunctionBC(ForcingFunctionBCType<TVar> f, int pOrder)`
- `int ForcingFunctionBCPOrder() const`
- `int IntegrationRuleOrder(int order) const override`
- `[[nodiscard]] bool HasForcingFunctionBC() const final`
- `[[nodiscard]] const ForcingFunctionBCType<TVar> &ForcingFunctionBC() const`
- `[[nodiscard]] ForcingFunctionBCType<TVar> &ForcingFunctionBC()`
- `void Print(std::ostream &out = std::cout) const override`
- `int ClassId() const override`
- `void Read(TPZStream& buf, void* context) override`
- `void Write(TPZStream& buf, int withclassid) const override`
- `const TPZFMatrix<TVar> &Val1() const`
- `const TPZVec<TVar> &Val2() const`
- `void SetVal1(const TPZFMatrix<TVar> &val1)`
- `void SetVal2(const TPZVec<TVar> &val2)`

Does NOT exist (common mistakes):
- Never instantiate directly with `new TPZBndCondT` — always create via `TPZBndCondT<STATE> *bc = mat->CreateBC(mat, bcId, bcType, val1, val2);` and insert with `cmesh->InsertMaterialObject(bc);` (types: 0 = Dirichlet, 1 = Neumann, 2 = Robin/mixed).
- For position-dependent (non-constant) boundary conditions, call `bc->SetForcingFunctionBC(bcFunc, pOrder);` where `bcFunc` takes 3 arguments: `[](const TPZVec<REAL> &loc, TPZVec<STATE> &val, TPZFMatrix<STATE> &deriv) { val[0] = ...; }`. (`SetForcingFunction` with 2 args is for domain materials, NOT `TPZBndCondT`).
