# NeoPZ Algorithm Notes

**Phase 4 deliverable.** Deep review of the major techniques on the analyzed paths, at `develop @ 6ffd38b12` (runtime evidence labeled `[run @ 852a5116c(+)]`). Method: four line-cited code traces (H1 hybrid creator at develop, HDiv creator + semi-hybridization, H(div) shape/Piola pipeline, app-side Schur solver) with load-bearing lines re-verified first-hand, plus an instrumented run of the mandated slice. Full detail in `wiki/` (links inline).

---

## 1. H(div) basis construction & the Piola question — **resolved, conventional (variant factorization)**

**Goal**: H(div)-conforming vector bases on all topologies, hierarchical, hp-capable.
**Implementation**: `Shape/TPZShapeHDiv*` compose each vector shape = scalar H1 shape × constant master-element direction (`TPZShapeHDiv.cpp:345-355`), directions from Topology (`ComputeHDivDirections`; the triangle routine is itself commented "contravariant piola mapping", `tpztriangle.cpp:1064-1068`). Shape layer outputs **master** quantities only. The element layer applies the **contravariant Piola map pointwise**: `fDeformedDirections = (1/|detJ|)·J·φ̂`, `divphi *= 1/|detJ|` (`Mesh/pzelchdiv.cpp:1032-1033`, verified). Orientation = `fSideOrient` (from `TPZGeoEl::NormalOrientation`) folded into master directions + facet-DOF permutation gather (`HDivPermutation`) for neighbor compatibility. Curved elements: pointwise Jacobians + an optional FAD branch (`:979-1031`) giving exact physical derivatives; algebraic divergence scaling is exact for general smooth maps (Piola identity) — no hidden affine assumption found.
**Verdict**: conventional contravariant Piola in a NeoPZ-specific factorization (|detJ| + explicit side-orient signs instead of signed detJ). Matches the published construction ([[devloo-group-shape-construction]]).
**Residual risks**: (a) |detJ|⊕fSideOrient sign composition across all refinement/orientation configs — expert derivation or targeted test recommended; (b) confirmed REAL-vs-FAD inconsistency in `TPZShapeHDivConstant` facet kernel counts ([[finding-hdivconstant-fad-index]]) — latent for curved × HDivConstant × variable face order; (c) intentionality of unused `divphiFad`.
**Validation present**: De Rham rank/kernel tests (SVD), permutation-invariance tests, constant div/curl reproduction, side-shape continuity — strong at basis level; no test combines H(div) × curved geometry × convergence rate (Phase 7 gap).

## 2. HDivConstant / kernel families — **intentional variants, published**

`TPZShapeHDivConstant` derives from `TPZShapeHCurlNoGrads`: per facet a single RT0-like function carries the (constant) divergence; all remaining functions are divergence-free (rotated H1 gradients in 2D, HCurl-NoGrads curls in 3D) (`TPZShapeHDivConstant.cpp:129-215`). Divergence image = piecewise constants — the property enabling exact total condensation with order-0 pressures. Family/enrichment-driven accuracy differences are the group's published research axis ([[devloo-hdiv-variants-accuracy]]). `EHDivOptimized` semantics remain undocumented in-tree (expert question).

## 3. Hybridization taxonomy — **traced end-to-end; conventional core + published extensions**

Frame: [[cockburn-2009-unified-hybridization]]. NeoPZ realization ([[hybridization]] for full line-cites):
- **Geometry protocol**: wrap geoels on interior facets + interface pairs + Lagrange skeleton geoels, ids strided above max matid; interfaces registered in `HybridizationData::fInterfaces`; glue = `TPZMultiphysicsInterfaceElement` + `TPZLagrangeMultiplierCS` with problem-dependent sign tables (verified `TPZApproxCreator.cpp:780-830`).
- **EStandard (H1)**: broken H1 volume; wrap comp-els *share* volume connects; skeleton flux mesh (HDivStandard, dim−1). Single multiplier level.
- **EStandardSquared (H1; mandated slice)**: literal hybridization² — `AddHybridSquareGeoElements` adds a second interface+multiplier layer; condensation groups absorb first-level flux/Lagrange DOFs (`AssociateElements`, numloops=2), leaving **only the second-level skeleton global**. Structurally matches the primal double-hybrid method of [[avancini-2025-double-hybrid-elasticity]].
- **ESemi (HDiv)**: requires EHDivConstant/EHDivOptimized; per interior facet the flux connect splits into even=constant (1 shape) + odd=higher-order (nshape−1) via `TPZCompElHDivDuplConnects`; only the even connect on the sideOrient=−1 side is rebound to the wrap ⇒ *constant normal flux* becomes multiplier-mediated, higher-order trace stays strongly continuous; order-0 multiplier mesh. Structurally the semi-hybridization of [[carvalho-2024-semi-hybrid-stokes]] (which trace is weakened differs — intentional variant).
- **Elasticity extras**: mixed-elasticity in HDiv adds a rotation space (weak symmetry; scalar 2D / 3-vector 3D); in-code guard documents that condensed HDivConstant elasticity is singular without ESemi or rigid-body spaces (`TPZHDivApproxCreator.cpp:85-89`).
**Assumptions/invariants**: multiplier sign tables per problem (Elastic asymmetry — only right interface reset to +1 — flagged as expert question); Lagrange-level ordering drives what is condensable; `EAvSol` global-coupling mechanism under EStandardSquared unclear from code (works per tests) — expert question.
**Hygiene**: cluster of small verified defects in exactly this layer ([[finding-approx-creator-hygiene]]).

