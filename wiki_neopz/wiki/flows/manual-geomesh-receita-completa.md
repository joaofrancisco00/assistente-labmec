# Receita: Construção Manual de Malha Geométrica (TPZGeoMesh)

## Quando usar este padrão

Use a **construção manual** de malha quando precisar de **controle total** sobre a
topologia: geometrias irregulares, malhas de elemento único para teste, híbridas, ou
quando nenhuma das ferramentas de geração automática serve.

Para malhas estruturadas regulares prefira `TPZGeoMeshTools::CreateGeoMeshOnGrid`;
para malhas externas use `TPZGmshReader`.

---

## Headers necessários

```cpp
#include "pzgmesh.h"      // TPZGeoMesh
#include "pzgnode.h"      // TPZGeoNode
#include "pzmanvector.h"  // TPZManVector
#include "pzgeoel.h"      // TPZGeoEl
#include "pzgeoelbc.h"    // TPZGeoElBC
#include "pzenumerate.h"  // ETriangle, EQuadrilateral, EOned, ETetraedro, …
```

---

## Passo a passo

### 1. Criar a malha e definir a dimensão

```cpp
TPZGeoMesh *gmesh = new TPZGeoMesh();
gmesh->SetDimension(2);   // 1, 2 ou 3
```

### 2. Alocar e inicializar os nós

> **NUNCA** instancie `TPZGeoNode` diretamente e tente empurrar com `PushBack` —
> o `TPZAdmChunkVector` não tem `PushBack`. O padrão correto é:

```cpp
// Pré-aloca espaço (opcional mas evita realocações)
gmesh->NodeVec().Resize(nNodes);

TPZManVector<REAL, 3> coord(3, 0.);
coord[0] = x;  coord[1] = y;  coord[2] = z;

auto idx = gmesh->NodeVec().AllocateNewElement(); // retorna int64_t
gmesh->NodeVec()[idx].Initialize(coord, *gmesh);  // registra o nó
```

`Initialize(coord, mesh)` gera um id único automaticamente e amarra o nó à malha.

#### Exemplo: 4 nós de um quadrado unitário

```cpp
const int nNodes = 4;
gmesh->NodeVec().Resize(nNodes);

const TPZManVector<TPZManVector<REAL,3>, 4> coords = {
    {0., 0., 0.},   // nó 0
    {1., 0., 0.},   // nó 1
    {1., 1., 0.},   // nó 2
    {0., 1., 0.},   // nó 3
};

for (int i = 0; i < nNodes; i++) {
    auto newindex = gmesh->NodeVec().AllocateNewElement();
    gmesh->NodeVec()[newindex].Initialize(coords[i], *gmesh);
}
```

### 3. Criar os elementos geométricos

Use `gmesh->CreateGeoElement(tipo, nodeIndices, matId, index)`:

| Tipo           | Enum NeoPZ        | Nós |
|----------------|-------------------|-----|
| Triângulo      | `ETriangle`       | 3   |
| Quadrilátero   | `EQuadrilateral`  | 4   |
| Segmento 1D    | `EOned`           | 2   |
| Tetraedro      | `ETetraedro`      | 4   |
| Prisma         | `EPrisma`         | 6   |
| Cubo           | `ECube`           | 8   |
| Ponto          | `EPoint`          | 1   |

```cpp
int64_t index{-1};  // preenchido pela função

// Quadrilátero (nós 0-1-2-3, anti-horário)
TPZManVector<int64_t, 4> quadNodes = {0, 1, 2, 3};
gmesh->CreateGeoElement(EQuadrilateral, quadNodes, /*matid=*/1, index);

// Triângulo (nós 1-2-3, anti-horário)
TPZManVector<int64_t, 3> triNodes = {1, 2, 3};
gmesh->CreateGeoElement(ETriangle, triNodes, /*matid=*/1, index);
```

