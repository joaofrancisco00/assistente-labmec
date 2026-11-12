# TPZManVector — API card

Generated from `Util/pzmanvector.h` — do not edit by hand.

Include: `"Util/pzmanvector.h"` (no código: #include "Util/pzmanvector.h")

Public methods (exact declarations from the header):
- `explicit TPZManVector(const int64_t size = 0)`
- `TPZManVector(const int64_t size, const T& copy)`
- `TPZManVector(const TPZVec<T> & copy)`
- `TPZManVector(const std::initializer_list<T>& list)`
- `TPZManVector(const TPZManVector< T, NumExtAlloc >& copy)`
- `TPZManVector(TPZManVector< T, NumExtAlloc >&& copy)`
- `virtual ~TPZManVector()`
- `TPZManVector< T, NumExtAlloc >& operator=(const TPZManVector< T, NumExtAlloc >& copy)`
- `TPZManVector< T, NumExtAlloc >& operator=(TPZManVector< T, NumExtAlloc >&& copy)`
- `TPZManVector< T, NumExtAlloc >& operator=(const std::initializer_list<T>& list)`
- `void Expand(const int64_t newsize)`
- `void Shrink()`
- `virtual void Resize(const int64_t newsize, const T& object) override`
- `virtual void Resize(const int64_t newsize) override`

Does NOT exist (common mistakes):
- No constructor takes 3+ element values in parentheses `TPZManVector<REAL, 3> v(x, y, z)` — use brace initializer list `TPZManVector<REAL, 3> v = {x, y, z};` or `TPZManVector<REAL, 3> v(3, 0.0);`.
