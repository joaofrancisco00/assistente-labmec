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
#include <string>

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
#include "pzvec.h"              // TPZVec
#include "TPZVTKGenerator.h"    // TPZVTKGenerator (post-processing to .vtk)

enum EMatid { ENone, EDomain };        // material ids: 0 is never used
constexpr int nThreads{4};             // number of threads for assembly and post-processing

TPZGeoMesh *CreateGMesh(int nDiv);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
REAL ComputeL2Error(TPZLinearAnalysis &an);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

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
    TPZGeoMesh *gmesh = CreateGMesh(nDiv);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder);

    REAL errorL2;
    {
        TPZLinearAnalysis an(cmesh);
        SolveProblem(an, cmesh);
        errorL2 = ComputeL2Error(an);
        if (exportVTK) {
            PrintResults(cmesh, "l2projection");
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

// ── Geometric mesh ────────────────────────────────────────────────────────
// A pure L2 projection has no boundary condition: the mass matrix is
// already symmetric positive definite. Hence createBoundEls = false and
// matIds has only the domain id (with boundaries, it would be dim*2 + 1 ids).
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};   // always 3 coordinates
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};   // size = dim
    const TPZManVector<int, 1> matIds = {EDomain};
    return TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, false);
}

// ── H1 computational mesh + projection material ──────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    constexpr int dim{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // Projection material (on the heap — the mesh takes ownership).
    // Constructor: TPZL2Projection(id, dim, nstate = 1).
    // The function to project enters through the material FORCING FUNCTION.
    auto *mat = new TPZL2Projection<STATE>(EDomain, dim);
    mat->SetForcingFunction(TargetFunction, pOrder + 2);
    // The exact solution is only needed to compute the error
    mat->SetExactSol(ExactSolution, pOrder + 2);
    cmesh->InsertMaterialObject(mat);

    cmesh->AutoBuild();
    return cmesh;
}

// ── Assemble and solve (mass matrix: symmetric → ELDLt) ──────────────────
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

// ── Error: [0] = H1 norm, [1] = L2 norm, [2] = H1 seminorm ────────────────
// The vector MUST arrive with size 3 (= the material NEvalErrors):
// empty, EvaluateError aborts with "error vector incompatible".
REAL ComputeL2Error(TPZLinearAnalysis &an) {
    TPZManVector<REAL, 3> errors(3, 0.);
    an.PostProcessError(errors, false);
    return errors[1];
}

// ── Post-processing (VTK) — TPZL2Projection variables ─────────────────────
// "Solution" (scalar) and "Derivative" (vector) — see VariableIndex.
// Unknown names hit DebugStop inside TPZVTKGenerator.
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Solution", "Derivative"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
