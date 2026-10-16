# TPZCondensedCompEl — API card

Generated from `Mesh/pzcondensedcompel.h` — do not edit by hand.

Include: `"Mesh/pzcondensedcompel.h"` (no código: #include "Mesh/pzcondensedcompel.h")

Public methods (exact declarations from the header):
- `virtual ~TPZCondensedCompEl()`
- `virtual void Print(std::ostream &out = std::cout) const override`
- `virtual void Unwrap()`
- `virtual void SetConnectIndex(int inode, int64_t index) override`
- `virtual int NConnects() const override`
- `virtual int64_t ConnectIndex(int i) const override`
- `virtual void BuildConnectList(TPZStack<int64_t> &connectlist) const override`
- `TPZCompEl * ReferenceCompEl()`
- `virtual bool NeedsComputing(const std::set<int> &materialids) override`
- `virtual void LoadElementReference() override`
- `virtual void BuildCornerConnectList(std::set<int64_t> &connectindexes) const override`
- `void SetKeepMatrix(bool keep)`
- `virtual int Dimension() const override`
- `virtual void LoadSolution() override = 0`
- `virtual void TransferMultiphysicsElementSolution() override`
- `virtual TPZVec<STATE> IntegrateSolution(const std::string &varname, const std::set<int> &matids) override`
- `virtual TPZVec<STATE> IntegrateSolution(int var) const override`
- `virtual bool HasMaterial(const std::set<int> &materialids) const override`
- `void EvaluateError(TPZVec<REAL> &errors, bool store_errors) override`
- `virtual void CreateGraphicalElement(TPZGraphMesh & graphmesh, int dimension) override`
- `void GetCompElList(TPZStack<TPZCompEl *> &stck) override`
- `int ComputeIntegrationOrder() const override`
- `virtual void PermuteActiveConnects(TPZManVector<int64_t> &perm) = 0`
- `virtual int ClassId() const override`
