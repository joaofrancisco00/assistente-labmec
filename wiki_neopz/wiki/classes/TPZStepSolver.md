# TPZStepSolver — API card

Generated from `Solvers/pzstepsolver.h` — do not edit by hand.

Include: `"pzstepsolver.h"` (in C++ code: `#include "pzstepsolver.h"`)

Public methods (exact declarations from the header):
- `TPZStepSolver(TPZAutoPointer<TPZMatrix<TVar> > mat = nullptr)`
- `TPZStepSolver(const TPZStepSolver<TVar> & copy)`
- `virtual ~TPZStepSolver()`
- `void SetSOR(const int64_t numiterations, const REAL overrelax, const REAL tol, const int64_t FromCurrent)`
- `void SetSSOR(const int64_t numiterations, const REAL overrelax, const REAL tol, const int64_t FromCurrent)`
- `void SetJacobi(const int64_t numiterations, const REAL tol, const int64_t FromCurrent)`
- `void SetCG(const int64_t numiterations, const TPZMatrixSolver<TVar> &pre, const REAL tol, const int64_t FromCurrent)`
- `void SetGMRES(const int64_t numiterations, const int numvectors, const TPZMatrixSolver<TVar> &pre, const REAL tol, const int64_t FromCurrent)`
- `void SetBiCGStab(const int64_t numiterations, const TPZMatrixSolver<TVar> &pre, const REAL tol, const int64_t FromCurrent)`
- `void SetDirect(const DecomposeType decomp)`
- `void SetMultiply()`
- `virtual TPZSolver *Clone() const override`
- `void SetTolerance(REAL tol)`
- `REAL GetTolerance() const`
- `void ResetSolver()`
- `virtual typename TPZMatrixSolver<TVar>::MSolver Solver() override`
- `std::list<int64_t> &Singular()`
- `virtual void ResetMatrix() override`
- `virtual void UpdateFrom(TPZAutoPointer<TPZBaseMatrix> matrix) override`
- `void Solve(const TPZFMatrix<TVar> &F, TPZFMatrix<TVar> &result, TPZFMatrix<TVar> *residual = 0) override`
- `virtual void Decompose() override`
- `void SetPreconditioner(TPZMatrixSolver<TVar> &solve)`
- `int NumIterations()`
- `TPZMatrixSolver<TVar> *PreConditioner()`
- `int ClassId() const override`
- `void Write(TPZStream &buf, int withclassid) const override`
- `void Read(TPZStream &buf, void *context) override`
