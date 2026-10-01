// darcy_misto.cpp — Reference solution: 2D Darcy in the MIXED formulation
// (H(div) flux + L2 pressure) with the current NeoPZ API.
//
// The mixed formulation requires THREE computational meshes:
//   1. atomic FLUX mesh      — H(div) space, material TPZNullMaterial
//   2. atomic PRESSURE mesh  — L2 (discontinuous) space, TPZNullMaterial
//   3. MULTIPHYSICS mesh     — combines the two, and it is where the real
//      material (TPZMixedDarcyFlow) and the boundary conditions live.
//
// Pattern extracted and verified from UnitTest_PZ/TestHDivCollapsed and
// TPZMultiphysicsCompMesh.h of the NeoPZ snapshot.

#include "pzgmesh.h"                  // TPZGeoMesh
#include "TPZGeoMeshTools.h"          // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"                // MMeshType::EQuadrilateral
#include "pzcmesh.h"                  // TPZCompMesh
#include "TPZMultiphysicsCompMesh.h"  // TPZMultiphysicsCompMesh
#include "TPZNullMaterial.h"          // TPZNullMaterial (atomic meshes)
#include "DarcyFlow/TPZMixedDarcyFlow.h"  // TPZMixedDarcyFlow (current API —
                                          // DarcyFlow/ family prefix)
#include "TPZLinearAnalysis.h"        // TPZLinearAnalysis
#include "pzskylstrmatrix.h"          // TPZSkylineStructMatrix
#include "pzstepsolver.h"             // TPZStepSolver
#include "pzmanvector.h"              // TPZManVector
#include "pzfmatrix.h"                // TPZFMatrix
#include "pzvec.h"                    // TPZVec

constexpr int matIdDomain{1};
constexpr int matIdBoundary{-1};

// ── Atomic FLUX mesh: H(div) space ───────────────────────────────────────
// TPZNullMaterial is only a space marker — the physics lives in the
// multiphysics mesh. The boundary NEEDS a material here: that is where the
// normal-flux degrees of freedom of the boundary live.
TPZCompMesh *CreateFluxMesh(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);

    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDomain, dim, nstate));
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdBoundary, dim - 1, nstate));

    cmesh->SetAllCreateFunctionsHDiv();
    cmesh->SetDefaultOrder(pOrder);
    cmesh->AutoBuild();
    return cmesh;
}

// ── Atomic PRESSURE mesh: L2 space (disconnected elements) ───────────────
// No boundary condition: in the mixed formulation the pressure has no degree
// of freedom on the boundary. SetLagrangeMultiplier(1) sets the assembly
// (condensation) order — without it the solution may fail.
TPZCompMesh *CreatePressureMesh(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDomain, dim, nstate));

    cmesh->SetAllCreateFunctionsContinuous();
    cmesh->ApproxSpace().CreateDisconnectedElements(true);  // L2: continuous PER element
    cmesh->AutoBuild();

    for (int64_t i = 0; i < cmesh->NConnects(); i++) {
        cmesh->ConnectVec()[i].SetLagrangeMultiplier(1);
    }
    return cmesh;
}

int main() {
    // ── 1. Geometric mesh (same recipe as the others) ────────────────────
    constexpr int dim{2};
    constexpr int pOrder{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    const TPZManVector<int, 5> matIds = {matIdDomain, matIdBoundary,
                                         matIdBoundary, matIdBoundary,
                                         matIdBoundary};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral,
        /*createBoundEls=*/true);

    // ── 2. Atomic meshes (H(div) flux + L2 pressure) ─────────────────────
    TPZCompMesh *cmeshFlux     = CreateFluxMesh(gmesh, dim, pOrder);
    TPZCompMesh *cmeshPressure = CreatePressureMesh(gmesh, dim, pOrder);

    // ── 3. Multiphysics mesh: physics + boundary live HERE ───────────────
    gmesh->ResetReference();
    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    auto *mat = new TPZMixedDarcyFlow(matIdDomain, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // source term f = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Boundary in the mixed formulation: type 0 imposes PRESSURE, type 1
    // imposes NORMAL FLUX. Here: zero pressure on the whole boundary.
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // The space style MUST be set to multiphysics BEFORE
    // BuildMultiphysicsSpace — without it, DebugStop in
    // TPZMultiphysicsCompMesh.cpp:94 (found by running this recipe).
    cmesh->SetAllCreateFunctionsMultiphysicElem();

    // Combines the atomic meshes (flux FIRST, pressure second) —
    // replaces AutoBuild for the multiphysics mesh.
    TPZManVector<TPZCompMesh *, 2> meshes = {cmeshFlux, cmeshPressure};
    TPZManVector<int, 2> active = {1, 1};
    cmesh->BuildMultiphysicsSpace(active, meshes);

    // ── 4. Assemble and solve ────────────────────────────────────────────
    // WARNING: the mixed system is a SADDLE POINT (indefinite) problem —
    // ECholesky does NOT work; use ELDLt (or ELU).
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 5. Post-processing (VTK) ─────────────────────────────────────────
    // Real TPZMixedDarcyFlow names (see VariableIndex): "Pressure"
    // (scalar), "Flux" (vector), "DivFlux" (scalar).
    const TPZManVector<std::string, 2> scalnames = {"Pressure", "DivFlux"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_mixed2d.vtk");
    an.PostProcess(/*resolution=*/1, dim);

    delete cmesh;
    delete cmeshFlux;
    delete cmeshPressure;
    delete gmesh;
    return 0;
}
