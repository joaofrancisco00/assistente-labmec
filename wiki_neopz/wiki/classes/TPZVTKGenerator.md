# TPZVTKGenerator — API card

Generated from `Post/TPZVTKGenerator.h` — do not edit by hand.

Include: `"Post/TPZVTKGenerator.h"` (no código: #include "Post/TPZVTKGenerator.h")

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
