---
type: concept
status: draft
updated: 2026-07-02
confidence: medium
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
---

# Mixed methods (saddle-point formulations)

**Idea.** Approximate two fields simultaneously (e.g. Darcy: flux σ ∈ H(div) and pressure p ∈ L²) yielding a saddle-point system; stability requires inf-sup-compatible space pairs; payoff = locally conservative fluxes / direct stress approximation.

**In NeoPZ.** Multiphysics machinery: atomic cmeshes per field combined in `TPZMultiphysicsCompMesh` ([[TPZCompMesh]]); combined-space materials (`TPZMatCombinedSpacesT`): `DarcyFlow/TPZMixedDarcyFlow`, `Elasticity/TPZMixedElasticityND`, `TPZHybridMixedElasticityUP` ([[material-system]]); spaces built by `TPZHDivApproxCreator` with `ProblemType::{EDarcy,EElastic}` ([[approx-space-creators]]); Lagrange-multiplier levels on connects order the condensation. App-side slices: [[flow-dupl-connects]], [[flow-dfreebubbles-1el]], hpc4 (3D mixed elasticity, SPE10-like).

**Invariants to check (Phase 4).** Flux×pressure order pairing (RT-like vs BDM-like: which does each `HDivFamily` give?); inf-sup for mixed *elasticity* (symmetry of stress handled how — weak symmetry with rotation multiplier? `TPZMixedElasticityND` interface suggests displacement+rotation multipliers [verify]); sign/scaling conventions in the saddle-point blocks; local conservation of computed fluxes.

**Reference anchors.** Boffi–Brezzi–Fortin (canonical); Devloo et al. mixed-elasticity papers (multiphysics + weak symmetry); Arnold's stress-element literature as contrast.

Related: [[hdiv-space]] · [[hybridization]] · [[static-condensation]] · [[de-rham-complex]] · [[error-estimation-convergence]]
