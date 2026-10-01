# Basic Data Structures: TPZVec

This page is a catalog of the NeoPZ TPZVec structure, for which **no** "invented" code should be generated. Follow the syntax example below strictly.

## `TPZVec` (NeoPZ vector)
Template vector class used extensively throughout NeoPZ. It often replaces `std::vector` in the API signatures.

**Header**: `#include "pzvec.h"`

### Usage example
```cpp
#include "pzvec.h"
#include <iostream>

int main() {
    // Initializing a vector of 3 floating-point elements
    TPZVec<REAL> coord(3, 0.0);

    // Accessing the elements (works like a normal array)
    coord[0] = 1.0;
    coord[1] = 2.5;
    coord[2] = -1.0;

    // Iterating over the vector (the size is obtained with .size())
    for (int i = 0; i < coord.size(); i++) {
        std::cout << coord[i] << std::endl;
    }

    return 0;
}
```
