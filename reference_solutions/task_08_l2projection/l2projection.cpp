// l2projection.cpp — Solução de referência: projeção L2 com a API ATUAL do NeoPZ
//
//   Encontrar u_h em V_h (H1, ordem p) tal que
//   (u_h, v) = (f, v)  para todo v em V_h,   f(x,y) = sin(πx)·sin(πy)
//
// Referência curada para o assistente LabMeC: cada chamada abaixo foi
// conferida contra os headers do snapshot em base_de_dados/neopz.
//
// O programa faz um estudo de convergência: para p = 2, o erro L2 da projeção
// deve cair com taxa ≈ p+1 = 3 ao refinar a malha. Essa taxa é a verificação
// numérica de que a receita está certa (não só de que compila).

#include <cmath>
#include <iostream>

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::EQuadrilateral
#include "pzcmesh.h"            // TPZCompMesh
#include "Projection/TPZL2Projection.h"  // TPZL2Projection<STATE> (o include
                                         // precisa do prefixo da família:
                                         // "Projection/", e NÃO
                                         // "Material/Projection/")
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix

// Função a projetar: f(x,y) = sin(πx)·sin(πy)
static void FuncaoAlvo(const TPZVec<REAL> &x, TPZVec<STATE> &f) {
    f[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
}

// Mesma função + gradiente, para o cálculo do erro (assinatura ExactSolType)
static void SolucaoExata(const TPZVec<REAL> &x, TPZVec<STATE> &u,
                         TPZFMatrix<STATE> &du) {
    u[0] = std::sin(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(0, 0) = M_PI * std::cos(M_PI * x[0]) * std::sin(M_PI * x[1]);
    du(1, 0) = M_PI * std::sin(M_PI * x[0]) * std::cos(M_PI * x[1]);
}

// Projeta f numa malha nDiv×nDiv e devolve o erro na norma L2
static REAL ProjetarL2(int nDiv, int pOrder, bool exportarVTK) {
    // ── 1. Malha geométrica ──────────────────────────────────────────────
    // Projeção L2 pura não tem condição de contorno: a matriz de massa já é
    // simétrica positiva definida. Por isso createBoundEls = false e matIds
    // tem só o id do domínio (com contornos, seriam dim*2 + 1 ids).
    constexpr int dim{2};
    constexpr int matIdDominio{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};   // sempre 3 coordenadas
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};   // tamanho = dim
    const TPZManVector<int, 1> matIds = {matIdDominio};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, false);

    // ── 2. Malha computacional H1 ────────────────────────────────────────
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // ── 3. Material de projeção (no heap — a malha assume a posse) ──────
    // Construtor: TPZL2Projection(id, dim, nstate = 1).
    // A função a projetar entra pela FORCING FUNCTION do material.
    auto *mat = new TPZL2Projection<STATE>(matIdDominio, dim);
    mat->SetForcingFunction(FuncaoAlvo, pOrder + 2);
    // Solução exata só é necessária para calcular o erro
    mat->SetExactSol(SolucaoExata, pOrder + 2);
    cmesh->InsertMaterialObject(mat);

    cmesh->AutoBuild();

    REAL erroL2;
    {
        // ── 4. Montar e resolver (matriz de massa: SPD → Cholesky) ───────
        TPZLinearAnalysis an(cmesh);
        TPZSkylineStructMatrix<STATE> strmat(cmesh);
        an.SetStructuralMatrix(strmat);
        TPZStepSolver<STATE> solver;
        solver.SetDirect(ECholesky);
        an.SetSolver(solver);
        an.Assemble();
        an.Solve();

        // ── 5. Erro: [0] = norma H1, [1] = norma L2, [2] = seminorma H1 ──
        // O vetor PRECISA chegar com tamanho 3 (= NEvalErrors do material):
        // vazio, o EvaluateError aborta com "error vector incompatible".
        TPZManVector<REAL, 3> erros(3, 0.);
        an.PostProcessError(erros, false);
        erroL2 = erros[1];

        // ── 6. Pós-processamento (VTK) — variáveis do TPZL2Projection ────
        if (exportarVTK) {
            const TPZManVector<std::string, 1> scalnames = {"Solution"};
            const TPZManVector<std::string, 1> vecnames = {"Derivative"};
            an.DefineGraphMesh(dim, scalnames, vecnames, "l2projection.vtk");
            an.PostProcess(1, dim);
        }
    }

    delete cmesh;
    delete gmesh;
    return erroL2;
}

int main() {
    constexpr int pOrder{2};
    const int divisoes[] = {4, 8, 16};

    REAL erroAnterior = -1.;
    for (int nDiv : divisoes) {
        const REAL erro = ProjetarL2(nDiv, pOrder, nDiv == 16);
        std::cout << "malha " << nDiv << "x" << nDiv
                  << "  erro L2 = " << erro;
        if (erroAnterior > 0.)
            std::cout << "  taxa = " << std::log2(erroAnterior / erro);
        std::cout << '\n';
        erroAnterior = erro;
    }
    return 0;
}
