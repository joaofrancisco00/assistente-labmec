---
type: concept
status: draft
updated: 2026-07-02
confidence: medium
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
  - adaptivity
---

# h-refinement, refinement patterns & hanging nodes

**Idea.** Subdivide elements (h-refinement) possibly non-uniformly → "hanging" nodes on interfaces between refinement levels; conformity restored by constraining hanging DOFs to coarse-side DOFs (dependency/constraint matrices), or by pattern-conforming closures.

**In NeoPZ (distinctive design).** *Runtime-defined refinement patterns*: `Refine/TPZRefPattern.h` + `TPZRefPatternDataBase` + 71 `.rpt` data files (`Refine/RefPatterns/`) describe father→sons subdivisions as little meshes; `TPZGeoElRefPattern<TGeo>` applies them ([[TPZGeoMesh]]). Uniform refinement via per-topology `TPZRef*` classes. Hanging-node constraints live on connects: `TPZConnect` dependency matrices ([[TPZCompMesh]]), built by `TPZInterpolatedElement` restraint logic; validated by `TestHangingNode`, `TestCondensedSpace` ("Constrained Space"), and a refinement suite [agent]. README claims hp-adaptivity + hanging-node support as headline features [repo:README.md:16-19].

**Invariants to check (Phase 4).** Dependency closure (no chains left unresolved / recursive dependencies resolved before assembly); shape restraints consistent with hierarchical basis (side order matching); geometric compatibility of patterns (sons partition father exactly); H(div)/H(curl) restraints under refinement (vector traces!) — is that supported/tested?

**Reference anchors.** Devloo's early adaptivity papers (Devloo–Oden 1987-89 line); Demkowicz hp book (constrained approximation); Šolín et al. as contrast.

Related: [[TPZGeoMesh]] · [[TPZCompMesh]] · [[shape-functions]] · [[hp-adaptivity]]
