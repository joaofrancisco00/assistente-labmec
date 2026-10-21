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
    PrintResults(cmesh, "poisson2d");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh ────────────────────────────────────────────────────────
TPZGeoMesh *CreateGMesh(int nDiv) {
    constexpr int dim{2};
    // minX/maxX ALWAYS have 3 coordinates, even in 2D (the code hits
    // DebugStop if they have another size)
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};  // size = dim

    // matids needs dim*2 + 1 ids when createBoundEls=true:
    // in 2D that is 5 (1 for the domain + 4 for the boundaries). Passing
    // only {EDomain} hits DebugStop inside NeoPZ.
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
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership of the
    // pointer; creating it on the stack and passing &material crashes
    // on destruction)
    auto *mat = new TPZMatPoisson<STATE>(EDomain, dim);

    // Source term f via std::function (current API). The old API used
    // TPZDummyFunction — do not mix the two.
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Homogeneous Dirichlet boundary condition (type 0)
    // types: 0 = Dirichlet, 1 = Neumann, 2 = Robin
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, EBC, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // Without AutoBuild there is no system at all
    cmesh->AutoBuild();
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
    an.Assemble();  // assembles stiffness + load vector (Solve does NOT assemble)
    an.Solve();
}

// ── Post-processing (VTK for Paraview) ────────────────────────────────────
// TPZMatPoisson field names (see TPZMatPoisson::VariableIndex):
// "Solution" (scalar) and "Derivative" (vector). An unknown name makes
// TPZVTKGenerator hit DebugStop at runtime.
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile) {
    constexpr int vtkRes{1};
    TPZVec<std::string> fields = {"Solution", "Derivative"};
    auto vtk = TPZVTKGenerator(cmesh, fields, plotfile, vtkRes);
    vtk.SetNThreads(nThreads);
    vtk.Do();  // writes <plotfile>.0.vtk
}
