# Complete recipe: read a Gmsh .msh mesh and solve Poisson on it

Canonical flow for using an **external mesh file** instead of a generator:
`TPZGmshReader` reads the `.msh`, the physical group names become the
material ids, and a standard Poisson problem is solved on top. This is the
pattern the tutorials (`HCurl3D`, `divfreebubbles`, `Biot`, `LearningPZ`)
use for real geometries.

## Step by step

1. **The file** — `TPZGmshReader` supports **msh format 3.x and 4.x only**
   (`GeometricGmshMesh` dispatches on the version; a 2.2 file hits
   `DebugStop`). The bundled `square.msh` is 4.1 ASCII with physical groups
   `"domain"` (dim 2) and `"boundary"` (dim 1).
2. **Read** — `TPZGmshReader reader; TPZGeoMesh *gmesh = reader.GeometricGmshMesh(file);`.
   The mesh elements already carry the **physical tags as material ids**.
3. **Name → id map** — `reader.GetDimNamePhysical()` returns
   `TPZManVector<std::map<std::string,int>,4>`: `names[dim][name]` is the id.
   Fill it **after** `GeometricGmshMesh` (the read populates it). Loop over
   `names[d]` to print the map, like the tutorials do.
   - There is **no `enum EMatid` here**: the ids come from the file. (The
     alternative is `reader.SetDimNamePhysical(map)` to override the ids
     with your own before reading.)
4. **Computational mesh** — `TPZCompMesh` + `SetDimModel(gmesh->Dimension())`
   + `SetDefaultOrder` + `SetAllCreateFunctionsContinuous()`; material and
   BC use the ids read from the file (`names[2]["domain"]`,
   `names[1]["boundary"]`).
5. **Analysis / post-processing** — same skeleton as the Poisson recipe:
   `ELDLt`, `SetNumThreads`, `TPZVTKGenerator` with `"Solution"`/`"Derivative"`.

## How to run

```bash
./gmsh_reader                          # reads ./square.msh
./gmsh_reader /path/to/other.msh       # any 3.x/4.x file
```

The binary takes the mesh path as `argv[1]` (default `square.msh` in the
current directory).

## Complete code (compilable)

```cpp
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
```

## Common mistakes

- **Hardcoding material ids** — the ids are the physical tags stored in the
  file; read them via `GetDimNamePhysical()` after `GeometricGmshMesh`,
  or pin them yourself with `SetDimNamePhysical` before reading.
- **Reading a msh 2.2 file** — `TPZGmshReader` supports only 3.x/4.x;
  re-export with `gmsh -format msh41` or
  `gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)`.
- **Expecting an `enum EMatid`** — unlike the generator-based recipes there
  is no fixed enum: the names/ids travel with the file.
- **Forgetting the domain depends on the file's dim** — use
  `gmesh->Dimension()` for the material and `SetDimModel`, do not assume 2.
- **`CreateGeoMeshOnGrid` arguments transplanted here** — `matIds`/`minX`/
  `maxX`/`nDivs` belong to the structured generator, not to `TPZGmshReader`.
- **Material on the stack / forgetting `AutoBuild` / `Solve` without
  `Assemble`** — same pitfalls as the Poisson recipe.
