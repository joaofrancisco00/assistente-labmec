# TPZLinearAnalysis — API card

Generated from `Analysis/TPZLinearAnalysis.h` — do not edit by hand.

Include: `"TPZLinearAnalysis.h"` (in C++ code: `#include "TPZLinearAnalysis.h"`)

Public methods (exact declarations from the header):
- `TPZLinearAnalysis()`
- `TPZLinearAnalysis(TPZCompMesh *mesh, const RenumType& renumtype = RenumType::EDefault, std::ostream &out = std::cout)`
- `TPZLinearAnalysis(TPZAutoPointer<TPZCompMesh> mesh, const RenumType& renumtype = RenumType::EDefault, std::ostream &out = std::cout)`
- `template<class TVar> TPZMatrixSolver<TVar> & MatrixSolver()`
- `TPZSolutionMatrix &Rhs()`
- `void Assemble() override`
- `virtual void AssembleResidual()`
- `void Solve() override`
- `void SetSolver(const TPZSolver &solver) override`
- `void SetCompMesh(TPZCompMesh * mesh, RenumType mustOptimizeBandwidth) override`
- `void AnimateRun(int64_t num_iter, int steps, TPZVec<std::string> &scalnames, TPZVec<std::string> &vecnames, const std::string &plotfile)`
- `void PostProcess(TPZVec<REAL> &loc, std::ostream &out = std::cout) override`
- `void PostProcess(int resolution) override`
- `void PostProcess(int resolution, int dimension) override`
- `inline void SetTime(REAL time)`
- `inline REAL GetTime() const`
- `int ClassId() const override`
- `void Write(TPZStream &buf, int withclassid) const override`
- `void Read(TPZStream &buf, void *context) override`

Does NOT exist (common mistakes):
- To compute exact L2/H1 errors: call `an.SetExact(exactSol, pOrder);` (signature `void(const TPZVec<REAL> &loc, TPZVec<STATE> &u, TPZFMatrix<STATE> &gradU)`) and `TPZManVector<REAL, 3> errors(3, 0.); an.PostProcessError(errors, false);` (`ComputeErrors` does NOT exist).
