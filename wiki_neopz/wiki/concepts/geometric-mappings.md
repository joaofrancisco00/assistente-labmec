---
type: concept
status: draft
updated: 2026-07-02
confidence: medium
evidence-commit: 6ffd38b12
tags:
  - fem
  - neopz
  - geometry
---

# Geometric mappings (master → physical)

**Idea.** Each element is the image of a reference (master) element under a map X(ξ); FE integrals are pulled back via the Jacobian. Linear/multilinear maps for straight elements; higher-order or exact maps for curved geometry.

**In NeoPZ.** Per-topology map classes in `Geom/` (`pzgeom::TPZGeoQuad` etc.) plugged into element templates (`TPZGeoElRefLess<TGeo>`); *blend* maps `tpzgeoblend.h` (transfinite blending of curved boundary reps into element interiors); `SpecialMaps/` exact maps (arc, ellipse, sphere, torus, cylinder, NACA airfoil, quadratic elements). README headline: "non-linear geometrical mappings (curved elements with exact representation)" [repo:README.md:18]. `TPZGeoEl::Jacobian/GradX` deliver the metric; `TestGeometry` (`gradx_tests`) and `TestBlend` (semicircle comparisons) validate [agent].

**Invariants to check (Phase 4).** Jacobian positivity/consistency (axes convention: NeoPZ uses an `axes` frame for gradients — 2D elements embedded in 3D!); blend-map consistency with neighboring exact maps; integration-order adequacy for curved maps ([[quadrature]]); interaction with [[piola-transformations]] for vector spaces on curved elements (Publications/hdivCurved* companion code exists [repo]).

**Reference anchors.** Gordon–Hall blending; Devloo-group curved H(div) paper (hdivCurvedJCompAppMath); Ern–Guermond ch. on geometry.

Related: [[TPZGeoMesh]] · [[topology-module]] · [[piola-transformations]] · [[quadrature]]
