// poisson.cpp — Solução de referência: Poisson 2D com a API ATUAL do NeoPZ
//
//   -∇²u = f  em [0,1]×[0,1],  u = 0 no contorno (Dirichlet homogêneo)
//
// Referência curada para o assistente LabMeC: cada chamada abaixo foi
// conferida contra os headers do snapshot em base_de_dados/neopz
// (assinaturas reais, API pós-refatoração de materiais — NADA de
// TPZMatLaplacian/TPZDummyFunction, que são a API antiga).

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::ETriangular
#include "pzcmesh.h"            // TPZCompMesh
#include "TPZMatPoisson.h"      // TPZMatPoisson<STATE> (API atual, Material/Poisson)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix

int main() {
    // ── 1. Malha geométrica ──────────────────────────────────────────────
    constexpr int dim{2};
    // minX/maxX SEMPRE têm 3 coordenadas, mesmo em 2D (o código dá
    // DebugStop se tiverem outro tamanho)
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};  // tamanho = dim

    // matids precisa de dim*2 + 1 ids quando createBoundEls=true:
    // em 2D são 5 (1 do domínio + 4 dos contornos). Passar só {1} dá
    // DebugStop dentro do NeoPZ.
    constexpr int matIdDominio{1};
    constexpr int matIdContorno{-1};
    const TPZManVector<int, 5> matIds = {matIdDominio, matIdContorno,
                                         matIdContorno, matIdContorno,
                                         matIdContorno};

    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular,
        /*createBoundEls=*/true);

    // ── 2. Malha computacional ───────────────────────────────────────────
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // aproximação H1 contínua

    // ── 3. Material — SEMPRE no heap (a malha assume a posse do ponteiro;
    //      criar na stack e passar &material dá crash na destruição) ──────
    auto *mat = new TPZMatPoisson<STATE>(matIdDominio, dim);

    // Termo fonte f via std::function (API atual). A API antiga usava
    // TPZDummyFunction — não misturar as duas.
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Condição de contorno Dirichlet homogênea (tipo 0) ─────────────
    // tipos: 0 = Dirichlet, 1 = Neumann, 2 = Robin
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Construir a malha (sem AutoBuild não existe sistema algum) ────
    cmesh->AutoBuild();

    // ── 6. Análise: montar e resolver ────────────────────────────────────
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);  // matriz do Laplaciano é SPD
    an.SetSolver(solver);
    an.Assemble();  // monta rigidez + vetor de carga (Solve NÃO monta sozinho)
    an.Solve();

    // ── 7. Pós-processamento (VTK para o Paraview) ───────────────────────
    // Nomes de variável do TPZMatPoisson: "Solution" (escalar) e
    // "Derivative" (vetor) — ver TPZMatPoisson::VariableIndex
    const TPZManVector<std::string, 1> scalnames = {"Solution"};
    const TPZManVector<std::string, 1> vecnames = {"Derivative"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "poisson2d.vtk");
    an.PostProcess(/*resolucao=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
