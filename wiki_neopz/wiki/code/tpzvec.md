# Estruturas de Dados Básicas: TPZVec

Esta página serve como catálogo da estrutura TPZVec do NeoPZ, para a qual **não deve** ser gerado código "inventado". Siga o exemplo de sintaxe abaixo estritamente.

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
