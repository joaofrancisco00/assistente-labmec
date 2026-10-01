// l2projection.cpp — Reference solution: L2 projection with the CURRENT NeoPZ API
//
//   Find u_h in V_h (H1, order p) such that
//   (u_h, v) = (f, v)  for every v in V_h,   f(x,y) = sin(πx)·sin(πy)
//
// Curated reference for the LabMeC assistant: every call below was checked
// against the headers of the snapshot in base_de_dados/neopz.
//
// The program runs a convergence study: for p = 2, the L2 error of the
// projection should decrease with a rate ≈ p+1 = 3 when refining the mesh.
// That rate is the numerical check that the recipe is right (not just that it
// compiles).

#include <cmath>
#include <iostream>

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::EQuadrilateral
#include "pzcmesh.h"            // TPZCompMesh
#include "Projection/TPZL2Projection.h"  // TPZL2Projection<STATE> (the include
                                         // needs the family prefix:
                                         // "Projection/", and NOT
                                         // "Material/Projection/")
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix

// Function to project: f(x,y) = sin(πx)·sin(πy)
static void TargetFunction(const TPZVec<REAL> &x, TPZVec<STATE> &f) {
    f[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
}

// Same function + gradient, for the error computation (ExactSolType signature)
static void ExactSolution(const TPZVec<REAL> &x, TPZVec<STATE> &u,
                          TPZFMatrix<STATE> &du) {
    u[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(0, 0) = M_PI * std::cos(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(1, 0) = M_PI * std::sin(M_PI * x[0]) * std::cos(M_PI * x[1]);
}

// Projects f onto an nDiv×nDiv mesh and returns the error in the L2 norm
static REAL ProjectL2(int nDiv, int pOrder, bool exportVTK) {
    // ── 1. Geometric mesh ────────────────────────────────────────────────
    // A pure L2 projection has no boundary condition: the mass matrix is
    // already symmetric positive definite. Hence createBoundEls = false and
    // matIds has only the domain id (with boundaries, it would be dim*2 + 1 ids).
    constexpr int dim{2};
    constexpr int matIdDomain{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};   // always 3 coordinates
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};   // size = dim
    const TPZManVector<int, 1> matIds = {matIdDomain};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, false);

    // ── 2. H1 computational mesh ─────────────────────────────────────────
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // ── 3. Projection material (on the heap — the mesh takes ownership) ──
    // Constructor: TPZL2Projection(id, dim, nstate = 1).
    // The function to project enters through the material FORCING FUNCTION.
    auto *mat = new TPZL2Projection<STATE>(matIdDomain, dim);
    mat->SetForcingFunction(TargetFunction, pOrder + 2);
    // The exact solution is only needed to compute the error
    mat->SetExactSol(ExactSolution, pOrder + 2);
    cmesh->InsertMaterialObject(mat);

    cmesh->AutoBuild();

    REAL errorL2;
    {
        // ── 4. Assemble and solve (mass matrix: SPD → Cholesky) ──────────
        TPZLinearAnalysis an(cmesh);
        TPZSkylineStructMatrix<STATE> strmat(cmesh);
        an.SetStructuralMatrix(strmat);
        TPZStepSolver<STATE> solver;
        solver.SetDirect(ECholesky);
        an.SetSolver(solver);
        an.Assemble();
        an.Solve();

        // ── 5. Error: [0] = H1 norm, [1] = L2 norm, [2] = H1 seminorm ────
        // The vector MUST arrive with size 3 (= the material NEvalErrors):
        // empty, EvaluateError aborts with "error vector incompatible".
        TPZManVector<REAL, 3> errors(3, 0.);
        an.PostProcessError(errors, false);
        errorL2 = errors[1];

        // ── 6. Post-processing (VTK) — TPZL2Projection variables ─────────
        if (exportVTK) {
            const TPZManVector<std::string, 1> scalnames = {"Solution"};
            const TPZManVector<std::string, 1> vecnames = {"Derivative"};
            an.DefineGraphMesh(dim, scalnames, vecnames, "l2projection.vtk");
            an.PostProcess(1, dim);
        }
    }

    delete cmesh;
    delete gmesh;
    return errorL2;
}

int main() {
    constexpr int pOrder{2};
    const int divisions[] = {4, 8, 16};

    REAL previousError = -1.;
    for (int nDiv : divisions) {
        const REAL error = ProjectL2(nDiv, pOrder, nDiv == 16);
        std::cout << "mesh " << nDiv << "x" << nDiv
                  << "  L2 error = " << error;
        if (previousError > 0.)
            std::cout << "  rate = " << std::log2(previousError / error);
        std::cout << '\n';
        previousError = error;
    }
    return 0;
}
