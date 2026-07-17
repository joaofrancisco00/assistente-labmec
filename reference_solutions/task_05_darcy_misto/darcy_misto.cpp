// darcy_misto.cpp — Solução de referência: Darcy 2D na formulação MISTA
// (fluxo H(div) + pressão L2) com a API atual do NeoPZ.
//
// A formulação mista exige TRÊS malhas computacionais:
//   1. malha atômica de FLUXO    — espaço H(div), material TPZNullMaterial
//   2. malha atômica de PRESSÃO  — espaço L2 (descontínuo), TPZNullMaterial
//   3. malha MULTIFÍSICA         — combina as duas, e é nela que vive o
//      material de verdade (TPZMixedDarcyFlow) e as condições de contorno.
//
// Padrão extraído e verificado de UnitTest_PZ/TestHDivCollapsed e
// TPZMultiphysicsCompMesh.h do snapshot do NeoPZ.

#include "pzgmesh.h"                  // TPZGeoMesh
#include "TPZGeoMeshTools.h"          // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"                // MMeshType::EQuadrilateral
#include "pzcmesh.h"                  // TPZCompMesh
#include "TPZMultiphysicsCompMesh.h"  // TPZMultiphysicsCompMesh
#include "TPZNullMaterial.h"          // TPZNullMaterial (malhas atômicas)
#include "TPZMixedDarcyFlow.h"        // TPZMixedDarcyFlow (API atual)
#include "TPZLinearAnalysis.h"        // TPZLinearAnalysis
#include "pzskylstrmatrix.h"          // TPZSkylineStructMatrix
#include "pzstepsolver.h"             // TPZStepSolver
#include "pzmanvector.h"              // TPZManVector
#include "pzfmatrix.h"                // TPZFMatrix
#include "pzvec.h"                    // TPZVec

constexpr int matIdDominio{1};
constexpr int matIdContorno{-1};

// ── Malha atômica de FLUXO: espaço H(div) ────────────────────────────────
// TPZNullMaterial é só um marcador de espaço — a física fica na multifísica.
// O contorno PRECISA de material aqui: é nele que vivem os graus de
// liberdade de fluxo normal da fronteira.
TPZCompMesh *CriarMalhaFluxo(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);

    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDominio, dim, nstate));
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdContorno, dim - 1, nstate));

    cmesh->SetAllCreateFunctionsHDiv();
    cmesh->SetDefaultOrder(pOrder);
    cmesh->AutoBuild();
    return cmesh;
}

// ── Malha atômica de PRESSÃO: espaço L2 (elementos desconectados) ────────
// Sem condição de contorno: pressão não tem grau de liberdade na fronteira
// na formulação mista. SetLagrangeMultiplier(1) define a ordem de montagem
// (condensação) — sem isso a resolução pode falhar.
TPZCompMesh *CriarMalhaPressao(TPZGeoMesh *gmesh, int dim, int pOrder) {
    gmesh->ResetReference();
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    constexpr int nstate{1};
    cmesh->InsertMaterialObject(new TPZNullMaterial<>(matIdDominio, dim, nstate));

    cmesh->SetAllCreateFunctionsContinuous();
    cmesh->ApproxSpace().CreateDisconnectedElements(true);  // L2: contínuo POR elemento
    cmesh->AutoBuild();

    for (int64_t i = 0; i < cmesh->NConnects(); i++) {
        cmesh->ConnectVec()[i].SetLagrangeMultiplier(1);
    }
    return cmesh;
}

int main() {
    // ── 1. Malha geométrica (mesma receita das demais) ───────────────────
    constexpr int dim{2};
    constexpr int pOrder{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    const TPZManVector<int, 5> matIds = {matIdDominio, matIdContorno,
                                         matIdContorno, matIdContorno,
                                         matIdContorno};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral,
        /*createBoundEls=*/true);

    // ── 2. Malhas atômicas (fluxo H(div) + pressão L2) ───────────────────
    TPZCompMesh *cmeshFluxo   = CriarMalhaFluxo(gmesh, dim, pOrder);
    TPZCompMesh *cmeshPressao = CriarMalhaPressao(gmesh, dim, pOrder);

    // ── 3. Malha multifísica: física + contorno moram AQUI ───────────────
    gmesh->ResetReference();
    auto *cmesh = new TPZMultiphysicsCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);

    auto *mat = new TPZMixedDarcyFlow(matIdDominio, dim);
    mat->SetConstantPermeability(1.);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // termo fonte f = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // Contorno na formulação mista: tipo 0 impõe PRESSÃO, tipo 1 impõe
    // FLUXO NORMAL. Aqui: pressão nula em toda a fronteira.
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // Combina as malhas atômicas (fluxo PRIMEIRO, pressão depois) —
    // substitui o AutoBuild da malha multifísica.
    TPZManVector<TPZCompMesh *, 2> malhas = {cmeshFluxo, cmeshPressao};
    TPZManVector<int, 2> ativas = {1, 1};
    cmesh->BuildMultiphysicsSpace(ativas, malhas);

    // ── 4. Montar e resolver ─────────────────────────────────────────────
    // ATENÇÃO: o sistema misto é de PONTO DE SELA (indefinido) —
    // ECholesky NÃO funciona; usar ELDLt (ou ELU).
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ELDLt);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 5. Pós-processamento (VTK) ───────────────────────────────────────
    // Nomes reais do TPZMixedDarcyFlow (ver VariableIndex): "Pressure"
    // (escalar), "Flux" (vetor), "DivFlux" (escalar).
    const TPZManVector<std::string, 2> scalnames = {"Pressure", "DivFlux"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_misto2d.vtk");
    an.PostProcess(/*resolucao=*/1, dim);

    delete cmesh;
    delete cmeshFluxo;
    delete cmeshPressao;
    delete gmesh;
    return 0;
}
