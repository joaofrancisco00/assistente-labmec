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
#include <iostream>

int main() {
    // ── 1. Geometric mesh — unit cube, hexahedra ─────────────────────────
    constexpr int dim{3};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 1.};
    const TPZManVector<int, 3> nDivs = {4, 4, 4};   // size = dim
    constexpr int matIdDomain{1};
    constexpr int matIdBoundary{-1};
    // dim*2 + 1 = 7 ids in 3D (1 domain + 6 faces) when createBoundEls=true
    const TPZManVector<int, 7> matIds = {matIdDomain, matIdBoundary, matIdBoundary,
                                         matIdBoundary, matIdBoundary, matIdBoundary,
                                         matIdBoundary};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EHexahedral,
        /*createBoundEls=*/true);

    // ── 2. Computational mesh ────────────────────────────────────────────
    constexpr int pOrder{1};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 (displacements)

    // ── 3. Material: TPZElasticity3D (on the heap — the mesh takes ownership)
    // Constructor is (id, E, nu, TPZVec<STATE> &force) — the body force is a
    // 3-entry vector; there is NO fx/fy or plane-stress flag — that belongs
    // to the 2D material.
    constexpr STATE E{1000.}, nu{0.3};
    TPZManVector<STATE, 3> force = {0., 0., -1.};  // self-weight along -z
    auto *mat = new TPZElasticity3D(matIdDomain, E, nu, force);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Boundary: clamped (homogeneous Dirichlet, type 0) ─────────────
    // 3D elasticity has 3 state variables (ux, uy, uz) — val1 is 3x3 and
    // val2 has 3 entries (NOT 2, as in 2D elasticity!)
    TPZFMatrix<STATE> val1(3, 3, 0.);
    TPZManVector<STATE, 3> val2 = {0., 0., 0.};
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
    // REAL variable names of TPZElasticity3D (see VariableIndex):
    // "Displacement" (vector), "StressX", "StressY", "StressZ",
    // "VonMises", "PrincipalStress"... — "SigmaY"/"TauXY" are 2D names
    // and do NOT exist here.
    const TPZManVector<std::string, 2> scalnames = {"StressX", "VonMises"};
    const TPZManVector<std::string, 1> vecnames = {"Displacement"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "elasticity3d.vtk");
    an.PostProcess(/*resolution=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
