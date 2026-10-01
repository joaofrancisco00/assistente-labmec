// poisson.cpp — Reference solution: 2D Poisson with the CURRENT NeoPZ API
//
//   -∇²u = f  in [0,1]×[0,1],  u = 0 on the boundary (homogeneous Dirichlet)
//
// Curated reference for the LabMeC assistant: every call below was
// checked against the headers of the snapshot in base_de_dados/neopz
// (real signatures, post-material-refactoring API — NO
// TPZMatLaplacian/TPZDummyFunction, which are the old API).

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::ETriangular
#include "pzcmesh.h"            // TPZCompMesh
#include "Poisson/TPZMatPoisson.h"  // TPZMatPoisson<STATE> (current API — the
                                    // include needs the family prefix:
                                    // plain "TPZMatPoisson.h" does NOT compile)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix

int main() {
    // ── 1. Geometric mesh ────────────────────────────────────────────────
    constexpr int dim{2};
    // minX/maxX ALWAYS have 3 coordinates, even in 2D (the code hits
    // DebugStop if they have another size)
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};  // size = dim

    // matids needs dim*2 + 1 ids when createBoundEls=true:
    // in 2D that is 5 (1 for the domain + 4 for the boundaries). Passing
    // only {1} hits DebugStop inside NeoPZ.
    constexpr int matIdDomain{1};
    constexpr int matIdBoundary{-1};
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
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // ── 3. Material — ALWAYS on the heap (the mesh takes ownership of the
    //      pointer; creating it on the stack and passing &material crashes
    //      on destruction) ────────────────────────────────────────────────
    auto *mat = new TPZMatPoisson<STATE>(matIdDomain, dim);

    // Source term f via std::function (current API). The old API used
    // TPZDummyFunction — do not mix the two.
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Homogeneous Dirichlet boundary condition (type 0) ─────────────
    // types: 0 = Dirichlet, 1 = Neumann, 2 = Robin
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdBoundary, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Build the mesh (without AutoBuild there is no system at all) ──
    cmesh->AutoBuild();

    // ── 6. Analysis: assemble and solve ──────────────────────────────────
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);  // the Laplacian matrix is SPD
    an.SetSolver(solver);
    an.Assemble();  // assembles stiffness + load vector (Solve does NOT assemble)
    an.Solve();

    // ── 7. Post-processing (VTK for Paraview) ────────────────────────────
    // TPZMatPoisson variable names: "Solution" (scalar) and
    // "Derivative" (vector) — see TPZMatPoisson::VariableIndex
    const TPZManVector<std::string, 1> scalnames = {"Solution"};
    const TPZManVector<std::string, 1> vecnames = {"Derivative"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "poisson2d.vtk");
    an.PostProcess(/*resolution=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
