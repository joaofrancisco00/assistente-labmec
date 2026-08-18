# Utilitários Matemáticos e Estruturas de Dados Básicas

Esta página serve como catálogo das estruturas matemáticas fundamentais do NeoPZ, para as quais **não deve** ser gerado código "inventado". Siga os exemplos de sintaxe abaixo estritamente.

## `TPZVec` (Vetor do NeoPZ)
Classe template de vetor utilizada extensivamente ao longo do NeoPZ. Substitui frequentemente o `std::vector` nas assinaturas da API.

**Header**: `#include "pzvec.h"`

### Exemplo de Uso
```cpp
#include "pzvec.h"
#include <iostream>

int main() {
    // Inicializando um vetor de 3 elementos de ponto flutuante
    TPZVec<REAL> coord(3, 0.0);
    
    // Acessando os elementos (funciona como um array normal)
    coord[0] = 1.0;
    coord[1] = 2.5;
    coord[2] = -1.0;
    
    // Iterando sobre o vetor (tamanho é obtido com .size())
    for (int i = 0; i < coord.size(); i++) {
        std::cout << coord[i] << std::endl;
    }
    
    return 0;
}
```

---

## Regras de Integração (`TPZIntPoints`)
Módulo responsável por fornecer pontos e pesos de integração (ex: Quadratura de Gauss) para os elementos finitos. As classes derivam de `TPZIntPoints`. As mais comuns são `TPZInt1d` (linhas), `TPZIntQuad` (quadriláteros) e `TPZIntTriang` (triângulos).

### `TPZInt1d`
**Header**: `#include "pzquad.h"`

Fornece regra de integração para elementos 1D (linha). **Não possui** métodos como `Integrate()`, `Contribute()` ou `SetMesh()`. Seus únicos métodos focam em extrair o peso e as coordenadas espaciais do ponto de integração.

### Exemplo de Uso
```cpp
#include "pzquad.h"
#include "pzvec.h"
#include <iostream>

int main() {
    // Instanciando uma regra de integração 1D
    // O construtor geralmente aceita a ordem polinomial desejada
    int order = 2;
    TPZInt1d regra(order);
    
    // Obtendo o número de pontos de integração com .NPoints()
    int npoints = regra.NPoints();
    
    // Extraindo peso e coordenada de cada ponto
    TPZVec<REAL> pos(1); // Em 1D a coordenada x ocupa 1 espaço no TPZVec
    REAL weight;
    
    for (int ip = 0; ip < npoints; ip++) {
        // O método .Point() carrega as posições paramétricas e o peso
        regra.Point(ip, pos, weight);
        std::cout << "Ponto " << ip << ": x = " << pos[0] << ", w = " << weight << std::endl;
    }
    
    return 0;
}
```
