# Condições de Contorno: TPZBndCond

Esta página serve como catálogo da estrutura de Condições de Contorno do NeoPZ, para a qual **não deve** ser gerado código "inventado" com métodos não suportados.

## `TPZBndCond`
**Header**: `#include "TPZBndCond.h"`

Representa as condições de contorno de um problema de elementos finitos no NeoPZ.
No NeoPZ, um objeto de condição de contorno **nunca** é instanciado diretamente usando `new TPZBndCond`. Ele sempre é gerado pelo material daquele domínio, utilizando o método `CreateBC()`.

### Exemplo de Uso (Dirichlet e Neumann)
```cpp
#include "TPZBndCond.h"
#include "Poisson/TPZMatPoisson.h" // Exemplo de material que gera o BC
#include "pzvec.h"
#include "pzfmatrix.h"

int main() {
    // 1. Instanciando o material (domínio principal)
    int mat_id = 1;
    int dim = 2;
    auto *material = new TPZMatPoisson<STATE>(mat_id, dim);
    
    // 2. Parâmetros da Condição de Contorno
    int bc_id = -1; // ID do contorno geométrico
    
    // Tipos comuns:
    // 0 = Dirichlet (Valor imposto da função)
    // 1 = Neumann (Valor imposto da derivada/fluxo)
    int typeDirichlet = 0; 
    
    // Matrizes de valores
    TPZFMatrix<STATE> val1(1, 1, 0.0); // Usado em condições do tipo Robin (mista)
    TPZVec<STATE> val2(1, 10.0);       // O valor escalar imposto (ex: temperatura = 10.0)
    
    // 3. O Material é quem CRIA o objeto TPZBndCond
    TPZBndCondT<STATE> *bnd = material->CreateBC(material, bc_id, typeDirichlet, val1, val2);
    
    return 0;
}
```
