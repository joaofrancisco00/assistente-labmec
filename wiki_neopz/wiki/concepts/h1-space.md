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

# H1-conforming spaces

**Idea.** Piecewise-polynomial spaces continuous across element boundaries; the natural home of primal formulations (Poisson, elasticity displacement). Conformity requirement: function traces match on shared faces/edges/vertices.

**In NeoPZ.** Continuous elements `TPZCompElH1`/`TPZIntelGen` over per-topology `pzshape::` classes; continuity by *shared connects* on sides ([[TPZCompMesh]]); hierarchical bases allow per-connect order → p-adaptivity. Creator: `SetAllCreateFunctionsContinuous` ([[approx-space-creators]]), problem-level `TPZH1ApproxCreator` (hybrid variants). `H1Family` enum suggests flavors (standard vs ?) — verify.

**Invariants to check (Phase 4).** Trace continuity under neighbor order mismatch (min-order rule on shared sides?); hanging-node dependency correctness ([[refinement-hanging-nodes]]); rigid-body/constant reproduction (`TestH1ApproxSpaceCreator` covers constant + linear solutions [agent]).

**Reference anchors (Phase 3).** Devloo–Bravo–Rylo 2009 (systematic shape construction); Szabó–Babuška (p-version); Ern–Guermond.

Related: [[shape-functions]] · [[hybridization]] · [[de-rham-complex]] · [[flow-iter-elast]]
