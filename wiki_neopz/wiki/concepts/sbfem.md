---
type: concept
status: draft
updated: 2026-07-02
confidence: low
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
---

# SBFem — Scaled Boundary FEM

**Idea.** Semi-analytical method: discretize only the boundary of star-shaped subdomains; the radial direction is handled analytically via an eigenvalue problem (good for singularities/unbounded domains).

**In NeoPZ.** Cross-cutting sub-framework: `Mesh/TPZSBFemVolume.h`, `TPZSBFemElementGroup.h`, HDiv/multiphysics variants (`TPZSBFemVolumeHdiv/L2/Multiphysics`, `TPZSBFemMultiphysicsElGroup`); builders `Pre/TPZBuildSBFem*`; LAPACK-gated (eigen decompositions), optional Blaze. Convergence-tested in `UnitTest_PZ/TestSBFem` (standard + HDiv variants) [agent]. Not on the assessment's critical path (no selected slice uses it) — treated as breadth item; depth only if findings warrant.

**Reference anchors.** Song & Wolf (SBFem origin); Devloo-group SBFem papers (sbfempaper branch exists [repo branch list]).

Related: [[hdiv-space]] · [[matrix-and-solvers]]
