# TPZGeoElSide — API card

Generated from `Mesh/pzgeoelside.h` — do not edit by hand.

Include: `"pzgeoelside.h"` (in C++ code: `#include "pzgeoelside.h"`)

Public methods (exact declarations from the header):
- `~TPZGeoElSideIndex()`
- `TPZGeoElSideIndex()`
- `TPZGeoElSideIndex(TPZGeoEl *gel,int side)`
- `TPZGeoElSideIndex(int64_t gelindex,int side)`
- `TPZGeoElSideIndex(const TPZGeoElSide &side)`
- `TPZGeoElSideIndex(const TPZGeoElSideIndex &cp)`
- `TPZGeoElSideIndex * Clone()`
- `TPZGeoElSideIndex &operator= (const TPZGeoElSideIndex &A )`
- `operator bool() const`
- `bool operator==(const TPZGeoElSideIndex &copy)`
- `int Side() const`
- `void SetSide(int side)`
- `TPZGeoEl *Element(const TPZGeoMesh *mesh) const`
- `void SetElement(TPZGeoEl* geoel)`
- `int64_t ElementIndex() const`
- `void SetElementIndex(int64_t i)`
- `int ClassId() const override`
- `void Read(TPZStream &buf, void *context) override`
- `void Write(TPZStream &buf, int withclassid) const override`
