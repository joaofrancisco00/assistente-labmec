// elasticidade3d.cpp — Reference solution: 3D linear elasticity with the
// CURRENT NeoPZ API.
//
//   Domain [0,1]³, self-weight along -z, clamped (homogeneous Dirichlet)
//   on the whole boundary.
//
// Curated reference for the LabMeC assistant: every call checked against
// the headers of the snapshot in base_de_dados/neopz. MIND the choice of
// material: in 3D it is TPZElasticity3D — the 2D class is ONLY for 2D
// and has a completely different constructor.

#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::EHexahedral
#include "pzcmesh.h"              // TPZCompMesh
#include "Elasticity/TPZElasticity3D.h"  // TPZElasticity3D (current API — the
                                         // include needs the Elasticity/
                                         // family prefix)
#include "TPZLinearAnalysis.h"    // TPZLinearAnalysis
#include "pzskylstrmatrix.h"      // TPZSkylineStructMatrix
#include "pzstepsolver.h"         // TPZStepSolver
#include "pzmanvector.h"          // TPZManVector
#include "pzfmatrix.h"            // TPZFMatrix
#include "pzvec.h"                // TPZVec
#include "TPZVTKGenerator.h"      // TPZVTKGenerator (post-processing to .vtk)
#include <iostream>
#include <string>

enum EMatid { ENone, EDomain, EBC };   // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main() {
    constexpr int pOrder{1};
    TPZGeoMesh *gmesh = CreateGMesh(4);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    TPZLinearAnalysis an(cmesh);
    std::cout << "Elements: " << cmesh->NElements()
              << " | Equations: " << cmesh->NEquations() << std::endl;
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "elasticity3d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh — unit cube, hexahedra ────────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{3};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 1.};
    const TPZManVector<int, 3> nDivs = {nDiv, nDiv, nDiv};   // size = dim
    // dim*2 + 1 = 7 ids in 3D (1 domain + 6 faces) when createBoundEls=true
    const TPZManVector<int, 7> matIds = {EDomain, EBC, EBC, EBC, EBC, EBC, EBC};
    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EHexahedral,
        /*createBoundEls=*/true);
}

// ── Computational mesh + material + boundary ─────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{3};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (displacements)

    // Material: TPZElasticity3D (on the heap — the mesh takes ownership)
    // Constructor is (id, E, nu, TPZVec<STATE> &force) — the body force is a
    // 3-entry vector; there is NO fx/fy or plane-stress flag — that belongs
    // to the 2D material.
    constexpr STATE E{1000.}, nu{0.3};
    TPZManVector<STATE, 3> force = {0., 0., -1.};  // self-weight along -z
    auto *mat = new TPZElasticity3D(EDomain, E, nu, force);
    cmesh->InsertMaterialObject(mat);

    // Boundary: clamped (homogeneous Dirichlet, type 0)
    // 3D elasticity has 3 state variables (ux, uy, uz) — val1 is 3x3 and
    // val2 has 3 entries (NOT 2, as in 2D elasticity!)
    TPZFMatrix<STATE> val1(3, 3, 0.);
    TPZManVector<STATE, 3> val2 = {0., 0., 0.};
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    cmesh->AutoBuild();
    return cmesh;
}

// ── Assemble and solve ────────────────────────────────────────────────────
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh) {
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    strmat.SetNumThreads(nThreads);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);  // the elasticity stiffness is symmetric
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();
}

// ── Post-processing (VTK) ────────────────────────────────────────────────
// REAL field names of TPZElasticity3D (see VariableIndex):
// "Displacement" (vector), "Stress", "Strain" (tensors), "StressX",
// "VonMises", "PrincipalStress"... — "SigmaY"/"TauXY" are 2D names
// and do NOT exist here (unknown names hit DebugStop).
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Displacement", "Stress", "Strain"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
