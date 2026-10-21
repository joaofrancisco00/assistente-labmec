// gmsh_reader.cpp — Reference solution: Poisson on a mesh read from a
// Gmsh .msh file with TPZGmshReader.
//
//   Unit square (square.msh, Gmsh 4.1 ASCII), physical groups "domain"
//   (dim 2) and "boundary" (dim 1), -∇²u = 1 with u = 0 on the boundary.
//
// Unlike the other recipes, the material ids are NOT hardcoded: they come
// from the physical names stored in the file, via GetDimNamePhysical() —
// this is how the tutorials (HCurl3D, divfreebubbles, Biot) do it.
//
// Run: ./gmsh_reader [path-to-square.msh]   (default: ./square.msh)

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGmshReader.h"      // TPZGmshReader (reads .msh 3.x and 4.x)
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
#include <iostream>
#include <map>

constexpr int nThreads{4};   // number of threads for assembly and post-processing

TPZGeoMesh *ReadGMesh(const std::string &file, int &domainId, int &bcId);
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder, int domainId, int bcId);
void SolveProblem(TPZLinearAnalysis &an, TPZCompMesh *cmesh);
void PrintResults(TPZCompMesh *cmesh, const std::string &plotfile);

int main(int argc, char *argv[]) {
    const std::string file = (argc > 1) ? argv[1] : "square.msh";
    constexpr int pOrder{2};

    int domainId, bcId;
    TPZGeoMesh *gmesh = ReadGMesh(file, domainId, bcId);
    TPZCompMesh *cmesh = CreateCMesh(gmesh, pOrder, domainId, bcId);
    TPZLinearAnalysis an(cmesh);
    SolveProblem(an, cmesh);
    PrintResults(cmesh, "gmsh_reader");
    delete cmesh;
    delete gmesh;
    return 0;
}

// ── Geometric mesh from the .msh file ─────────────────────────────────────
TPZGeoMesh *ReadGMesh(const std::string &file, int &domainId, int &bcId) {
    TPZGmshReader reader;
    TPZGeoMesh *gmesh = reader.GeometricGmshMesh(file);

    // names[dim][name] = physical tag stored in the file — the reader already
    // used those tags as the material ids of the geometric elements
    auto &names = reader.GetDimNamePhysical();
    for (int d = 0; d < 4; d++) {
        for (const auto &[name, id] : names[d]) {
            std::cout << "physical name: dim " << d << "  \"" << name
                      << "\"  ->  matId " << id << '\n';
        }
    }
    domainId = names[2]["domain"];
    bcId     = names[1]["boundary"];
    return gmesh;
}

// ── Computational mesh + material + boundary ─────────────────────────────
TPZCompMesh *CreateCMesh(TPZGeoMesh *gmesh, int pOrder, int domainId, int bcId) {
    const int dim = gmesh->Dimension();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // continuous H1 approximation

    // Material — ALWAYS on the heap (the mesh takes ownership)
    auto *mat = new TPZMatPoisson<STATE>(domainId, dim);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Homogeneous Dirichlet boundary condition (type 0)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, bcId, 0, val1, val2);
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
