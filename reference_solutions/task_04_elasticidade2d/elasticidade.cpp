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
#include <iostream>

int main() {
    // ── 1. Geometric mesh (same recipe as 2D Poisson) ────────────────────
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

    // ── 2. Computational mesh ────────────────────────────────────────────
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (displacements)

    // ── 3. Material: TPZElasticity2D (on the heap — the mesh takes ownership)
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
    auto *mat = new TPZElasticity2D(matIdDomain, E, nu, fx, fy, planeStress);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Boundary: clamped (homogeneous Dirichlet, type 0) ─────────────
    // 2D elasticity has 2 state variables (ux, uy) — val1 is 2x2 and
    // val2 has 2 entries (NOT 1, as in scalar Poisson!)
    TPZFMatrix<STATE> val1(2, 2, 0.);
    TPZManVector<STATE, 2> val2 = {0., 0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Build the mesh ────────────────────────────────────────────────
    cmesh->AutoBuild();
    std::cout << "Elements: " << cmesh->NElements()
              << " | Equations: " << cmesh->NEquations() << std::endl;

    // ── 6. Assemble and solve ────────────────────────────────────────────
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);  // the elasticity stiffness is SPD
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 7. Post-processing (VTK) ─────────────────────────────────────────
    // REAL variable names of TPZElasticity2D (see VariableIndex):
    // "Displacement" (vector), "SigmaX", "SigmaY", "TauXY",
    // "PrincipalStress1", "PrincipalStress2"... — the names "Solution" and
    // "Derivative" belong to Poisson and do NOT exist here.
    const TPZManVector<std::string, 2> scalnames = {"SigmaX", "SigmaY"};
    const TPZManVector<std::string, 1> vecnames = {"Displacement"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "elasticity2d.vtk");
    an.PostProcess(/*resolution=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
