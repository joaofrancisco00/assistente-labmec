---
type: concept
status: draft
updated: 2026-07-02
confidence: medium
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
  - validation
---

# Error computation & convergence validation

**Idea.** Manufactured/analytic solutions → compute norms of (u_h − u) per element and globally; convergence rate vs h (or p) validates implementation order. A posteriori estimators drive adaptivity.

**In NeoPZ.** `TPZAnalysis::SetExact(...)` + `PostProcessError(errors,...)` computes per-material norms via `TPZMatError*::Errors` interfaces ([[material-system]]); `Pre/TPZAnalyticSolution.h` supplies exact solutions+forcings (`TElasticity2DAnalytic` etc. [repo, used in iter_elast]). Error vector convention: typically [0]=energy?, [1]=L2?, per material — **norm indices are material-specific; document per slice** (iter_elast prints error[0..4] [repo, commented block]). Convergence *rate* tests in-library: `TestSBFem` explicitly; most suites test exact-representation (polynomial reproduction) instead of rates [agent] → Phase 7 theme: reproduction-tests vs rate-tests.
A posteriori: gradient reconstruction (Post/), dedicated ErrorEstimation work appears to live downstream (branch `develop-for-ErrorEstimation` [repo branch list]).

**Invariants to check.** Error integration order sufficiency; `ElementSolution` redim before PostProcessError (iter_elast commented code shows the required incantation [repo:391-401]); parallel post-process equality (tested [agent]).

**Reference anchors.** Ainsworth–Oden (a posteriori); standard a priori theory (Ern–Guermond) for expected rates per space/order.

## Canonical API for Exact Error Evaluation (L2 and H1)

To evaluate numerical errors against an analytic solution after `an.Solve()` in `TPZLinearAnalysis` (`#include "TPZLinearAnalysis.h"`), register the exact solution and its gradient with `an.SetExact(exactSol, pOrder)` and call `an.PostProcessError(errors, false)` (`ComputeErrors` does NOT exist):

```cpp
auto exactSol = [](const TPZVec<REAL> &loc, TPZVec<STATE> &u, TPZFMatrix<STATE> &gradU) {
    const REAL x = loc[0], y = loc[1];
    u[0] = std::sin(M_PI * x) * std::sin(M_PI * y);
    gradU.Resize(2, 1);
    gradU(0, 0) = M_PI * std::cos(M_PI * x) * std::sin(M_PI * y);
    gradU(1, 0) = M_PI * std::sin(M_PI * x) * std::cos(M_PI * y);
};

an.SetExact(exactSol, pOrder);
TPZManVector<REAL, 3> errors(3, 0.0);
an.PostProcessError(errors, /*store_error=*/false);
// errors[0] = H1 / energy norm, errors[1] = L2 norm, errors[2] = H1 seminorm
```

Related: [[TPZAnalysis]] · [[material-system]] · [[mixed-methods]] · [[flow-dfreebubbles-1el]]
