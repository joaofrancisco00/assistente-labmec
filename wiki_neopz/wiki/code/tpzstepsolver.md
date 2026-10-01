# Linear System Solvers: TPZStepSolver

This page is a catalog of the structure of the NeoPZ step solver, for which **no** "invented" code with unsupported methods should be generated.

## `TPZStepSolver`
**Header**: `#include "pzstepsolver.h"`

Represents a matrix solver and can also be used as a preconditioner. `TPZStepSolver` solves linear systems of the form `A*x = B`. In NeoPZ it is usually instantiated, configured and then handed to the analysis class (`TPZAnalysis` or `TPZLinearAnalysis`) with `SetSolver`.

### Real configuration methods (from `pzstepsolver.h`)

| Method | Use |
|---|---|
| `SetDirect(DecomposeType)` | **Direct** solver only: `ECholesky` (SPD), `ELDLt` (symmetric indefinite, e.g. saddle point), `ELU` (general) |
| `SetCG(numiterations, pre, tol, FromCurrent)` | Conjugate Gradient with preconditioner `pre` |
| `SetGMRES(numiterations, numvectors, pre, tol, FromCurrent)` | GMRES with `numvectors` Krylov vectors and preconditioner `pre` |
| `SetBiCGStab(numiterations, pre, tol, FromCurrent)` | BiCGStab with preconditioner `pre` |
| `SetJacobi(numiterations, tol, FromCurrent)` | Jacobi (also used as a preconditioner) |
| `SetSOR(...)` / `SetSSOR(...)` | (Symmetric) successive over-relaxation |
| `SetTolerance(tol)` | Changes the tolerance |
| `SetPreconditioner(solver)` | Sets a preconditioner solver |

**`SetDirect` does NOT select iterative methods**: `SetDirect(EGMRES)` or
`SetDirect(EJacobi)` do not exist. Iterative methods have their own setters,
which receive the preconditioner as an argument.

### Usage example (direct and iterative with preconditioner)
```cpp
#include "pzstepsolver.h"
#include "TPZLinearAnalysis.h"

int main() {
    // Assume the analysis already has its computational mesh and structural matrix
    TPZLinearAnalysis an;

    // Option 1: direct solver (SPD system → Cholesky)
    TPZStepSolver<STATE> direct;
    direct.SetDirect(ECholesky);

    // Option 2: GMRES preconditioned with Jacobi
    TPZStepSolver<STATE> jacobi;
    jacobi.SetJacobi(1, 0., 0);           // 1 iteration, as a preconditioner

    TPZStepSolver<STATE> gmres;
    const int64_t maxIterations = 500;
    const int krylovVectors = 50;
    const REAL tol = 1.e-8;
    gmres.SetGMRES(maxIterations, krylovVectors, jacobi, tol, 0);

    // Hand the chosen solver to the analysis
    an.SetSolver(gmres);

    return 0;
}
```
