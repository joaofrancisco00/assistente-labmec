# Receita completa: projeção L2 2D com a API atual do NeoPZ

Fluxo canônico para projetar uma função conhecida `f(x,y)` num espaço H1 de
ordem `p`, usando `TPZL2Projection`: encontrar `u_h` tal que
`(u_h, v) = (f, v)` para todo `v` do espaço discreto. Serve para inicializar
uma solução, interpolar dados numa malha ou testar a convergência de um espaço
de aproximação.
(O estado de verificação desta receita está no README do projeto, não aqui:
essa informação é para quem mantém o assistente, não para copiar na resposta.)

**O include leva o prefixo da família, e só ele**:
`#include "Projection/TPZL2Projection.h"`. Nem `"TPZL2Projection.h"` nem
`"Material/Projection/TPZL2Projection.h"` compilam (o NeoPZ propaga como
include path os diretórios de topo, e `Material/` é um deles).

## Passo a passo

1. **Malha geométrica** — `TPZGeoMeshTools::CreateGeoMeshOnGrid(dim, minX, maxX, matIds, nDivs, meshType, createBoundEls)`.
   - Projeção L2 pura **não tem condição de contorno**: a matriz de massa já é simétrica positiva definida. Use `createBoundEls = false` e `matIds` com **um único id** (o do domínio).
   - `minX`/`maxX` sempre com 3 coordenadas, mesmo em 2D; `nDivs` com tamanho `dim`.
2. **Malha computacional** — `TPZCompMesh` + `SetDimModel` + `SetDefaultOrder(p)` + `SetAllCreateFunctionsContinuous()` (H1).
3. **Material** — `new TPZL2Projection<STATE>(matId, dim)` (terceiro argumento opcional: `nstate`, padrão 1). Sempre com `new`: a malha assume a posse.
4. **Função a projetar** — entra pela **forcing function** do material: `SetForcingFunction(func, ordemIntegracao)`, com `func` do tipo `void(const TPZVec<REAL>&, TPZVec<STATE>&)`. Não existe método `SetFunction`/`SetProjection`.
5. **(Opcional) Solução exata para o erro** — `SetExactSol(func, ordemIntegracao)`, com `func` do tipo `void(const TPZVec<REAL>&, TPZVec<STATE>&, TPZFMatrix<STATE>&)` (valor + gradiente).
6. **`cmesh->AutoBuild()`**.
7. **Análise** — `TPZLinearAnalysis` + `TPZSkylineStructMatrix<STATE>` + `TPZStepSolver<STATE>::SetDirect(ECholesky)` (matriz de massa é SPD). `Assemble()` antes de `Solve()`.
8. **Erro** — `an.PostProcessError(erros, false)` com `erros` **já dimensionado com 3 posições**: `[0]` norma H1, `[1]` norma L2, `[2]` seminorma H1.
9. **Pós-processamento** — `DefineGraphMesh(dim, {"Solution"}, {"Derivative"}, "saida.vtk")` + `PostProcess(resolucao, dim)`. Esses são os nomes de variável reais do `TPZL2Projection`.

## Código completo (compilável)

Faz um estudo de convergência: com `p = 2`, o erro L2 da projeção deve cair
com taxa próxima de `p + 1 = 3` a cada refinamento da malha.

```cpp
#include <cmath>
#include <iostream>

#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::EQuadrilateral
#include "pzcmesh.h"            // TPZCompMesh
#include "Projection/TPZL2Projection.h"  // TPZL2Projection<STATE> (prefixo da família!)
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
    // 1. Malha geométrica — sem contorno: um único matId
    constexpr int dim{2};
    constexpr int matIdDominio{1};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {nDiv, nDiv};
    const TPZManVector<int, 1> matIds = {matIdDominio};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::EQuadrilateral, false);

    // 2. Malha computacional H1
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. Material de projeção (no heap — a malha assume a posse)
    auto *mat = new TPZL2Projection<STATE>(matIdDominio, dim);
    mat->SetForcingFunction(FuncaoAlvo, pOrder + 2);   // função a projetar
    mat->SetExactSol(SolucaoExata, pOrder + 2);        // só para o erro
    cmesh->InsertMaterialObject(mat);

    cmesh->AutoBuild();

    REAL erroL2;
    {
        // 4. Montar e resolver (matriz de massa: SPD → Cholesky)
        TPZLinearAnalysis an(cmesh);
        TPZSkylineStructMatrix<STATE> strmat(cmesh);
        an.SetStructuralMatrix(strmat);
        TPZStepSolver<STATE> solver;
        solver.SetDirect(ECholesky);
        an.SetSolver(solver);
        an.Assemble();
        an.Solve();

        // 5. Erro: [0] = norma H1, [1] = norma L2, [2] = seminorma H1
        //    (o vetor PRECISA chegar com tamanho 3)
        TPZManVector<REAL, 3> erros(3, 0.);
        an.PostProcessError(erros, false);
        erroL2 = erros[1];

        // 6. Pós-processamento (VTK)
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
        std::cout << "malha " << nDiv << "x" << nDiv << "  erro L2 = " << erro;
        if (erroAnterior > 0.)
            std::cout << "  taxa = " << std::log2(erroAnterior / erro);
        std::cout << '\n';
        erroAnterior = erro;
    }
    return 0;
}
```

## Erros comuns (armadilhas)

- **`#include "Material/Projection/TPZL2Projection.h"`** — não compila: o prefixo é só a família, `"Projection/TPZL2Projection.h"`.
- **Criar condição de contorno sem necessidade** — a projeção L2 não precisa de BC. Se mesmo assim usar `createBoundEls = true`, `matIds` passa a precisar de `dim*2 + 1` ids (em 2D: 1 do domínio + 4 dos contornos).
- **Procurar um método para "passar a função"** — a função a projetar é a forcing function (`SetForcingFunction`). Sem ela, o material projeta a solução constante passada no construtor (zero por padrão).
- **`PostProcessError` com vetor vazio** — `TPZManVector<REAL,3> erros;` tem tamanho 0 e aborta com *"error vector incompatible with material"*. Dimensione com `erros(3, 0.)`.
- **Confundir com `TPZMatPoisson`** — projeção L2 resolve a matriz de massa `(u, v)`, não a rigidez `(∇u, ∇v)`. Para `-∇²u = f`, ver a receita de Poisson.
- **Material na stack** — `TPZL2Projection<STATE> mat(...); cmesh->InsertMaterialObject(&mat);` dá crash na destruição da malha. Sempre `new`.
