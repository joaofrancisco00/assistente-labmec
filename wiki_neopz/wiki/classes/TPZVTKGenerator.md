# TPZVTKGenerator — API card

Generated from `Post/TPZVTKGenerator.h` — do not edit by hand.

Include: `"TPZVTKGenerator.h"` (in C++ code: `#include "TPZVTKGenerator.h"`)

Public methods (exact declarations from the header):
- `TPZVTKGenerator(TPZCompMesh* cmesh, const TPZVec<std::string> &fields, std::string filename, int vtkres, int dim = -1, bool safe_check = false)`
- `TPZVTKGenerator(TPZAutoPointer<TPZCompMesh> cmesh, const TPZVec<std::string> &fields, std::string filename, int vtkres, int dim = -1, bool safe_check = false)`
- `TPZVTKGenerator(TPZCompMesh* cmesh, std::set<int> mats, const TPZVec<std::string> &fields, std::string filename, int vtkres, bool safe_check = false)`
- `TPZVTKGenerator(TPZAutoPointer<TPZCompMesh> cmesh, std::set<int> mats, const TPZVec<std::string> &fields, std::string filename, int vtkres, bool safe_check = false)`
- `void Do()`
- `void ResetArrays()`
- `void SetNThreads(int nt)`
- `int NThreads() const`
- `void SetStep(int st)`
- `int Step() const`

Does NOT exist (common mistakes):
- `SetSolution`, `Generate`, `Write`, `Export` do NOT exist — the solution is already stored in `TPZCompMesh` after `an.Solve()`; pass `an.Mesh()` (or `cmesh`) to the constructor and call `vtk.Do()`.
