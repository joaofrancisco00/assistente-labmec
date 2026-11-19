# TPZMultiphysicsCompMesh — API card

Generated from `Mesh/TPZMultiphysicsCompMesh.h` — do not edit by hand.

Include: `"TPZMultiphysicsCompMesh.h"` (in C++ code: `#include "TPZMultiphysicsCompMesh.h"`)

Public methods (exact declarations from the header):
- `TPZMultiphysicsCompMesh()`
- `TPZMultiphysicsCompMesh(TPZGeoMesh * gmesh, bool isComplex=false)`
- `TPZMultiphysicsCompMesh(TPZAutoPointer<TPZGeoMesh> gmesh, bool isComplex=false)`
- `TPZMultiphysicsCompMesh(const TPZMultiphysicsCompMesh &other)`
- `TPZMultiphysicsCompMesh & operator=(const TPZMultiphysicsCompMesh &other)`
- `~TPZMultiphysicsCompMesh()`
- `virtual void AutoBuild() override`
- `void BuildMultiphysicsSpace(TPZVec<int> & active_approx_spaces, const TPZVec<TPZCompMesh * > & mesh_vector)`
- `virtual void BuildMultiphysicsSpace()`
- `virtual void BuildMultiphysicsSpace(TPZVec<TPZCompMesh * > & mesh_vector)`
- `virtual void BuildMultiphysicsSpace(TPZVec<TPZCompMesh * > & mesh_vector, const TPZVec<int64_t> &gelindexes)`
- `virtual void BuildMultiphysicsSpace(const TPZVec<int64_t> &gelindexes)`
- `void BuildMultiphysicsSpaceWithMemory(TPZVec<int> & active_approx_spaces, TPZVec<TPZCompMesh * > & mesh_vector)`
- `virtual void BuildMultiphysicsSpaceWithMemory()`
- `void BuildMultiphysicsSpaceWithMemory(TPZVec<int> & active_approx_spaces, TPZVec<TPZCompMesh * > & mesh_vector, std::set<int> matsIdWithMem, std::set<int> matsIdNoMem)`
- `virtual void BuildMultiphysicsSpaceWithMemory(std::set<int> matsIdWithMem, std::set<int> matsIdNoMem)`
- `void SetMeshVectorAndActiveSpaces(const TPZVec<TPZCompMesh * > & mesh_vector, const TPZVec<int> & active_approx_spaces)`
- `virtual void LoadSolutionFromMeshes()`
- `virtual void LoadSolutionFromMultiPhysics()`
- `const TPZVec<TPZCompMesh *> &MeshVector() const`
- `const TPZVec<int> &GetActiveApproximationSpaces() const`
- `virtual void CleanElementsConnects()`
