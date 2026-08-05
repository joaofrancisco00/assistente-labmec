// elasticidade.cpp — Solução de referência: elasticidade linear 2D com a
// API ATUAL do NeoPZ.
//
//   Domínio [0,1]×[0,1], estado plano de tensão, peso próprio (fy < 0),
//   engaste (Dirichlet homogêneo) em todo o contorno.
//
// Referência curada para o assistente LabMeC: cada chamada conferida contra
// os headers do snapshot em base_de_dados/neopz. ATENÇÃO à escolha do
// material: em 2D é TPZElasticity2D — TPZElasticity3D é SÓ para 3D e tem
// construtor completamente diferente.

#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::ETriangular
#include "pzcmesh.h"              // TPZCompMesh
#include "Elasticity/TPZElasticity2D.h"  // TPZElasticity2D (API atual — o
                                         // include precisa do prefixo da
                                         // família Elasticity/)
#include "TPZLinearAnalysis.h"    // TPZLinearAnalysis
#include "pzskylstrmatrix.h"      // TPZSkylineStructMatrix
#include "pzstepsolver.h"         // TPZStepSolver
#include "pzmanvector.h"          // TPZManVector
#include "pzfmatrix.h"            // TPZFMatrix
#include "pzvec.h"                // TPZVec
#include <iostream>

int main() {
    // ── 1. Malha geométrica (mesma receita do Poisson 2D) ────────────────
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    constexpr int matIdDominio{1};
    constexpr int matIdContorno{-1};
    // dim*2 + 1 ids com createBoundEls=true (1 domínio + 4 contornos em 2D)
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
    cmesh->SetAllCreateFunctionsContinuous();  // H1 contínuo (deslocamentos)

    // ── 3. Material: TPZElasticity2D (no heap — a malha assume a posse) ──
    // Use SEMPRE o construtor completo, que é o único que inicializa a lei
    // constitutiva (fConstitutiveLaw) — o membro que de fato calcula tensão:
    //     TPZElasticity2D(id, E, nu, fx, fy, planestress)
    // NÃO use o construtor de 1 argumento + SetElasticity: SetElasticity só
    // grava fE_def/fnu_def e NÃO alcança a lei constitutiva. O programa
    // compila, roda, termina com exit 0 e grava o VTK — mas SigmaX/SigmaY
    // saem ZERO em todos os pontos e o deslocamento fica errado, sem nenhum
    // aviso. Descoberto EXECUTANDO esta receita e comparando os campos.
    constexpr STATE E{1000.}, nu{0.3};
    constexpr STATE fx{0.}, fy{-1.};      // peso próprio para baixo
    constexpr int planeStress{1};         // 1 = tensão plana; 0 = deformação plana
    auto *mat = new TPZElasticity2D(matIdDominio, E, nu, fx, fy, planeStress);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Contorno: engaste (Dirichlet homogêneo, tipo 0) ───────────────
    // Elasticidade 2D tem 2 variáveis de estado (ux, uy) — val1 é 2x2 e
    // val2 tem 2 entradas (NÃO 1, como no Poisson escalar!)
    TPZFMatrix<STATE> val1(2, 2, 0.);
    TPZManVector<STATE, 2> val2 = {0., 0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Construir a malha ─────────────────────────────────────────────
    cmesh->AutoBuild();
    std::cout << "Elementos: " << cmesh->NElements()
              << " | Equações: " << cmesh->NEquations() << std::endl;

    // ── 6. Montar e resolver ─────────────────────────────────────────────
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);  // rigidez da elasticidade é SPD
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 7. Pós-processamento (VTK) ───────────────────────────────────────
    // Nomes de variável REAIS do TPZElasticity2D (ver VariableIndex):
    // "Displacement" (vetor), "SigmaX", "SigmaY", "TauXY",
    // "PrincipalStress1", "PrincipalStress2"... — os nomes "Solution" e
    // "Derivative" são do Poisson e NÃO existem aqui.
    const TPZManVector<std::string, 2> scalnames = {"SigmaX", "SigmaY"};
    const TPZManVector<std::string, 1> vecnames = {"Displacement"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "elasticidade2d.vtk");
    an.PostProcess(/*resolucao=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
