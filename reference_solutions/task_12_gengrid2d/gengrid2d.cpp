// gengrid2d.cpp — Reference solution: 2D Poisson on a structured mesh built
// by TPZGenGrid2D.
//
//   Unit square (quadrilaterals), -∇²u = 1 with u = 0 on the 4 edges.
//
// TPZGenGrid2D is the older structured-mesh generator still used by most
// unit tests (TestReducedSpace, TestHCurl, TestHDivApproxSpaceCreator…).
// Compared to TPZGeoMeshTools::CreateGeoMeshOnGrid it gives per-side
// boundary ids, an element-type switch and refinement patterns.

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGenGrid2D.h"       // TPZGenGrid2D
#include "MMeshType.h"          // MMeshType::EQuadrilateral
#include "pzcmesh.h"            // TPZCompMesh
#include "Poisson/TPZMatPoisson.h"  // TPZMatPoisson<STATE> (current API — family prefix!)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix
#include "pzvec.h"              // TPZVec
#include "TPZVTKGenerator.h"    // TPZVTKGenerator (post-processing to .vtk)
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
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "gengrid2d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh — structured grid via TPZGenGrid2D ─────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    // x0/x1 have 2 coordinates here (x, y) — NOT the 3-coords convention of
    // CreateGeoMeshOnGrid
    const TPZManVector<int, 2> nx = {nDiv, nDiv};
    const TPZManVector<REAL, 2> x0 = {0., 0.};
    const TPZManVector<REAL, 2> x1 = {1., 1.};
    TPZGenGrid2D gen(nx, x0, x1);
    gen.SetElementType(MMeshType::EQuadrilateral);  // or ETriangular

    auto *gmesh = new TPZGeoMesh;
    gen.Read(gmesh, EDomain);  // Read already sets dimension + connectivity

    // Sides 4..7 are the 4 edges of the quadrilateral domain — this is what
    // makes GenGrid2D handy: each side can get its own material id
    for (int side = 4; side < 8; side++) {
        gen.SetBC(gmesh, side, EBC);
    }
    return gmesh;
}

// ── Computational mesh + material + boundary ─────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder) {
    const int dim = gmesh->Dimension();  // 2, set by Read
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership)
    auto *mat = new TPZMatPoisson<STATE>(EDomain, dim);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Homogeneous Dirichlet boundary condition (type 0)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    cmesh->AutoBuild();  // without it the computational mesh stays empty
    return cmesh;
}

// ── Assemble and solve ────────────────────────────────────────────────────
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh) {
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    strmat.SetNumThreads(nThreads);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);  // symmetric system — the standard direct solver
    an.SetSolver(solver);
    an.Assemble();  // Solve does NOT assemble
    an.Solve();
}

// ── Post-processing (VTK for Paraview) ────────────────────────────────────
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Solution", "Derivative"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
