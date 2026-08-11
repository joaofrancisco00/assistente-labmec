// manual_geomesh.cpp — Solução de referência: construção MANUAL de uma malha
// geométrica com elementos triangulares e quadrilaterais.
//
// Ensina o padrão canônico do NeoPZ para criar nós e elementos sem usar os
// helpers (TPZGeoMeshTools::CreateGeoMeshOnGrid, TPZGmshReader, etc.).
// Use este padrão quando precisar de controle total sobre a topologia da malha.
//
// Fluxo:
//   1. new TPZGeoMesh()  →  SetDimension
//   2. NodeVec().AllocateNewElement()  →  [i].Initialize(coords, *gmesh)
//   3. CreateGeoElement(tipo, nodeindices, matid, index)
//   4. BuildConnectivity()
//   5. TPZGeoElBC para criar elementos de contorno

#include "pzgmesh.h"        // TPZGeoMesh
#include "pzgnode.h"        // TPZGeoNode
#include "pzmanvector.h"    // TPZManVector
#include "pzgeoel.h"        // TPZGeoEl
#include "pzgeoelbc.h"      // TPZGeoElBC
#include "pzenumerate.h"    // ETriangle, EQuadrilateral, EOned
#include <iostream>

int main() {
    // ── 1. Criar a malha geométrica e definir a dimensão ──────────────────
    TPZGeoMesh *gmesh = new TPZGeoMesh();
    gmesh->SetDimension(2);

    // ── 2. Alocar e inicializar os nós ────────────────────────────────────
    // Padrão canônico: AllocateNewElement() reserva espaço no ChunkVector e
    // retorna o índice; Initialize() preenche as coordenadas e registra o nó.
    //
    //  5─────6─────7
    //  │  Q  │  T  │   (Q = quadrilátero matId 1, T = triângulo matId 2)
    //  │     │  /  │
    //  0─────1─────2
    //        │  /
    //        3─4    ← nós extras do triângulo inferior (não usados no exemplo
    //                 acima, mantidos para ilustrar padrão multi-elemento)
    //
    // Malha simples: 4 nós, 1 quadrilátero + 1 triângulo compartilhando aresta.
    //
    //  3───2
    //  │ \ │
    //  0───1
    //
    //  Elemento 1 (EQuadrilateral): nós 0-1-2-3
    //  Elemento 2 (ETriangle):      nós 1-2-3   ← triângulo no canto superior

    const int nNodes = 4;
    const TPZManVector<TPZManVector<REAL, 3>, 4> coords = {
        {0., 0., 0.},  // nó 0
        {1., 0., 0.},  // nó 1
        {1., 1., 0.},  // nó 2
        {0., 1., 0.},  // nó 3
    };

    gmesh->NodeVec().Resize(nNodes);
    for (int i = 0; i < nNodes; i++) {
        auto newindex = gmesh->NodeVec().AllocateNewElement();
        gmesh->NodeVec()[newindex].Initialize(coords[i], *gmesh);
    }

    // ── 3. Criar os elementos geométricos ────────────────────────────────
    constexpr int matIdDom{1};
    constexpr int matIdBC{-1};
    int64_t index{-1};

    // Quadrilátero: 4 nós em sentido anti-horário
    TPZManVector<int64_t, 4> quadNodes = {0, 1, 2, 3};
    gmesh->CreateGeoElement(EQuadrilateral, quadNodes, matIdDom, index);

    // Triângulo: 3 nós em sentido anti-horário
    // (compartilha a aresta 1-2 com o quadrilátero acima)
    TPZManVector<int64_t, 3> triNodes = {1, 2, 3};
    gmesh->CreateGeoElement(ETriangle, triNodes, matIdDom, index);

    // ── 4. Construir a conectividade ──────────────────────────────────────
    // OBRIGATÓRIO após inserir todos os elementos — sem isso os vizinhos ficam
    // nulos e a integração numérica não funciona.
    gmesh->BuildConnectivity();

    // ── 5. Criar elementos de contorno via TPZGeoElBC ─────────────────────
    // TPZGeoElBC cria um elemento 1D de contorno num lado (side) de um elemento
    // existente. Os "sides" 1D de um quadrilátero (4 nós) são 4, 5, 6 e 7.
    // Os "sides" 1D de um triângulo (3 nós) são 3, 4 e 5.
    {
        TPZGeoEl *quad = gmesh->Element(0);
        // Lados 1D do quadrilátero: 4=aresta 0-1, 5=1-2, 6=2-3, 7=3-0
        TPZGeoElBC(quad, 4, matIdBC);  // contorno inferior
        TPZGeoElBC(quad, 7, matIdBC);  // contorno esquerdo
    }
    {
        TPZGeoEl *tri = gmesh->Element(1);
        // Lados 1D do triângulo: 3=aresta 1-2, 4=2-3, 5=3-1
        TPZGeoElBC(tri, 5, matIdBC);   // contorno diagonal
    }

    // ── 6. Verificação simples ────────────────────────────────────────────
    std::cout << "Nós:      " << gmesh->NNodes()    << std::endl;
    std::cout << "Elementos:" << gmesh->NElements() << std::endl;

    delete gmesh;
    return 0;
}
