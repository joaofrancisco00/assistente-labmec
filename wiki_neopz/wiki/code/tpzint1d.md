# Mathematical Utilities: Integration Rule (TPZInt1d)

This page is a catalog of the TPZInt1d structure of NeoPZ, for which **no** "invented" code with unsupported methods should be generated.

## `TPZInt1d`
**Header**: `#include "pzquad.h"`

Provides an integration rule for 1D (line) elements. It **does not have** methods such as `Integrate()`, `Contribute()` or `SetMesh()`. Its only methods focus on extracting the weight and the spatial coordinates of each integration point.

### Usage example
```cpp
#include "pzquad.h"
#include "pzvec.h"
#include <iostream>

int main() {
    // Instantiating a 1D integration rule
    // The constructor takes the desired polynomial order
    int order = 2;
    TPZInt1d rule(order);

    // Getting the number of integration points with .NPoints()
    int npoints = rule.NPoints();

    // Extracting the weight and coordinate of each point
    TPZVec<REAL> pos(1); // in 1D the parametric coordinate takes 1 entry
    REAL weight;

    for (int ip = 0; ip < npoints; ip++) {
        // .Point() loads the parametric positions and the weight
        rule.Point(ip, pos, weight);
        std::cout << "Point " << ip << ": ksi = " << pos[0] << ", w = " << weight << std::endl;
    }

    return 0;
}
```