## 4. Static condensation & rigid-body spaces — **coherent design, invariants identified**

`TPZElementGroup` → `TPZCondensedCompElT` decorator (exposes only active connects; internal Schur via library `TPZMatRed`, which is rigid-body-mode aware — `pzmatred.h:23-79` verified). Connect "Lagrange levels" order condensability; `fIsRBSpaces` appends order-0 constant meshes (distributed flux + average solution; elastic: 3/6 states = rigid-body-mode counts) precisely to make interior blocks invertible for total condensation. Invariants: K00 invertibility (guarded in one known-singular case), correct recovery via `UGlobal`-style back-substitution, dependency (hanging-node) connects excluded from splits.

## 5. The app-side Schur solver (`TPZMatRedSolver`/`TPZSparseMatRed`) — **sound structure; one consequential mislabel**

Flow (verified by trace + run): equations split purely by Lagrange level (`lag={1}` → K00), independent of mode; K00 = symmetric sparse Pardiso/MUMPS, Cholesky-factorized; Schur complement K11−K10·K00⁻¹·K01 applied **matrix-free** in CG (`TPZSparseMatRed::MultAdd`), block-diagonal(ELU) preconditioner from K11; 500 iter cap, tol 1e-10; solution recovered and loaded back. Negative-definite K00 handled by global sign flips for the H1-hybrid modes.
**Run evidence** [run]: CG iterations = 19 at 50² and 400² (p=1) — mesh-independent; t1 = block assembly, t2 = K00 factorization + preconditioner build + CG.
**Findings**: mode mislabel with measurable effect on the benchmark ([[finding-matred-solver-mode-mislabel]]); memory-unit platform bug ([[finding-rusage-memory-units]]); `EMHMSparse`-era API removed at HEAD leaving one registered target uncompilable ([[finding-mhm-target-uncompilable]]). "Orthogonalizing restraints" (`ComputeOrthogonalizingRestraints`, app-side, feeding the High-Order/Linear flux split observed at runtime) not yet traced — expert/maintainer question.

## 6. Assembly & solve orchestration — **verified at the orchestration level**

`TPZLinearAnalysis::AssembleT`: defaulting rules (MKL sparse else skyline; LU), in-place matrix reuse when size matches, load-case-aware RHS (`TPZLinearAnalysis.cpp:35-100`, verified). Solve honors equation filters (`NReducedEquations`). Parallel-vs-serial assembly equality is unit-tested (`TestMultithreading` [agent]). Per-element `CalcStiff` → material `Contribute` pipeline detail (H1/mixed data vectors ordering) is documented per creator ordering; thread-safety of shared materials → Phase 5.

## 7. At-pin defects on analyzed paths (library)

1. **`TPZHybridElasticity2D::Contribute` omits body-force RHS at the pin** — confirmed, fixed 2 commits later upstream ([[finding-hybridelasticity2d-missing-rhs-at-pin]]). The mandated benchmark is insensitive (zero body force), which is exactly why no test caught it.
2. `TPZShapeHDivConstant` FAD facet-count inconsistency ([[finding-hdivconstant-fad-index]]).
3. `TPZCreateApproximationSpace` copy ops drop family flags ([[finding-approxspace-copy-drops-families]]).
4. Missing self-assignment guard pattern (`TPZMatRed::CopyFrom`; patched post-pin in `TPZSYsmpMatrix`) — same family.

## 8. Numerical-stability & correctness watchlist (expert-validation queue)

- |detJ| ⊕ fSideOrient composition on reflected/refined configurations ([[piola-transformations]]).
- Elastic interface-multiplier sign asymmetry (H1 path).
- `EAvSol` coupling mechanism under EStandardSquared.
- ESemi-for-Darcy vs the Stokes-oriented published semi-hybridization (which trace should be weak for Darcy).
- Preconditioner block-size validity (`bsize | nEqHigh`) if the elasticity mode is corrected.
- Quadrature-order sufficiency for `fExtraInternalPOrder`-enriched spaces on curved maps (untested combination).

## 9. Performance notes carried to Phase 6

Mesh-independent CG counts (excellent); K00 factorization dominates t2 at scale (3.4 s of 4.7 s at 400², p=1 [run]); assembly scales ~linearly across the sweep; renumbering disabled in benchmarks (`RenumType::ENone`) — interaction with the Lagrange-level-contiguous reordering inside `TPZSparseMatRed::ReorderEquations` explains why (the solver does its own ordering); memory column unreliable on macOS.
