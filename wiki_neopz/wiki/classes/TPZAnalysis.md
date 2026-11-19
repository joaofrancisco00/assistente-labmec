# TPZAnalysis — API card

Generated from `Analysis/TPZAnalysis.h` — do not edit by hand.

Include: `"TPZAnalysis.h"` (in C++ code: `#include "TPZAnalysis.h"`)

Public methods (exact declarations from the header):
- `TPZAnalysis()`
- `TPZAnalysis(TPZCompMesh *mesh, const RenumType& renumtype = RenumType::EDefault, std::ostream &out = std::cout)`
- `TPZAnalysis(TPZAutoPointer<TPZCompMesh> mesh, const RenumType& renumtype = RenumType::EDefault, std::ostream &out = std::cout)`
- `void CreateRenumberObject(const RenumType& renumtype)`
- `virtual ~TPZAnalysis(void)`
- `virtual void Assemble() = 0`
- `virtual void Solve() = 0`
- `virtual void Run(std::ostream &out = std::cout)`
- `TPZSolutionMatrix &Solution()`
- `virtual void LoadSolution()`
- `virtual void LoadSolution(const TPZFMatrix<STATE> &sol)`
- `virtual void LoadSolution(const TPZFMatrix<CSTATE> &sol)`
- `template<class TVar> TPZMatrixSolver<TVar> *BuildPreconditioner(Precond::Type preconditioner, bool overlap)`
- `void CleanUp()`
- `void OptimizeBandwidth()`
- `int HighestDimension()`
- `void Resequence(int firstel = -1)`
- `int ComputeNumberofLoadCases()`
- `TPZCompMesh *Mesh()const`
- `virtual void SetCompMesh(TPZCompMesh * mesh, RenumType mustOptimizeBandwidth)`
- `void SetRenumber(TPZAutoPointer<TPZRenumbering> renumber)`
- `inline TPZSolver * Solver()`
- `virtual void SetSolver(const TPZSolver &solver) = 0`
- `TPZAutoPointer<TPZStructMatrix> StructMatrix()`
- `void SetStructuralMatrix(TPZAutoPointer<TPZStructMatrix> strmatrix)`
- `void SetStructuralMatrix(TPZStructMatrix &strmatrix)`
- `void SetThreadsForError(int nthreads)`
- `void PrintVectorByElement(std::ostream &out, TPZFMatrix<STATE> &vec, REAL tol = 1.e-10)`
- `TPZVec<STATE> Integrate(const std::string &varname, const std::set<int> &matids)`
- `void SetExact(std::function<void (const TPZVec<REAL> &loc, TPZVec<STATE> &result, TPZFMatrix<STATE> &deriv)> f, int pOrder = 1)`
- `void SetExact(std::function<void (const TPZVec<REAL> &loc, TPZVec<CSTATE> &result, TPZFMatrix<CSTATE> &deriv)> f, int pOrder = 1)`
- `virtual void PostProcess(TPZVec<REAL> &loc, std::ostream &out = std::cout)`
- `virtual void PostProcessError(TPZVec<REAL> &, bool store_error = true, std::ostream &out = std::cout)`
- `void ShowShape(const std::string &plotfile, TPZVec<int64_t> &equationindices)`
- `void ShowShape(const std::string &plotfile, TPZVec<int64_t> &equationindices, int matid, const TPZVec<std::string> &varname)`
- `virtual void DefineGraphMesh(int dimension, const TPZVec<std::string> &scalnames, const TPZVec<std::string> &vecnames, const std::string &plotfile)`
- `virtual void DefineGraphMesh(int dimension, const TPZVec<std::string> &scalnames, const TPZVec<std::string> &vecnames, const TPZVec<std::string> &tensnames, const std::string &plotfile)`
- `virtual void DefineGraphMesh(int dimension, const std::set<int> & matids ,const TPZVec<std::string> &scalnames, const TPZVec<std::string> &vecnames, const std::string &plotfile)`
- `virtual void DefineGraphMesh(int dimension, const std::set<int> & matids, const TPZVec<std::string> &scalnames, const TPZVec<std::string> &vecnames, const TPZVec<std::string> &tensnames, const std::string &plotfile)`
- `virtual void CloseGraphMesh()`
- `TPZGraphMesh *GraphMesh(int dimension)`
- `inline void SetStep(int step)`
- `inline int GetStep() const`
- `virtual void PostProcess(int resolution)`
- `virtual void PostProcess(int resolution, int dimension)`
- `void IdentifyPostProcessingMatIds(int dimension, std::set<int> & matids)`
- `virtual void DefineElementTable(int dimension, TPZVec<int64_t> &GeoElIds, TPZVec<REAL> &points)`
- `virtual void SetTableVariableNames(TPZVec<std::string> varnames)`
- `virtual void PrePostProcessTable(std::ostream &out_file)`
- `virtual void PostProcessTable(std::ostream &out_file)`
- `void PostProcessTable( TPZFMatrix<REAL> &pos,std::ostream &out= std::cout )`
- `void Print( const std::string &name , std::ostream &out )`
- `int ClassId() const override`
- `void Write(TPZStream &buf, int withclassid) const override`
- `void Read(TPZStream &buf, void *context) override`
