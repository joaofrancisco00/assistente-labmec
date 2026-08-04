// darcy_h1.cpp — Solução de referência: fluxo de Darcy 2D na formulação
// PRIMAL (espaço H1, pressão como única incógnita).
//
//   -∇·(K ∇p) = f  em [0,1]×[0,1],  p = 0 no contorno
//
// Estruturalmente idêntico ao Poisson 2D (mesmo esqueleto H1, malha única) —
// o que muda é o material e a permeabilidade. NÃO confundir com:
//   TPZMixedDarcyFlow  → formulação mista (H(div)+L2, 3 malhas, multifísica)
//   TPZHybridDarcyFlow → formulação hibridizada (espaços COMBINADOS); herda
//                        de TPZDarcyFlow, mas não é o material de uma malha
//                        H1 simples.

#include "pzgmesh.h"                // TPZGeoMesh
#include "TPZGeoMeshTools.h"        // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"              // MMeshType::ETriangular
#include "pzcmesh.h"                // TPZCompMesh
#include "DarcyFlow/TPZDarcyFlow.h" // TPZDarcyFlow (H1 — prefixo da família!)
#include "TPZLinearAnalysis.h"      // TPZLinearAnalysis
#include "pzskylstrmatrix.h"        // TPZSkylineStructMatrix
#include "pzstepsolver.h"           // TPZStepSolver
#include "pzmanvector.h"            // TPZManVector
#include "pzfmatrix.h"              // TPZFMatrix
#include "pzvec.h"                  // TPZVec

int main() {
    // ── 1. Malha geométrica ──────────────────────────────────────────────
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

    // ── 2. Malha computacional — UMA malha, espaço H1 ────────────────────
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();  // H1 contínuo (pressão)

    // ── 3. Material (no heap — a malha assume a posse) ───────────────────
    auto *mat = new TPZDarcyFlow(matIdDominio, dim);
    // Permeabilidade K (de TPZIsotropicPermeability). Para K variável no
    // espaço existe SetPermeabilityFunction.
    mat->SetConstantPermeability(1.);
    // Termo fonte f
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // ── 4. Contorno ──────────────────────────────────────────────────────
    // Em H1 a incógnita é a pressão: tipo 0 = Dirichlet (pressão imposta),
    // tipo 1 = Neumann (fluxo normal imposto). 1 variável de estado → val2
    // com 1 entrada.
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // ── 5. Construir a malha ─────────────────────────────────────────────
    cmesh->AutoBuild();
    std::cout << "Elementos: " << cmesh->NElements()
              << " | Equações: " << cmesh->NEquations() << std::endl;

    // ── 6. Montar e resolver ─────────────────────────────────────────────
    // Sistema H1 é SPD (diferente da formulação mista, que é ponto de sela
    // e exige ELDLt) → ECholesky serve.
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // ── 7. Pós-processamento (VTK) ───────────────────────────────────────
    // Nomes reais do TPZDarcyFlow (ver VariableIndex): "Pressure"/"Solution"
    // (escalar), "Flux"/"MinusKGradU" (vetor, = -K∇p), "Derivative"/"GradU",
    // "Divergence", "NormKDu".
    const TPZManVector<std::string, 1> scalnames = {"Pressure"};
    const TPZManVector<std::string, 1> vecnames = {"Flux"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "darcy_h1_2d.vtk");
    an.PostProcess(/*resolucao=*/1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
