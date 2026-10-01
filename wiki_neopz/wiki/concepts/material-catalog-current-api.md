# Catalog: which current-API material to use for each problem

NeoPZ material selection guide (current API, post-refactoring). All the
constructors and headers below were checked against the real source code and
**validated by compilation/execution** (reference_solutions/).
General rule: the current materials live in `Material/<Family>/`; everything
in `Material/needrefactor/` is the old API — do not use it in new code.

**INCLUDE RULE**: new-API materials are included WITH the family
prefix — `#include "Poisson/TPZMatPoisson.h"`,
`#include "Elasticity/TPZElasticity2D.h"`,
`#include "DarcyFlow/TPZMixedDarcyFlow.h"`,
`#include "Projection/TPZL2Projection.h"`. The basename alone
(`"TPZMatPoisson.h"`) does NOT compile, and neither does the `Material/` prefix.

## Poisson / Laplace / scalar diffusion (H1)

- **Class**: `TPZMatPoisson<STATE>` — include `"Poisson/TPZMatPoisson.h"`
- **Constructor**: `TPZMatPoisson<STATE>(int id, int dim)`
- **Source term**: `SetForcingFunction(lambda, pOrder)` with
  `std::function<void(const TPZVec<REAL>&, TPZVec<STATE>&)>`
- **Post-processing**: `"Solution"` (scalar), `"Derivative"` (vector)
- 1 state variable → boundary `val2` with 1 entry
- Old names that NO longer exist: `TPZMatLaplacian`, `TPZMatPoisson3d` (legacy)

## L2 projection of a known function (H1)

- **Class**: `TPZL2Projection<STATE>` — include `"Projection/TPZL2Projection.h"`
- **Constructor**: `TPZL2Projection<STATE>(int id, int dim, int nstate = 1)`
- **Function to project**: `SetForcingFunction(lambda, pOrder)` (same signature as Poisson)
- **No boundary condition**: the mass matrix is SPD → `ECholesky`
- **Post-processing**: `"Solution"` (scalar), `"Derivative"` (vector) — see the
  complete L2 projection recipe

## Darcy — three formulations, three classes (do not mix them up)

| Formulation | Class | Space / meshes |
|---|---|---|
| Primal (**H1**) | `TPZDarcyFlow` | continuous H1, **one** mesh |
| Mixed | `TPZMixedDarcyFlow` | H(div) + L2, **three** meshes (multiphysics) |
| Hybridized | `TPZHybridDarcyFlow` | **combined** spaces (hybridization/MHM); inherits from `TPZDarcyFlow`, but does **not** work as the material of a simple H1 mesh |

## H1 Darcy (pressure) — primal formulation

- **Class**: `TPZDarcyFlow` — include `"DarcyFlow/TPZDarcyFlow.h"`
- **Constructor**: `TPZDarcyFlow(int id, int dim)`
- **Permeability**: `SetConstantPermeability(STATE k)` or
  `SetPermeabilityFunction(...)` (inherited from `TPZIsotropicPermeability`)
- **Mesh**: just one, `SetAllCreateFunctionsContinuous()`; solver `ECholesky`
  (SPD) — see the complete H1 Darcy recipe
- **Boundary**: type 0 = imposed pressure, type 1 = imposed normal flux
- **Post-processing**: `"Pressure"`/`"Solution"` (scalar),
  `"Flux"`/`"MinusKGradU"` (vector), `"Derivative"`/`"GradU"`, `"Divergence"`

## Mixed / H(div) Darcy (flux + pressure)

- **Class**: `TPZMixedDarcyFlow` — include `"DarcyFlow/TPZMixedDarcyFlow.h"`
- **Constructor**: `TPZMixedDarcyFlow(int id, int dim)`
- Requires H(div) + L2 approximation spaces (multiphysics mesh — see the
  complete mixed Darcy recipe)
- Legacy old name: `TPZMixedPoisson` → use `TPZMixedDarcyFlow`

## 2D linear elasticity

- **Class**: `TPZElasticity2D` — include `"Elasticity/TPZElasticity2D.h"`
- **Configuration**: use the full constructor
  `TPZElasticity2D(id, E, nu, fx, fy, planestress)` — `planestress` 1 for
  plane stress, 0 for plane strain.
  **DO NOT use** `TPZElasticity2D(id)` + `SetElasticity(E, nu)`: `SetElasticity`
  does not initialize the constitutive law, and the result comes out with `SigmaX`/`SigmaY`
  zeroed and a wrong displacement — compiling and running without any warning.
- **Post-processing**: `"Displacement"`, `"SigmaX"`, `"SigmaY"`, `"TauXY"`,
  `"PrincipalStress1"`, `"PrincipalStress2"`
- 2 state variables → `val1` 2×2 and `val2` with 2 entries on the boundary
- Old name that NO longer exists: `TPZMatElasticity2D`

## 3D linear elasticity

- **Class**: `TPZElasticity3D` — include `"Elasticity/TPZElasticity3D.h"`
- **Constructor**: `TPZElasticity3D(int id, STATE E, STATE poisson, TPZVec<STATE> &force, ...)`
  (the body force is a 3-entry `TPZVec` — a DIFFERENT signature from 2D)
- **Post-processing**: `"Displacement"`, `"StressX"`, `"PrincipalStress"`
- 3 state variables → `val2` with 3 entries
- **3D only** — in a 2D problem use `TPZElasticity2D`

## Rules that apply to all of them

- Material always on the **heap** (`new`) — `InsertMaterialObject` takes ownership.
- Boundary: `mat->CreateBC(mat, matIdBoundary, type, val1, val2)` with type
  `0` = Dirichlet, `1` = Neumann, `2` = Robin; `val2` has as many entries
  as the material has state variables.
- Functions (source, exact solution) via `std::function`/lambda — the
  `TPZDummyFunction` class is the old API, do not use it.
- Mandatory sequence: `InsertMaterialObject` → `AutoBuild()` →
  `Assemble()` → `Solve()`.
