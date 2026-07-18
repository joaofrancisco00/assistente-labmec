---
type: concept
status: draft
updated: 2026-07-02
confidence: low
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
  - adaptivity
---

# hp-adaptivity

**Idea.** Combine local mesh refinement (h) with local polynomial-order enrichment (p); with the right strategy gives exponential convergence for elliptic problems with singularities.

**In NeoPZ.** The *mechanisms* exist: per-connect orders (hierarchical [[shape-functions]]), `TPZInterpolatedElement::PRefine`, refinement patterns ([[refinement-hanging-nodes]]), side-order compatibility rules. Whether a full *adaptive driver* (error estimator → marking → refine loop) ships in-library is TBD — `Analysis/pzmganalysis`, gradient reconstruction (Post/), and an `ErrorEstimation` companion repo/branch (`develop-for-ErrorEstimation` branch exists [repo branch list]) suggest drivers live partly downstream. Verify in Phase 4/7 what is actually in-tree at the pin.

**Invariants to check.** Min/max order rules on shared sides; order propagation after PRefine; interaction of p-enrichment with H(div) flavors (`fExtraInternalPOrder` hdiv+/hdiv++ [repo:TPZApproxCreator.h:58]).

**Reference anchors.** Devloo–Oden hp work; Szabó–Babuška; Demkowicz.

Related: [[refinement-hanging-nodes]] · [[error-estimation-convergence]] · [[shape-functions]]
