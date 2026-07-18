---
type: concept
status: draft
updated: 2026-07-02
confidence: medium
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
  - hcurl
---

# H(curl)-conforming spaces

**Idea.** Vector fields with curl in L²; conformity = continuity of *tangential* components across faces/edges. Standard for electromagnetics (edge/Nédélec elements).

**In NeoPZ.** `Mesh/TPZCompElHCurl*`, shapes `Shape/TPZShapeHCurl.h` and `TPZShapeHCurlNoGrads.h` ("no-grads" = basis without gradient fields — reduced/kernel-oriented family, cf. kernel-H(div) 2D duality); `TPZHCurlEquationFilter.h` (edge/tree gauging? verify); materials in `Material/Electromagnetics/` (waveguides + PML). Unit tests: `TestHCurl` (trace continuity, permutations, curls), `TestTopology` `constant_curl_test` [agent].

**Invariants to check.** Tangential-trace continuity under edge orientation mismatch; covariant Piola mapping; exactness grad(H1) ⊂ H(curl) ([[de-rham-complex]] — `TestDeRham` covers H1↔HCurl pairs [agent]).

**Reference anchors.** De Siqueira–Devloo–Gomes; Nédélec's families (via Boffi–Brezzi–Fortin / Monk); Devloo-group HCurl papers (Orlandini et al.?) — locate in Phase 3.

Related: [[hdiv-space]] · [[de-rham-complex]] · [[shape-functions]] · [[topology-module]]
