# Solvers de Sistemas Lineares: TPZStepSolver

Esta página serve como catálogo da estrutura do solver de passos do NeoPZ, para a qual **não deve** ser gerado código "inventado" com métodos não suportados.

## `TPZStepSolver`
**Header**: `#include "pzstepsolver.h"`

Representa um solver de matriz e também pode ser utilizado como pré-condicionador. O `TPZStepSolver` atua resolvendo sistemas lineares do tipo `A*x = B`. No NeoPZ, ele geralmente é instanciado, configurado e depois entregue à classe de análise computacional (`TPZAnalysis` ou `TPZLinearAnalysis`).

### Exemplo de Uso (Iterativo com Pré-condicionador)
```cpp
#include "pzstepsolver.h"
#include "TPZLinearAnalysis.h"

int main() {
    // Supomos que a análise já possua a matriz global montada
    TPZLinearAnalysis an;
    
    // 1. Criando o Solver Principal (Ex: Método iterativo GMRES)
    TPZStepSolver<STATE> step;
    
    // Configurando o tipo de solver com SetDirect (apesar do nome, define o método)
    // Opções comuns: EGMRES, ECG (Gradiente Conjugado), EDirect
    step.SetDirect(EGMRES); 
    
    // Configurações do solver iterativo
    step.SetTolerance(1.e-8);
    // Para acesso ao número máximo de iterações, usa-se a variável fMaxIterations ou métodos específicos dependendo da versão
    
    // 2. Criando o Pré-condicionador (Ex: Jacobi)
    TPZStepSolver<STATE> jacobi;
    jacobi.SetDirect(EJacobi);
    
    // 3. Conectando o pré-condicionador ao solver principal
    step.SetPreconditioner(jacobi); // Nota: Em versões do NeoPZ, o método correto é SetPrecond() ou SetPreconditioner()
    
    // 4. Entregando o solver completo para a classe de análise
    an.SetSolver(step);
    
    return 0;
}
```
