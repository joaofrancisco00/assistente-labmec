# NeoPZ Domain Primer

**Phase 3 deliverable.** Practical explanations of the FEM concepts the repository actually uses, each split into *reference evidence* (established theory, → `wiki/sources/`) and *repository evidence* (what NeoPZ demonstrably does at `develop @ 6ffd38b12`). Concept detail pages: `wiki/concepts/`.

## 1. The space zoo and why NeoPZ is unusual

Reference: conforming FEM needs function spaces matched to the operator — H1 (continuous traces) for primal problems, H(div) (continuous *normal* traces) for fluxes/stresses, H(curl) (continuous *tangential* traces) for EM, L² (no continuity) for pressures/multipliers ([[boffi-brezzi-fortin-2013]]).

NeoPZ does **not** implement the textbook RT/BDM/Nédélec families. It implements the Devloo-group *hierarchical* construction: pick geometry-based vector fields per element, multiply by hierarchical H1 scalars → vector bases whose normal (H(div)) or tangential (H(curl)) interface components are continuous **by construction** ([[devloo-group-shape-construction]], JCAM 2013). Repo: `Shape/TPZShapeHDiv*.h`, `TPZShapeHCurl*.h` compose exactly this way (structure verified; deep trace Phase 4); per-connect orders make hp native ([[shape-functions]]).

Flavors at the pin [repo `Shape/TPZEnumApproxFamily.h:5-11`]: `HDivFamily {EHDivStandard, EHDivConstant, EHDivKernel, EHDivOptimized}`, `H1Family {EH1Standard, EH1WidePrism}`, `HCurlFamily {EHCurlStandard, EHCurlNoGrads}`. Published context: multiple H(div) types with different internal enrichment and divergence accuracy are a *deliberate research axis* ([[devloo-hdiv-variants-accuracy]]) — reviewers should treat flavor-specific surprises as candidate intentional variants, not bugs, until traced.

## 2. De Rham compatibility as the house correctness criterion

Reference: the discrete sequence H1 →grad→ H(curl) →curl→ H(div) →div→ L² should be exact for stable mixed pairs (FEEC; [[boffi-brezzi-fortin-2013]] Ch.2.5).
Repo: NeoPZ *tests this directly* — `UnitTest_PZ/TestDeRham` builds Gram matrices of `op(φ)` and checks `rank(M_left) = ker(M_right)` plus range-inclusion via SVD, dims 2/3, k=1..3, incl. the `HDivConst` flavor [repo TestDeRham.cpp:49-120]. Mesh-level De Rham checks incl. face-permutation invariance live in `TestMesh/TestHDiv.cpp`. This is a strong, unusual, in-repo validation asset ([[de-rham-complex]]). What it does *not* establish: commuting-diagram/interpolation properties, curved-element exactness — Phase 7 records these as gaps, not failures.

## 3. Mixed methods and multiphysics plumbing

Reference: saddle-point problems need inf-sup-compatible pairs; payoffs are local conservation and direct flux/stress fields ([[boffi-brezzi-fortin-2013]] Ch.4-5).
Repo: one `TPZCompMesh` per field (flux, pressure, …) combined into `TPZMultiphysicsCompMesh`; combined-space materials (`TPZMatCombinedSpacesT`) evaluate the coupled weak form; `TPZHDivApproxCreator` builds Darcy/elasticity pairs by `ProblemType` ([[mixed-methods]], [[approx-space-creators]], [[material-system]]). The De Rham-compatible H(div)×L² pairing is the group's standard trick to keep divergence-consistency exact.

## 4. Hybridization: the repo's central research axis

Reference: hybridization breaks a continuity and re-imposes it with skeleton Lagrange multipliers; local problems condense to an SPD skeleton system ([[cockburn-2009-unified-hybridization]]).
Repo taxonomy [Pre/TPZApproxCreator.h:15]: `ENone | EStandard | EStandardSquared | ESemi`, orchestrated with wrap/interface/Lagrange material ids (`HybridizationData`).
- **EStandard** ≈ classic single-level hybridization.
- **EStandardSquared** ("double hybrid"): second hybridization level — traced in Phase 4 as a literal hybridization² of the **broken-H1 primal space** (second interface/multiplier layer; only the 2nd-level skeleton stays global). The published double-hybrid elasticity paper ([[avancini-2025-double-hybrid-elasticity]], CMAME 2025) uses H(div)–L² displacements/pressure — the in-code H1 path is a *structurally matching primal variant*, not a verbatim implementation of that paper (classification: intentional variant; exact correspondence = expert question). Exercised by the mandated slice [[flow-iter-elast]] (`TPZH1HybridApproxCreator`, elasticity).
- **ESemi** (semi-hybridization): only *part* of the interface coupling moves to multipliers — H(div) normal continuity stays strong, tangential (or a designated subset) goes weak; realized via duplicated connects ([[carvalho-2024-semi-hybrid-stokes]], IJNME 2024; `TPZCompElHDivDuplConnects*`). Exercised by [[flow-dupl-connects]].
Mapping code↔paper is **hypothesis-level until Phase 4** (recorded on both source pages).

