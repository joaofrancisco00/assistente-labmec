from langchain_core.tools import tool
from typing import Annotated
from .context import PipelineContext
from . import _descrever_problemas, _recursos_validacao, _verificar_resposta
from .retrieval import _buscar_declaracoes_por_nome

def obter_todas_ferramentas(ctx: PipelineContext):

    @tool
    def get_class_declaration(class_name: Annotated[str, "The exact NeoPZ class name, e.g. TPZGeoMesh"]) -> str:
        """Fetches the full declaration (the .h file) of a NeoPZ class, showing all its public methods, constructors and base classes.
        Useful when you need the exact arguments of a constructor or the list of methods a class has."""
        if ctx.headers_db is None:
            return "Error: headers database unavailable."

        docs = ctx.headers_db.similarity_search(class_name, k=3, filter={"classe": class_name})
        if not docs:
            docs = _buscar_declaracoes_por_nome(ctx.headers_db, {class_name}, limite=1)
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
        """Validates a code snippet against NeoPZ: checks that classes, headers and methods exist,
        checks NeoPZ domain rules (e.g. correct constructors and solvers) and runs it through the real g++ compiler.
        Returns 'SUCCESS' if everything passes, or the list of PROBLEMS to fix.
        ALWAYS use this tool to validate your idea BEFORE giving the final answer with the generated code to the user, making sure what you deliver actually works."""
        if "```" not in cpp_code:
            cpp_code = f"```cpp\n{cpp_code}\n```"
        v = _verificar_resposta(cpp_code, **_recursos_validacao(ctx))
        corrigido = ""
        if v["correcoes_automaticas"]:
            corrigido = ("\nNOTE: the validator applied these automatic fixes; apply them in your final answer too: "
                         + ", ".join(v["correcoes_automaticas"]))
        if not v["valido"]:
            problemas = "\n".join(f"- {p}" for p in _descrever_problemas(v))
            return (f"VALIDATION FAILED. Problems found:\n{problemas}{corrigido}\n"
                    "Understand the problems, check the class declarations if needed "
                    "(with get_class_declaration) and try again.")
        if v["compilacao"]["status"] == "ok":
            return ("SUCCESS: the code compiled, the methods/signatures really exist in NeoPZ "
                    f"and no domain rule was violated.{corrigido}")
        return (f"Names and domain rules verified, but compilation was not conclusive "
                f"({v['compilacao']['status']}). It was not possible to confirm that the code "
                f"is 100% correct.{corrigido}")

    return [
        get_class_declaration,
        search_code_examples,
        search_wiki_docs,
        test_compilation,
    ]
