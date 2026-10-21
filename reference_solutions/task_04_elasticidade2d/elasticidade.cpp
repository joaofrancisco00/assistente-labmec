// elasticidade.cpp — Reference solution: 2D linear elasticity with the
// CURRENT NeoPZ API.
//
//   Domain [0,1]×[0,1], plane stress, self-weight (fy < 0),
//   clamped (homogeneous Dirichlet) on the whole boundary.
//
// Curated reference for the LabMeC assistant: every call checked against
// the headers of the snapshot in base_de_dados/neopz. MIND the choice of
// material: in 2D it is TPZElasticity2D — TPZElasticity3D is ONLY for 3D and
// has a completely different constructor.

#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::ETriangular
#include "pzcmesh.h"              // TPZCompMesh
#include "Elasticity/TPZElasticity2D.h"  // TPZElasticity2D (current API — the
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
    constexpr int pOrder{2};
    TPZGeoMesh *gmesh = CreateGMesh(8);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);
    TPZLinearAnalysis an(cmesh);
    std::cout << "Elements: " << cmesh->NElements()
              << " | Equations: " << cmesh->NEquations() << std::endl;
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "elasticity2d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh (same recipe as 2D Poisson) ────────────────────────────
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

// ── Computational mesh + material + boundary ─────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (displacements)

    // Material: TPZElasticity2D (on the heap — the mesh takes ownership)
    // ALWAYS use the full constructor, which is the only one that initializes
    // the constitutive law (fConstitutiveLaw) — the member that actually
    // computes stress:
    //     TPZElasticity2D(id, E, nu, fx, fy, planestress)
    // DO NOT use the 1-argument constructor + SetElasticity: SetElasticity only
    // stores fE_def/fnu_def and does NOT reach the constitutive law. The
    // program compiles, runs, exits with 0 and writes the VTK — but
    // SigmaX/SigmaY come out ZERO at every point and the displacement is
    // wrong, without any warning. Found by RUNNING this recipe and comparing
    // the fields.
    constexpr STATE E{1000.}, nu{0.3};
    constexpr STATE fx{0.}, fy{-1.};      // self-weight pointing down
    constexpr int planeStress{1};         // 1 = plane stress; 0 = plane strain
    auto *mat = new TPZElasticity2D(EDomain, E, nu, fx, fy, planeStress);
    cmesh->InsertMaterialObject(mat);

    // Boundary: clamped (homogeneous Dirichlet, type 0)
    // 2D elasticity has 2 state variables (ux, uy) — val1 is 2x2 and
    // val2 has 2 entries (NOT 1, as in scalar Poisson!)
    TPZFMatrix<STATE> val1(2, 2, 0.);
    TPZManVector<STATE, 2> val2 = {0., 0.};
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
// REAL field names of TPZElasticity2D (see VariableIndex):
// "Displacement" (vector), "SigmaX", "SigmaY", "TauXY",
// "PrincipalStress1", "PrincipalStress2"... — the names "Solution" and
// "Derivative" belong to Poisson and do NOT exist here (unknown names hit
// DebugStop inside TPZVTKGenerator).
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Displacement", "SigmaX", "SigmaY", "TauXY"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
