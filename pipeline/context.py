"""
Contexto do pipeline — carregado uma vez, reusado em todas as chamadas.

Encapsula todos os recursos (bancos vetoriais, whitelists, índices, LLM)
que o pipeline precisa. Antes ficavam como 12 variáveis globais separadas,
repetidas em app.py, pipeline/__init__.py:main() e eval_benchmark.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineContext:
    """Encapsula todos os recursos (bancos, whitelists, índices, LLM)
    que o pipeline precisa.  Carregados UMA vez na subida do app."""

    llm: object
    headers_db: object
    examples_db: object
    wiki_db: object | None

    whitelist: set
    headers_whitelist: set
    methods_whitelist: set

    class_header_index: dict
    class_methods_index: dict
    collisions: dict
    renames: dict

    legacy_classes: set
    system_base: str

    @classmethod
    def load(cls) -> PipelineContext:
        """Factory que carrega tudo de uma vez — substitui o bloco de
        carregamento repetido nos 3+ entry-points do projeto."""
        from .config import EMBED_MODEL, HuggingFaceEmbeddings
        from .loader import (
            _carregar_bancos,
            _carregar_class_header_index,
            _carregar_class_methods_index,
            _carregar_collisions,
            _carregar_headers_whitelist,
            _carregar_legacy_classes,
            _carregar_methods_whitelist,
            _carregar_renames,
            _carregar_system_prompt,
            _carregar_whitelist,
        )

        # import circular-safe: obter_llm está em __init__, mas só é chamado
        # em runtime (nunca no import-time do módulo).
        from . import obter_llm

        print("Carregando modelos e banco de dados...")
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            encode_kwargs={"normalize_embeddings": True},
        )
        headers_db, examples_db, wiki_db = _carregar_bancos(embeddings)

        ctx = cls(
            llm=obter_llm(),
            headers_db=headers_db,
            examples_db=examples_db,
            wiki_db=wiki_db,
            whitelist=_carregar_whitelist(),
            headers_whitelist=_carregar_headers_whitelist(),
            methods_whitelist=_carregar_methods_whitelist(),
            class_header_index=_carregar_class_header_index(),
            class_methods_index=_carregar_class_methods_index(),
            collisions=_carregar_collisions(),
            renames=_carregar_renames(),
            legacy_classes=_carregar_legacy_classes(),
            system_base=_carregar_system_prompt(),
        )
        print("Pronto.\n")
        return ctx