## 5. Static condensation, rigid-body spaces, and Schur solvers

Reference: eliminate interior DOFs per element/patch; needs invertible interior blocks; skeleton system stays SPD for symmetric problems.
Repo: `TPZCondensedCompEl`/`TPZElementGroup` wrap elements; connect "Lagrange levels" order what is condensable; `fIsRBSpaces` enriches with constants/rigid-body fields precisely so interior blocks *become* invertible (needed for total condensation with `EHDivConstant`) [[static-condensation]]. Downstream, the app repo drives reductions iteratively: `TPZMatRedSolver` (Schur complement on the multiplier/BC block, modes per problem family) over lib-side `TPZMatRed`-style containers ([[divfree-support-lib]], [[matrix-and-solvers]]).

## 6. MHM — multiscale hybrid-mixed

Reference: [[araya-2013-mhm]] (SINUM 2013): coarse-skeleton multipliers + independent fine local problems per coarse cell; locally conservative dual variable; per-subdomain constant/rigid-body kernels become the coarse unknowns.
Repo: two generations (older `TPZMHM*MeshControl`, newer `TPZMHM*ApproxCreator` — in *both* the library and the app repo, same class name!). Slice [[flow-mhm-hdivconstant]]: polygonal coarse cells from a quadtree file, triangulated around scaling centers, `EHDivConstant` + rigid-body spaces + `PutinSubstructures`/`CondenseElements` (`TPZSubCompMesh` = the local-problem container). Elasticity-on-polygons variant published by the group ([[devloo-mhm-elasticity-polygonal]]).

## 7. Geometry: master elements, sides, curved maps, and the mapping question

Reference: FE integrals pull back through the element map; *vector* bases additionally need Piola-type transforms — contravariant for H(div), covariant for H(curl) — especially on non-affine/curved elements ([[boffi-brezzi-fortin-2013]] Ch.2).
Repo: topology layer (`Topology/`, "sides" with permutation machinery) → geometry maps (`Geom/`, blend maps, `SpecialMaps/` exact curved geometries) → `axes`-based gradient frames (2D elements embeddable in 3D). **Where/how the Piola step happens is deliberately left open** ([[piola-transformations]]) — the group has published on H(div) for curved meshes ([[devloo-hdiv-variants-accuracy]]), so the convention is a documented variant to be traced, not presumed textbook. Phase 4 must locate the transform in `TPZCompElHDiv::ComputeRequiredData`/shape drivers before any correctness claim.

## 8. Refinement, hanging nodes, hp

Reference: nonuniform h-refinement produces hanging DOFs constrained to coarse neighbors; hp needs per-entity orders and side-order compatibility.
Repo: *runtime-defined refinement patterns* (71 `.rpt` data files + `TPZRefPattern` database) — a distinctive NeoPZ capability [README + Refine/]; constraints live in `TPZConnect` dependency matrices resolved at assembly ([[refinement-hanging-nodes]]); per-connect orders come free with hierarchical shapes ([[hp-adaptivity]]). Unit tests cover hanging nodes and constrained spaces; H(div)/H(curl)-under-refinement coverage is a Phase 7 question.

## 9. Assembly, solvers, output

Repo pipeline (verified across five slices, [[flow-iter-elast]] etc.): `TPZLinearAnalysis` → `TPZStructMatrix` flavor (storage × parallel scheme × equation filter) → per-element `CalcStiff` → material `Contribute` per quadrature point → connect-indexed scatter → `TPZStepSolver` direct (ELDLt/Cholesky/LU, in-house or MKL/Pardiso/MUMPS) or Krylov (CG/GMRES with block/Jacobi preconditioners) ([[assembly]], [[structural-matrices]], [[matrix-and-solvers]], [[TPZAnalysis]]).
Output: modern `TPZVTKGenerator` (legacy-format .vtk, element subdivision by `vtkRes`, NGSolve-derived) + legacy graph-mesh writers; error path `SetExact` → `PostProcessError` with material-defined norms ([[vtk-output]], [[error-estimation-convergence]]).

## 10. Reviewer's caution list (from Phase 3)

1. NeoPZ families ≠ textbook families — compare *properties* (traces, exactness, orders), never DOF layouts.
2. Hybridization taxonomy is a research frontier here (squared/semi) — papers exist but code may lead or lag them; classify mismatches per the 5-way scheme.
3. Flavor knobs (`HDivFamily`, `fExtraInternalPOrder`, RB spaces) intentionally change accuracy orders — "wrong-looking" convergence may be the documented behavior ([[devloo-hdiv-variants-accuracy]]).
4. The De Rham tests are rank-level; don't over-claim what they prove.
5. Benchmarks in the app repo validate performance only (error/VTK legs disabled) — correctness evidence lives in unit tests + dFreeBubbles1el ([[flow-dfreebubbles-1el]]).
