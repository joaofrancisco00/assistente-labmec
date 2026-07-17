# Receita completa: elasticidade linear 2D com a API atual do NeoPZ

Fluxo canônico para elasticidade linear 2D (estado plano de tensão ou
deformação) com Dirichlet, usando a **API atual**. Cada chamada foi conferida
contra os headers reais do NeoPZ. O esqueleto (malha → cmesh → material →
contorno → AutoBuild → Assemble → Solve) é o mesmo da receita do Poisson 2D —
o que muda é o material e tudo que decorre de a solução ser vetorial.

## Escolha do material — o erro mais comum

- **2D → `TPZElasticity2D`** (`Material/Elasticity/TPZElasticity2D.h`)
- **3D → `TPZElasticity3D`** — NÃO usar em problemas 2D; além da física
  errada, o construtor é diferente: `TPZElasticity3D(id, E, nu, TPZVec<STATE> &force)`.
- Construtor real do 2D: `TPZElasticity2D(int id, STATE E, STATE nu, STATE fx, STATE fy, int planestress = 1)`
  — `E` = módulo de Young, `nu` = Poisson, `fx`/`fy` = força de corpo,
  `planestress`: `1` = tensão plana, `0` = deformação plana.
  Alternativa: `TPZElasticity2D(id)` + `SetElasticity(E, nu)`.

## Diferenças em relação ao Poisson escalar

1. **2 variáveis de estado** (ux, uy): na condição de contorno, `val1` é
   `TPZFMatrix<STATE>(2, 2, 0.)` e `val2` tem **2 entradas** (`{0., 0.}`) —
   tamanho 1 é erro.
2. **Pós-processamento**: os nomes de variável são do material —
   `"Displacement"` (vetor), `"SigmaX"`, `"SigmaY"`, `"TauXY"`,
   `"PrincipalStress1"`, `"PrincipalStress2"`, `"MaxStress"`.
   `"Solution"`/`"Derivative"` são do Poisson e **não existem** aqui.
3. **Força de corpo** entra no construtor (`fx`, `fy`) — não precisa de
   `SetForcingFunction` para carga constante.

## Código completo (compilável)

```cpp
#include "pzgmesh.h"              // TPZGeoMesh
#include "TPZGeoMeshTools.h"      // TPZGeoMeshTools::CreateGeoMeshOnGrid
#include "MMeshType.h"            // MMeshType::ETriangular
#include "pzcmesh.h"              // TPZCompMesh
#include "TPZElasticity2D.h"      // TPZElasticity2D (API atual)
#include "TPZLinearAnalysis.h"    // TPZLinearAnalysis
#include "pzskylstrmatrix.h"      // TPZSkylineStructMatrix
#include "pzstepsolver.h"         // TPZStepSolver
#include "pzmanvector.h"          // TPZManVector
#include "pzfmatrix.h"            // TPZFMatrix
#include "pzvec.h"                // TPZVec

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

    // 3. Material 2D (no heap — a malha assume a posse)
    constexpr STATE E{1000.}, nu{0.3};
    constexpr STATE fx{0.}, fy{-1.};  // peso próprio
    auto *mat = new TPZElasticity2D(matIdDominio, E, nu, fx, fy, 1);
    cmesh->InsertMaterialObject(mat);

    // 4. Engaste em todo o contorno (Dirichlet, tipo 0) — val2 com 2 entradas
    TPZFMatrix<STATE> val1(2, 2, 0.);
    TPZManVector<STATE, 2> val2 = {0., 0.};
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

    // 7. Pós-processamento (VTK) — nomes de variável do TPZElasticity2D
    const TPZManVector<std::string, 2> scalnames = {"SigmaX", "SigmaY"};
    const TPZManVector<std::string, 1> vecnames = {"Displacement"};
    an.DefineGraphMesh(dim, scalnames, vecnames, "elasticidade2d.vtk");
    an.PostProcess(1, dim);

    delete cmesh;
    delete gmesh;
    return 0;
}
```

## Erros comuns

- **`TPZElasticity3D` em problema 2D** — classe existe, compila o nome, mas é
  a física errada e o construtor é outro. Em 2D, sempre `TPZElasticity2D`.
- **`TPZElasticity2D(id, dim)`** — esse construtor NÃO existe; o segundo
  argumento não é dimensão, ver assinatura real acima.
- **`val2` com 1 entrada** no `CreateBC` — elasticidade 2D tem 2 variáveis de
  estado; `val2 = {0., 0.}`.
- **`"Solution"`/`"Derivative"` no `DefineGraphMesh`** — são nomes do Poisson;
  aqui é `"Displacement"`, `"SigmaX"` etc.
- **`TPZMatElasticity2D`** — nome antigo, não existe mais; hoje é
  `TPZElasticity2D`.
- **Material na stack / esquecer `AutoBuild` / `Solve` sem `Assemble`** —
  mesmas armadilhas da receita do Poisson.
