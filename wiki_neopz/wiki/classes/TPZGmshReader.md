# TPZGmshReader — API card

Generated from `Pre/TPZGmshReader.h` — do not edit by hand.

Include: `"TPZGmshReader.h"` (in C++ code: `#include "TPZGmshReader.h"`)

Public methods (exact declarations from the header):
- `void ReadPhysicalProperties4(std::istream &input)`
- `TPZGmshReader()`
- `~TPZGmshReader() = default`
- `TPZGmshReader(const TPZGmshReader &copy) = default`
- `TPZGmshReader &operator=(const TPZGmshReader &copy) = default`
- `TPZGeoMesh * GeometricGmshMesh(const std::string &file_name, TPZGeoMesh *gmesh = NULL, bool addNonAssignedEls = true)`
- `void SetCharacteristiclength(REAL length)`
- `void SetCreateRefPatterns(bool create_refpatterns)`
- `void PrintPartitionSummary(std::ostream & out)`
- `void SetVerbose(int verbose)`
- `void InsertElement(TPZGeoMesh *gmesh, const int physical_identifier, const int el_type, const int el_identifier, const std::vector<int> &node_identifiers)`
- `int GetNumberofNodes(int & el_type)`
- `auto GetPeriodicEls() const`
- `bool InsertElement(TPZGeoMesh * gmesh, std::ifstream & line)`
- `TPZManVector<std::map<int,std::string>,4> & GetDimPhysicalTagName()`
- `void SetDimPhysicalTagName(TPZManVector<std::map<int,std::string>,4> & dim_physical_tag_and_name)`
- `void SetDimNamePhysical(TPZManVector<std::map<std::string,int>,4> & dim_name_and_physical_tag)`
- `TPZManVector<std::map<std::string,int>,4> & GetDimNamePhysical()`
- `void GetDimNamePhysical(TPZVec<std::map<std::string,int>> & dim_name_and_physical_tag)`
- `TPZVec<int64_t> &EntityIndex()`
- `int NHexahedra()`
- `int NTetrahera()`
- `int NPrisms()`
- `int NPyramids()`
- `int NQuadrilaterals()`
- `int NTriangles()`
- `int NLines()`
- `int NPoints()`
- `int Dimension()`
