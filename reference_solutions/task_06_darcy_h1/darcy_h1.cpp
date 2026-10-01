// darcy_h1.cpp — Reference solution: 2D Darcy flow in the PRIMAL
// formulation (H1 space, pressure as the only unknown).
//
//   -∇·(K ∇p) = f  in [0,1]×[0,1],  p = 0 on the boundary
//
// Structurally identical to 2D Poisson (same H1 skeleton, single mesh) —
// what changes is the material and the permeability. DO NOT confuse with:
//   TPZMixedDarcyFlow  → mixed formulation (H(div)+L2, 3 meshes, multiphysics)
//   TPZHybridDarcyFlow → hybridized formulation (COMBINED spaces); it inherits
//                        from TPZDarcyFlow, but it is not the material of a
//                        simple H1 mesh.

#include "pzgmesh.h"                // TPZGeoMesh
#include "TPZGeoMeshTools.h"        // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"              // MMeshType::ETriangular
#include "pzcmesh.h"                // TPZCompMesh
#include "DarcyFlow/TPZDarcyFlow.h" // TPZDarcyFlow (H1 — family prefix!)
#include "TPZLinearAnalysis.h"      // TPZLinearAnalysis
#include "pzskylstrmatrix.h"        // TPZSkylineStructMatrix
#include "pzstepsolver.h"           // TPZStepSolver
#include "pzmanvector.h"            // TPZManVector
#include "pzfmatrix.h"              // TPZFMatrix
#include "pzvec.h"                  // TPZVec

int main() {
    // ── 1. Geometric mesh ────────────────────────────────────────────────
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    constexpr int matIdDomain{1};
    constexpr int matIdBoundary{-1};
    // dim*2 + 1 ids with createBoundEls=true (1 domain + 4 boundaries in 2D)
    const TPZManVector<int, 5> matIds = {matIdDomain, matIdBoundary,
                                         matIdBoundary, matIdBoundary,
                                         matIdBoundary};

    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular,
        /*createBoundEls=*/true);

    // ── 2. Computational mesh — ONE mesh, H1 space ───────────────────────
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (pressure)

    // ── 3. Material (on the heap — the mesh takes ownership) ─────────────
    auto *mat = new TPZDarcyFlow(matIdDomain, dim);
    // Permeability K (from TPZIsotropicPermeability). For a spatially
    // varying K there is SetPermeabilityFunction.
    mat->SetConstantPermeability(1.);
    // Source term f
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Boundary ──────────────────────────────────────────────────────
    // In H1 the unknown is the pressure: type 0 = Dirichlet (imposed pressure),
    // type 1 = Neumann (imposed normal flux). 1 state variable → val2
    // with 1 entry.
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Build the mesh ────────────────────────────────────────────────
    cmesh->AutoBuild();
    std::cout << "Elements: " << cmesh->NElements()
              << " | Equations: " << cmesh->NEquations() << std::endl;

    // ── 6. Assemble and solve ────────────────────────────────────────────
    // The H1 system is SPD (unlike the mixed formulation, which is a saddle
    // point and requires ELDLt) → ECholesky works.
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 7. Post-processing (VTK) ─────────────────────────────────────────
    // Real TPZDarcyFlow names (see VariableIndex): "Pressure"/"Solution"
    // (scalar), "Flux"/"MinusKGradU" (vector, = -K∇p), "Derivative"/"GradU",
    // "Divergence", "NormKDu".
    const TPZManVector<std::string, 1> scalnames = {"Pressure"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_h1_2d.vtk");
    an.PostProcess(/*resolution=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