> **Atenção — tipo do elemento:** O primeiro argumento de `CreateGeoElement` é
> sempre um valor do enum `MElementType` (ex: `ETriangle`, `EQuadrilateral`,
> `EOned`, `ETetraedro`). **Nunca** use:
> - `new TPZTriangle` — cria a topologia pura, não um elemento de malha
> - `TPZTriangle::ClassId()` — retorna o id de serialização, não o tipo geométrico
> - `TPZTriangle::Type()` — correto apenas em contexto template; prefira o enum direto
>
> O enum `ETriangle` já está disponível ao incluir `pzenumerate.h` (ou indiretamente
> via `pzgmesh.h`).

### 4. Construir a conectividade

```cpp
// OBRIGATÓRIO após inserir todos os elementos.
// Sem isso, os vizinhos ficam nulos e a integração numérica falha.
gmesh->BuildConnectivity();
```

### 5. Criar elementos de contorno

`TPZGeoElBC` cria um elemento filho no lado (`side`) de um elemento pai e
registra-o automaticamente na malha:

```cpp
TPZGeoEl *quad = gmesh->Element(0);
// Lados 1D de um quadrilátero 4 nós: side 4=aresta 0-1, 5=1-2, 6=2-3, 7=3-0
TPZGeoElBC(quad, 4, /*matIdBC=*/-1);  // contorno inferior
TPZGeoElBC(quad, 7, /*matIdBC=*/-1);  // contorno esquerdo

TPZGeoEl *tri = gmesh->Element(1);
// Lados 1D de um triângulo 3 nós: side 3=1-2, 4=2-3, 5=3-1
TPZGeoElBC(tri, 5, /*matIdBC=*/-1);
```

---

## Exemplo completo mínimo

```cpp
#include "pzgmesh.h"
#include "pzgnode.h"
#include "pzmanvector.h"
#include "pzgeoel.h"
#include "pzgeoelbc.h"
#include "pzenumerate.h"

int main() {
    TPZGeoMesh *gmesh = new TPZGeoMesh();
    gmesh->SetDimension(2);

    // Nós
    const int nNodes = 4;
    gmesh->NodeVec().Resize(nNodes);
    const TPZManVector<TPZManVector<REAL,3>,4> coords = {
        {0.,0.,0.}, {1.,0.,0.}, {1.,1.,0.}, {0.,1.,0.}
    };
    for (int i = 0; i < nNodes; i++) {
        auto idx = gmesh->NodeVec().AllocateNewElement();
        gmesh->NodeVec()[idx].Initialize(coords[i], *gmesh);
    }

    // Elementos
    int64_t index{-1};
    TPZManVector<int64_t,4> quadNodes = {0,1,2,3};
    gmesh->CreateGeoElement(EQuadrilateral, quadNodes, 1, index);

    TPZManVector<int64_t,3> triNodes = {1,2,3};
    gmesh->CreateGeoElement(ETriangle, triNodes, 1, index);

    gmesh->BuildConnectivity();

    // Contorno
    TPZGeoElBC(gmesh->Element(0), 4, -1);  // aresta 0-1

    delete gmesh;
    return 0;
}
```

---

## Armadilhas comuns

| Erro                                            | Causa                                                                             | Correção                                                    |
|-------------------------------------------------|-----------------------------------------------------------------------------------|-------------------------------------------------------------|
| `TPZAdmChunkVector` has no `PushBack`           | Tentativa de usar `NodeVec().PushBack()`                                          | Use `AllocateNewElement()` + `Initialize()`                 |
| `TPZTriangle` not declared in scope             | Incluiu `tpztriangle.h` esperando uma classe de elemento de malha                | Use `ETriangle` (enum) em `CreateGeoElement`                |
| `no matching function` em `CreateGeoElement`    | Passou `TPZTriangle::ClassId()` (int de serialização) como tipo do elemento       | Use o enum direto: `ETriangle`, `EQuadrilateral`, etc.      |
| Vizinhos nulos em tempo de execução             | Esqueceu `BuildConnectivity()`                                                    | Chame sempre após todos os `CreateGeoElement`               |
| Nó com coordenadas erradas                      | Usou `SetCoord` em vez de `Initialize` (não amarra o nó à malha corretamente)    | Use sempre `Initialize(coord, *gmesh)` para novos nós       |
