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
#include "TPZVTKGenerator.h"          // TPZVTKGenerator (post-processing)
#include <string>

enum EMatid { ENone, EDomain, EBC };   // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateFluxMesh(TPZGeoMesh *gmesh, int dim, int pOrder);
TPZCompMesh *CreatePressureMesh(TPZGeoMesh *gmesh, int dim, int pOrder);
TPZMultiphysicsCompMesh *CreateMultiphysicsMesh(TPZGeoMesh *gmesh, int dim, int pOrder,
                                                TPZCompMesh *cmeshFlux,
                                                TPZCompMesh *cmeshPressure);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main() {
    constexpr int dim{2};
    constexpr int pOrder{1};

    TPZGeoMesh *gmesh           = CreateGMesh(8);
    TPZCompMesh *cmeshFlux      = CreateFluxMesh(gmesh, dim, pOrder);
    TPZCompMesh *cmeshPressure  = CreatePressureMesh(gmesh, dim, pOrder);
    TPZMultiphysicsCompMesh *cmesh = CreateMultiphysicsMesh(gmesh, dim, pOrder,
                                                         cmeshFlux, cmeshPressure);

    TPZLinearAnalysis an(cmesh);
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "darcy_mixed2d");

    delete cmesh;
    delete cmeshFlux;
    delete cmeshPressure;
    delete gmesh;
    return 0;
}

// ── Geometric mesh (same recipe as the others) ────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};
    const TPZManVector<int, 5> matIds = {EDomain, EBC, EBC, EBC, EBC};
    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral,
        /*createBoundEls=*/true);
}

// ── Atomic FLUX mesh: H(div) space ───────────────────────────────────────
// TPZNullMaterial is only a space marker — the physics lives in the
// multiphysics mesh. The boundary NEEDS a material here: that is where the
// normal-flux degrees of freedom of the boundary live.
TPZCompMesh *CreateFluxMesh(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);

    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(EDomain, dim, nstate));
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(EBC, dim - 1, nstate));

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
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(EDomain, dim, nstate));

    cmesh->SetAllCreateFunctionsContinuous();
    cmesh->ApproxSpace().CreateDisconnectedElements(true);  // L2: continuous PER element
    cmesh->AutoBuild();

    for (int64_t i = 0; i < cmesh->NConnects(); i++) {
        cmesh->ConnectVec()[i].SetLagrangeMultiplier(1);
    }
    return cmesh;
}

// ── MULTIPHYSICS mesh: physics + boundary live HERE ───────────────────────
TPZMultiphysicsCompMesh *CreateMultiphysicsMesh(TPZGeoMesh *gmesh, int dim, int pOrder,
                                                TPZCompMesh *cmeshFlux,
                                                TPZCompMesh *cmeshPressure) {
    gmesh->ResetReference();
    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    auto *mat = new TPZMixedDarcyFlow(EDomain, dim);
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
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
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
    return cmesh;
}

// ── Assemble and solve ────────────────────────────────────────────────────
// WARNING: the mixed system is a SADDLE POINT (indefinite) problem —
// ECholesky does NOT work; use ELDLt (or ELU).
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh) {
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    strmat.SetNumThreads(nThreads);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();
}

// ── Post-processing (VTK) — pass the MULTIPHYSICS mesh, not an atomic one ─
// Real TPZMixedDarcyFlow names (see VariableIndex): "Pressure" (scalar),
// "Flux" (vector), "DivFlux" (scalar). Unknown names hit DebugStop.
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Pressure", "Flux", "DivFlux"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
