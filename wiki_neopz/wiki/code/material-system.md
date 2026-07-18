---
type: code
status: draft
updated: 2026-07-02
confidence: high
evidence-commit: 6ffd38b12
tags:
  - neopz
  - material
  - weak-form
---

# Material system — weak forms & constitutive models

## Responsibility
A "material" is NeoPZ's unit of physics: it evaluates the weak form (`Contribute`: element matrix + rhs at an integration point), boundary conditions (`ContributeBC`), post-processing variables (`Solution`), and optionally exact-solution errors. Materials are keyed by material-id and attached to [[TPZCompMesh]].

## Architecture (verified [repo])
Layered + variadic-mixin design:
- `Material/TPZMaterial.h` — type-agnostic root ("Actual materials should derive from TPZMatBase").
- `Material/TPZMaterialT.h` — `TPZMaterialT<TVar>` type-parametrized layer (STATE vs CSTATE).
- `Material/TPZMatBase.h:21-23` — `template<class TVar, class... Interfaces> class TPZMatBase : public TPZMaterialT<TVar>, public virtual Interfaces...`. One mandatory space interface: `TPZMatSingleSpaceT` (one approximation space) or `TPZMatCombinedSpacesT` (multiphysics). Optional capability mixins: error computation (`TPZMatError*`), load cases, integration-point memory (`TPZMatWithMem`, plasticity/history), eigen problems, interface (DG) contributions.
- `Material/TPZBndCond(Base,T).h` — boundary conditions are themselves materials created via `TPZMatBase::CreateBC` (TPZMatBase.h:59-68) referencing the volumetric material.
- `Material/TPZMaterialData(T).h` — per-integration-point data carrier (shape values, gradients, axes, solution) passed into `Contribute` → [[assembly]].

## Physics families (dirs under `Material/`) [repo dirs; class lists agent-cited]
`Poisson/` (`TPZMatPoisson`), `DarcyFlow/` (`TPZDarcyFlow` primal, `TPZMixedDarcyFlow` H(div)×L², hybrid + fracture variants), `Elasticity/` (`TPZElasticity2D/3D`, `TPZMixedElasticityND`, `TPZHybridElasticity2D/3D` — the 2D hybrid one is in the 5-file develop delta, `TPZHybridMixedElasticityUP`), `Projection/` (L²/H(div)/H(curl) projections), `Electromagnetics/` (waveguides + PML), `Plasticity/` (~75 headers, `BUILD_PLASTICITY_MATERIALS`-gated), `ConsLaw/` (Euler), `BlackOil/`.
Glue materials: `TPZNullMaterial(CS)` (space placeholder), `TPZLagrangeMultiplier(CS)` (interface coupling in [[hybridization]]).

## Legacy layer
`Material/needrefactor/` = 19 top-level entries + `REAL/` with 108 files [repo count] — old-style materials predating the mixin design, several duplicating modern formulations (e.g. two `TPZMixedDarcyFlow`, old vs new mixed elasticity) [agent]. Self-labeled refactor debt → finding candidate for Phase 5.

## Related
[[TPZCompMesh]] · [[assembly]] · [[mixed-methods]] · [[hybridization]] · [[approx-space-creators]] · [[error-estimation-convergence]]

## Open questions
- How the combined-spaces `Contribute` receives per-space `TPZMaterialData` vectors (order = mesh vector order?) — needed before judging mixed weak forms (Phase 4).
- Virtual-inheritance diamond (`public virtual Interfaces...`) cost/complexity — Phase 5.
