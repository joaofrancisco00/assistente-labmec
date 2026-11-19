# TPZCompMeshTools — API card

Generated from `Mesh/TPZCompMeshTools.h` — do not edit by hand.

Include: `"TPZCompMeshTools.h"` (in C++ code: `#include "TPZCompMeshTools.h"`)

Public methods (exact declarations from the header):
- `void AddHDivPyramidRestraints(TPZCompMesh *cmesh)`
- `void ExpandHDivPyramidRestraints(TPZCompMesh *cmesh)`
- `void LoadSolution(TPZCompMesh *cpressure, TPZFunction<STATE> &Forcing)`
- `void GroupElements(TPZCompMesh *cmesh, std::set<int64_t> elbasis, std::set<int64_t> &grouped)`
- `void PutinSubmeshes(TPZCompMesh *cmesh, std::set<int64_t> &elindices, int64_t &index, int KeepOneLagrangian)`
- `void PutinSubmeshes(TPZCompMesh *cmesh, std::map<int64_t,std::set<int64_t> >&elindices, std::map<int64_t,int64_t> &indices, int KeepOneLagrangian)`
- `void GroupElements(TPZCompMesh *cmesh)`
- `void GroupNeighbourElements(TPZCompMesh *cmesh, const std::set<int64_t> &seed_elements, std::set<int64_t> &groupindexes)`
- `void CreatedCondensedElements(TPZCompMesh *cmesh, bool KeepOneLagrangian, bool keepmatrix = true)`
- `void CondenseElements(TPZCompMesh *cmesh, char LagrangeLevelNotCondensed, bool keepmatrix)`
- `void UnGroupElements(TPZCompMesh *cmesh)`
- `void UnCondensedElements(TPZCompMesh *cmesh)`
- `void ComputeDifferenceNorm(TPZCompMesh *mesh1, TPZCompMesh *mesh2, TPZVec<STATE> &square_errors)`
- `void AdjustFluxPolynomialOrders(TPZCompMesh *fluxmesh, int hdivplusplus)`
- `void SetPressureOrders(TPZCompMesh *fluxmesh, TPZCompMesh *pressuremesh)`
- `void OptimizeBandwidth(TPZCompMesh *cmesh)`
- `void PrintSolutionByGeoElement(TPZCompMesh *cmesh, std::ostream &out)`
- `void PrintStiffnessMatrixByGeoElement(TPZCompMesh *cmesh, std::ostream &out, std::set<int> matIDs =`
- `void PrintConnectInfoByGeoElement(TPZCompMesh *cmesh, std::ostream &out, std::set<int> matIDs =`

Does NOT exist (common mistakes):
- Canonical static condensation sequence on `TPZCompMesh *cmesh`: `TPZCompMeshTools::GroupElements(cmesh); TPZCompMeshTools::CreatedCondensedElements(cmesh, true);` (or `TPZCompMeshTools::CondenseElements(cmesh, 0, true);`), then solve with `TPZLinearAnalysis an(cmesh); an.Assemble(); an.Solve();`, then `TPZCompMeshTools::UnCondensedElements(cmesh);`.
- `TPZLinearAnalysis::SetMaterial` and `TPZNonLinMultGridAnalysis` do NOT exist — materials belong in `cmesh->InsertMaterialObject(mat)`.
