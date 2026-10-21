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
#include "TPZVTKGenerator.h"        // TPZVTKGenerator (post-processing)
#include <iostream>
#include <string>

enum EMatid { ENone, EDomain, EBC };   // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main() {
    constexpr int pOrder{2};
    TPZGeoMesh *gmesh = CreateGMesh(8);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    TPZLinearAnalysis an(cmesh);
    std::cout << "Elements: " << cmesh->NElements()
              << " | Equations: " << cmesh->NEquations() << std::endl;
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "darcy_h1_2d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh ────────────────────────────────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};
    // dim*2 + 1 ids with createBoundEls=true (1 domain + 4 boundaries in 2D)
    const TPZManVector<int, 5> matIds = {EDomain, EBC, EBC, EBC, EBC};

    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular,
        /*createBoundEls=*/true);
}

// ── Computational mesh + material + boundary — ONE mesh, H1 space ─────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (pressure)

    // Material (on the heap — the mesh takes ownership)
    auto *mat = new TPZDarcyFlow(EDomain, dim);
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

    // Boundary: in H1 the unknown is the pressure — type 0 = Dirichlet
    // (imposed pressure), type 1 = Neumann (imposed normal flux).
    // 1 state variable → val2 with 1 entry.
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    cmesh->AutoBuild();
    return cmesh;
}

// ── Assemble and solve ────────────────────────────────────────────────────
// The H1 system is SPD (unlike the mixed formulation, which is a saddle
// point and REQUIRES ELDLt) — we still use ELDLt as the standard direct
// solver for symmetric systems.
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

// ── Post-processing (VTK) ────────────────────────────────────────────────
// Real TPZDarcyFlow names (see VariableIndex): "Pressure"/"Solution"
// (scalar), "Flux"/"MinusKGradU" (vector, = -K∇p), "Derivative"/"GradU",
// "Divergence", "NormKDu". Unknown names hit DebugStop.
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Pressure", "Flux"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
