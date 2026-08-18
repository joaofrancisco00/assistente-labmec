# Utilitários Matemáticos: Regra de Integração (TPZInt1d)

Esta página serve como catálogo da estrutura TPZInt1d do NeoPZ, para a qual **não deve** ser gerado código "inventado" com métodos não suportados.

## `TPZInt1d`
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
    TPZVec<REAL> pos(1); // Em 1D a coordenada paramétrica ocupa 1 espaço
    REAL weight;
    
    for (int ip = 0; ip < npoints; ip++) {
        // O método .Point() carrega as posições paramétricas e o peso
        regra.Point(ip, pos, weight);
        std::cout << "Ponto " << ip << ": ksi = " << pos[0] << ", w = " << weight << std::endl;
    }
    
    return 0;
}
```
