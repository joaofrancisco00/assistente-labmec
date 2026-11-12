# Basic Data Structures: TPZVec

This page is a catalog of the NeoPZ TPZVec structure, for which **no** "invented" code should be generated. Follow the syntax example below strictly.

## `TPZVec` and `TPZManVector` (NeoPZ vectors)
Template vector classes used extensively throughout NeoPZ. `TPZManVector<T, N>` pre-allocates `N` elements on the stack and grows dynamically if needed.

**Headers**: `#include "pzvec.h"` (`TPZVec`), `#include "pzmanvector.h"` (`TPZManVector`)

> **CRITICAL — Constructor signatures**:
> - `TPZManVector<T, N>(int64_t size = 0)` — allocates `size` elements
> - `TPZManVector<T, N>(int64_t size, const T &copy)` — allocates `size` elements initialized to `copy`
> - `TPZManVector<T, N> v = {a, b, c};` — `std::initializer_list<T>` (use braces `{...}`, **NEVER** parentheses `v(a, b, c)` with 3+ arguments!)

### Usage example
```cpp
#include "pzmanvector.h"
#include "pzvec.h"
#include <iostream>

int main() {
    // 1. Initialize with size and default value (at most 2 constructor arguments!)
    TPZVec<REAL> coord(3, 0.0);

    // 2. Or initialize directly with a brace-enclosed initializer list
    TPZManVector<REAL, 3> point = {1.0, 2.5, -1.0};

    // Accessing the elements (works like a normal array)
    coord[0] = point[0];
    coord[1] = point[1];
    coord[2] = point[2];

    // Iterating over the vector (the size is obtained with .size())
    for (int i = 0; i < coord.size(); i++) {
        std::cout << coord[i] << std::endl;
    }

    return 0;
}
```
