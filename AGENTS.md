# Notes for agents working on this repo

## Verification commands

- Unit tests (also run by the pre-commit hook): `uv run python -m unittest discover -s tests`
- Build the reference recipes against the local NeoPZ install:
  ```bash
  cmake -S reference_solutions -B reference_solutions/build_develop \
        -DNeoPZ_DIR=$HOME/opt/neopz-develop/lib/cmake/neopz \
        -DCMAKE_CXX_COMPILER=/opt/local/bin/g++
  cmake --build reference_solutions/build_develop -j4
  ```
  Then run each binary in `reference_solutions/build_develop/` — compiling is not
  enough (e.g. PostProcessError and manual node allocation bugs only show at runtime).
- Reindex the wiki after editing `wiki_neopz/wiki/**`: `uv run indexer_wiki.py`
  (rebuilds only the `neopz_wiki` collection of `banco_chroma_develop/`).
- Benchmark, fully local and without spending Gemini quota:
  `env -u GOOGLE_API_KEY LLM_CACHE=1 uv run eval_benchmark.py`
- RAG vs agent on one question: `uv run compare_agente_rag.py "<question>" "<suffix>"`

## Conventions

- The assistant is used in English: prompts, wiki, recipes and UI are in English;
  intent detection (`pipeline/retrieval.py`) is bilingual. Terminal logs, README and
  Python identifiers/comments stay in Portuguese.
- Every recipe in `wiki_neopz/wiki/flows/` mirrors a `.cpp` in
  `reference_solutions/task_*/` (copy of the `.md` kept next to it).
- `GOOGLE_API_KEY` lives in `.env` (git-ignored); Gemini free tier is ~20 requests/day.
