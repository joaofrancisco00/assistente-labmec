# Receita completa: Poisson 2D com a API atual do NeoPZ

Fluxo canônico para resolver `-∇²u = f` num retângulo com condição de
Dirichlet, usando a **API atual** (pós-refatoração de materiais). Use este
exemplo como esqueleto para qualquer problema H1 escalar.
(O estado de verificação desta receita está no README do projeto, não aqui:
essa informação é para quem mantém o assistente, não para copiar na resposta.)

**Include de material da API nova leva o prefixo da família**:
`#include "Poisson/TPZMatPoisson.h"` — só `"TPZMatPoisson.h"` NÃO compila
(o NeoPZ propaga como include path apenas os diretórios de topo, e os
materiais novos ficam em subpastas de `Material/`).

## Passo a passo

1. **Malha geométrica** — `TPZGeoMeshTools::CreateGeoMeshOnGrid(dim, minX, maxX, matIds, nDivs, meshType, createBoundEls)`.
   - `minX`/`maxX` **sempre** com 3 coordenadas, mesmo em 2D.
   - `nDivs` com tamanho igual a `dim`.
   - `matIds` precisa de `dim*2 + 1` ids quando `createBoundEls=true` (em 2D: 1 do domínio + 4 dos contornos). Passar só um id dá `DebugStop`.
2. **Malha computacional** — `TPZCompMesh` + `SetDimModel` + `SetDefaultOrder` + `SetAllCreateFunctionsContinuous()` (H1 contínuo).
3. **Material** — `TPZMatPoisson<STATE>` (include `"Poisson/TPZMatPoisson.h"` — com o prefixo da família!). Sempre criado com `new`: a malha assume a posse do ponteiro.
4. **Termo fonte** — `SetForcingFunction(lambda, pOrder)` com `std::function<void(const TPZVec<REAL>&, TPZVec<STATE>&)>`.
5. **Condição de contorno** — `mat->CreateBC(mat, matIdContorno, tipo, val1, val2)` e inserir o retorno na malha. Tipos: `0` = Dirichlet, `1` = Neumann, `2` = Robin.
6. **`cmesh->AutoBuild()`** — sem isso a malha computacional fica vazia.
7. **Análise** — `TPZLinearAnalysis` + `TPZSkylineStructMatrix<STATE>` + `TPZStepSolver<STATE>::SetDirect(ECholesky)`. Chamar `Assemble()` **antes** de `Solve()` — `Solve()` não monta o sistema sozinho.
8. **Pós-processamento** — `DefineGraphMesh(dim, {"Solution"}, {"Derivative"}, "saida.vtk")` + `PostProcess(resolucao, dim)`. Esses são os nomes de variável reais do `TPZMatPoisson`.

## Código completo (compilável)

```cpp
#include "pzgmesh.h"            // TPZGeoMesh
#include "TPZGeoMeshTools.h"    // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"          // MMeshType::ETriangular
#include "pzcmesh.h"            // TPZCompMesh
#include "Poisson/TPZMatPoisson.h"  // TPZMatPoisson<STATE> (API atual — prefixo da família!)
#include "TPZLinearAnalysis.h"  // TPZLinearAnalysis
#include "pzskylstrmatrix.h"    // TPZSkylineStructMatrix
#include "pzstepsolver.h"       // TPZStepSolver
#include "pzmanvector.h"        // TPZManVector
#include "pzfmatrix.h"          // TPZFMatrix

int main() {
    // 1. Malha geométrica
    constexpr int dim{2};
    const TPZManVector<REAL, 3> minX = {0., 0., 0.};
    const TPZManVector<REAL, 3> maxX = {1., 1., 0.};
    const TPZManVector<int, 2> nDivs = {8, 8};
    constexpr int matIdDominio{1};
    constexpr int matIdContorno{-1};
    const TPZManVector<int, 5> matIds = {matIdDominio, matIdContorno,
                                         matIdContorno, matIdContorno,
                                         matIdContorno};
    TPZGeoMesh *gmesh = TPZGeoMeshTools::CreateGeoMeshOnGrid(
        dim, minX, maxX, matIds, nDivs, MMeshType::ETriangular, true);

    // 2. Malha computacional
    constexpr int pOrder{2};
    auto *cmesh = new TPZCompMesh(gmesh);
    cmesh->SetDimModel(dim);
    cmesh->SetDefaultOrder(pOrder);
    cmesh->SetAllCreateFunctionsContinuous();

    // 3. Material (no heap — a malha assume a posse)
    auto *mat = new TPZMatPoisson<STATE>(matIdDominio, dim);
    mat->SetForcingFunction(
        [](const TPZVec<REAL> &loc, TPZVec<STATE> &result) {
            result[0] = 1.;  // f(x,y) = 1
        },
        pOrder);
    cmesh->InsertMaterialObject(mat);

    // 4. Condição de contorno Dirichlet homogênea (tipo 0)
    TPZFMatrix<STATE> val1(1, 1, 0.);
    TPZManVector<STATE, 1> val2 = {0.};
    auto *bnd = mat->CreateBC(mat, matIdContorno, 0, val1, val2);
    cmesh->InsertMaterialObject(bnd);

    // 5. Construir a malha
    cmesh->AutoBuild();

    // 6. Montar e resolver
    TPZLinearAnalysis an(cmesh);
    TPZSkylineStructMatrix<STATE> strmat(cmesh);
    an.SetStructuralMatrix(strmat);
    TPZStepSolver<STATE> solver;
    solver.SetDirect(ECholesky);
    an.SetSolver(solver);
    an.Assemble();
    an.Solve();

    // 7. Pós-processamento (VTK)
    const TPZManVector<std::string, 1> scalnames = {"Solution"};
    const TPZManVector<std::string, 1> vecnames = {"Derivative"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "poisson2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Erros comuns (API antiga e armadilhas)

- **`TPZMatLaplacian` não existe mais** — foi substituída por `TPZMatPoisson` na refatoração de materiais. Para formulações mistas/fluxo, ver `TPZDarcyFlow` e `TPZMixedDarcyFlow`.
- **`TPZDummyFunction` é da API antiga** — a API atual usa `std::function` direto em `SetForcingFunction`/`SetExactSol`. Não misturar as duas.
- **Material na stack** — `TPZMatPoisson<STATE> material(...); cmesh->InsertMaterialObject(&material);` dá crash na destruição da malha. Sempre `new`.
- **`matIds` com tamanho errado** em `CreateGeoMeshOnGrid` — precisa de `dim*2 + 1` ids com `createBoundEls=true`.
- **Esquecer `AutoBuild()`** — a malha computacional fica vazia e a análise não tem o que montar.
- **Chamar `Solve()` sem `Assemble()`** — o sistema nunca é montado.
- **`#include "NeoPZ.h"`** — não existe header único no NeoPZ; cada classe tem o seu.
- **`#include "TPZMatPoisson.h"` sem o prefixo `Poisson/`** — não compila; os
  materiais da API nova vivem em subpastas de `Material/` e o include leva o
  nome da família.
