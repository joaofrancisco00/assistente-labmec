from langchain_core.tools import tool
from typing import Annotated
from .context import PipelineContext
from .compilation import _compilar_codigo

def obter_todas_ferramentas(ctx: PipelineContext):

    @tool
    def get_class_declaration(class_name: Annotated[str, "The exact NeoPZ class name, e.g. TPZGeoMesh"]) -> str:
        """Fetches the full declaration (the .h file) of a NeoPZ class, showing all its public methods, constructors and base classes.
        Useful when you need the exact arguments of a constructor or the list of methods a class has."""
        if ctx.headers_db is None:
            return "Error: headers database unavailable."

        docs = ctx.headers_db.similarity_search(class_name, k=3, filter={"classe": class_name})
        if not docs:
            docs = ctx.headers_db.similarity_search(class_name, k=3)

        return "\n\n".join([f"/// {d.metadata.get('source', 'Header')}\n{d.page_content}" for d in docs])

    @tool
    def search_code_examples(query: Annotated[str, "What you want to find in the code, e.g. 'TPZMixedDarcyFlow' or 'create geometric mesh'"]) -> str:
        """Searches real NeoPZ source code (tests and tutorials) where classes and functions are used in practice.
        Useful when you have the class declaration but do not know how to initialize it or how it interacts with the computational mesh."""
        if ctx.examples_db is None:
            return "Error: examples database unavailable."

        docs = ctx.examples_db.max_marginal_relevance_search(query, k=4, fetch_k=20)
        return "\n\n".join([f"/// {d.metadata.get('source', 'Example')}\n{d.page_content}" for d in docs])

    @tool
    def search_wiki_docs(query: Annotated[str, "A mathematical or NeoPZ concept, e.g. 'convection', 'H1 space', 'saddle point'"]) -> str:
        """Searches theoretical explanations, documentation and step-by-step recipes in the NeoPZ project Wiki.
        Useful to understand the physics, the available formulations, or the high-level steps to structure a NeoPZ program."""
        if ctx.wiki_db is None:
            return "Error: wiki database unavailable."

        docs = ctx.wiki_db.similarity_search(query, k=3)
        return "\n\n".join([f"/// {d.metadata.get('source', 'Wiki')}\n{d.page_content}" for d in docs])

    @tool
    def test_compilation(cpp_code: Annotated[str, "Complete C++ code snippet to be tested by the GCC compiler"]) -> str:
        """Runs a code snippet through the real g++ compiler using the NeoPZ environment.
        Returns 'SUCCESS' if the code compiles correctly, or the list of COMPILER ERRORS.
        ALWAYS use this tool to validate your idea BEFORE giving the final answer with the generated code to the user, making sure what you deliver actually works."""
        if "```" not in cpp_code:
            cpp_code = f"```cpp\n{cpp_code}\n```"
        res = _compilar_codigo(cpp_code)
        if res["status"] == "ok":
            return "SUCCESS: the code compiled and the methods/signatures really exist in NeoPZ."
        elif res["status"] == "erros":
            erros_str = "\n".join(res["erros"])
            return f"COMPILATION ERROR. The compiler reported the following errors:\n{erros_str}\nUnderstand the errors, check the class declarations if needed (with get_class_declaration) and try again."
        else:
            return f"Warning: {res['status']}. It was not possible to confirm that the code is 100% correct."

    return [
        get_class_declaration,
        search_code_examples,
        search_wiki_docs,
        test_compilation,
    ]
