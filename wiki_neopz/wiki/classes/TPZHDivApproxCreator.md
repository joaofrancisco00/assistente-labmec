# TPZHDivApproxCreator — API card

Generated from `Pre/TPZHDivApproxCreator.h` — do not edit by hand.

Include: `"TPZHDivApproxCreator.h"` (in C++ code: `#include "TPZHDivApproxCreator.h"`)

Public methods (exact declarations from the header):
- `TPZHDivApproxCreator() = default`
- `TPZHDivApproxCreator(TPZGeoMesh * gmesh)`
- `~TPZHDivApproxCreator()`
- `HDivFamily &HdivFamily()`
- `const HDivFamily &HdivFamily() const`
- `virtual void SetHybridType(HybridizationType hybrid) override`
- `virtual void SetProbType(ProblemType prob) override`
- `TPZMultiphysicsCompMesh *CreateApproximationSpace() override`
- `void AddInterfaceComputationalElements(TPZMultiphysicsCompMesh *mphys)`
- `void AddInterfaceComputationalElementsBackup(TPZMultiphysicsCompMesh *mphys)`
- `void PrintMeshElementsConnectInfo(TPZCompMesh* cmesh)`
- `static void PrintAllMeshes(TPZMultiphysicsCompMesh* mpcmesh)`
- `void CreateAtomicMeshes(TPZManVector<TPZCompMesh*,7>& meshvec, int& lagLevelCounter)`
- `void CreateMultiPhysicsMesh(TPZManVector<TPZCompMesh*,7>& meshvec, int& lagLevelCounter, TPZMultiphysicsCompMesh*& cmeshmulti)`
- `void SetShouldCondensePressure(bool isCondensed)`
- `bool ShouldCondensePressure() const`
- `void CheckSetupConsistency() override`

Does NOT exist (common mistakes):
- Set polynomial order with `hdivCreator.SetDefaultOrder(pOrder);` (`HdivFamily()` is a getter taking 0 args; to change family call `SetHdivFamily(HDivFamily::EHDivStandard)` with values from `TPZEnumApproxFamily.h`: `EHDivStandard`, `EHDivConstant`, `EHDivKernel`).
