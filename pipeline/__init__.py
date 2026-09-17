import datetime
import json
import os
from pathlib import Path

from .config import (
    GEMINI_MODEL,
    OLLAMA_MODEL,
    NUM_CTX,
    EMBED_MODEL,
    INDEX_DIR,
    WHITELIST_FILE,
    HEADERS_WHITELIST_FILE,
    METHODS_WHITELIST_FILE,
    CLASS_METHODS_INDEX_FILE,
    HEADER_INDEX_DIR,
    CLASS_HEADER_INDEX_FILE,
    COLLISIONS_FILE,
    LEGACY_CLASSES_FILE,
    LOG_INTERACOES_FILE,
    RENAMES_FILE,
    TEMPERATURE,
    MAX_RETRIES,
    K_HEADERS,
    K_EXAMPLES,
    EXAMPLE_POOL_MULT,
    COL_HEADERS,
    COL_EXAMPLES,
    COL_WIKI,
    K_WIKI,
    K_WIKI_CONCEITOS,
    INCLUDES_LIXO_CONHECIDOS,
    HEADERS_SISTEMA,
    NEOPZ_PREFIXES,
    NEOPZ_CXX,
    TIMEOUT_COMPILACAO,
    MAX_ERROS_RELATADOS,
    OllamaLLM,
    HuggingFaceEmbeddings,
    Chroma,
    ChatGoogleGenerativeAI,
)

from .loader import (
    _carregar_whitelist,
    _carregar_headers_whitelist,
    _carregar_methods_whitelist,
    _carregar_class_methods_index,
    _carregar_class_header_index,
    _carregar_legacy_classes,
    _carregar_renames,
    _carregar_collisions,
    _carregar_system_prompt,
    _carregar_bancos,
)

from .retrieval import (
    _boost_por_classe,
    _DIRS_LEGADO,
    _DIRS_NAO_API,
    _fora_da_api,
    _despriorizar_legado,
    _pergunta_e_explicativa,
    _pede_snippet_curto,
    _reservar_vagas_conceitos,
    _dedup_docs,
    _buscar_declaracoes_por_classe,
    _recuperar_contexto,
)

from .validation import (
    _resposta_contem_codigo,
    _validar_codigo,
    _extrair_includes,
    _includes_com_caminho,
    _validar_includes,
    _include_para_header,
    _motivo_indisponivel,
    _classes_indisponiveis,
    _validar_includes_por_classe,
    _validar_metodos,
)

from .correction import (
    _sugerir_correcoes,
    _whitelist_utilizavel,
    _corrigir_classes_automaticamente,
    _corrigir_metodos_automaticamente,
    _corrigir_includes_automaticamente,
)

from .compilation import (
    _extrair_blocos_codigo,
    _montar_tu,
    _erro_denuncia_alucinacao,
    _neopz_prefix,
    _compilador_disponivel,
    _include_flags,
    _compilar_codigo,
    _classes_citadas_em_erros,
)

from .prompt import (
    _montar_prompt,
    _formatar_contexto,
    _formatar_historico,
    _classes_do_contexto,
)

from . import (
    config,
    loader,
    retrieval,
    validation,
    correction,
    compilation,
    prompt,
    cpp_parser,
)

from .cpp_parser import (
    find_tpz_classes_in_code,
    find_suspicious_method_calls,
)

from .health_check import run_health_check


def _registrar_interacao(pergunta: str, resultado: dict, caminho: Path = LOG_INTERACOES_FILE):
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        registro = {
            "quando":                datetime.datetime.now().isoformat(timespec="seconds"),
            "pergunta":              pergunta,
            "resposta":              resultado["resposta"],
            "valido":                resultado["valido"],
            "tentativas":            resultado["tentativas"],
            "correcoes_automaticas": resultado["correcoes_automaticas"],
            "alucinacoes":           resultado["alucinacoes"],
            "includes_errados":      sorted(resultado["includes"].keys()),
            "metodos_suspeitos":     [f"{c}::{m}" for c, m in resultado["metodos_suspeitos"]],
            "compilacao":            resultado.get("compilacao", {}).get("status", "nao_executada"),
            "erros_compilacao":      resultado.get("compilacao", {}).get("erros", []),
            "classes_legado":        resultado.get("classes_legado", []),
            "classes_indisponiveis": resultado.get("classes_indisponiveis", {}),
            "fontes_nao_api":        resultado.get("fontes_nao_api", []),
            "fontes":                sorted(resultado["fontes"]),
        }
        with caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  (log de interações falhou: {e})")


def _emitir(on_evento, tipo: str, texto: str):
    if on_evento is None:
        return
    try:
        on_evento(tipo, texto)
    except Exception:
        pass


def gerar_codigo(
    pergunta: str,
    llm,
    headers_db,
    examples_db,
    whitelist: set,
    headers_whitelist: set,
    system_base: str,
    class_header_index: dict = None,
    collisions: dict = None,
    wiki_db=None,
    methods_whitelist: set = None,
    class_methods_index: dict = None,
    renames: dict = None,
    legacy_classes: set = None,
    historico: list = None,
    on_evento=None,
) -> dict:
    import difflib

    class_header_index = class_header_index or {}
    collisions = collisions or {}
    methods_whitelist = methods_whitelist or set()
    class_methods_index = class_methods_index or {}
    renames = renames or {}
    legacy_classes = legacy_classes or set()

    whitelist_destino = _whitelist_utilizavel(whitelist, class_header_index)

    classes_alucinadas = None
    includes_errados = None
    includes_por_classe = None
    metodos_suspeitos = None
    erros_compilacao = None
    compilacao = {"status": "nao_executada", "erros": [], "ignorados": 0}
    correcoes_automaticas = []
    classes_legado_usadas = []
    classes_indisponiveis = {}
    nomes_ok = False

    melhor = None

    def _resultado(valido: bool) -> dict:
        return {
            "resposta":             resposta,
            "valido":               valido,
            "alucinacoes":          classes_alucinadas or [],
            "includes":             includes_errados or {},
            "includes_por_classe":  includes_por_classe or {},
            "metodos_suspeitos":    metodos_suspeitos or [],
            "compilacao":           compilacao,
            "classes_legado":       classes_legado_usadas,
            "classes_indisponiveis": classes_indisponiveis,
            "fontes_nao_api":       sorted(f for f in fontes
                                           if _fora_da_api(f) == "teste/benchmark"),
            "correcoes_automaticas": correcoes_automaticas,
            "fontes":               set(fontes),
            "tentativas":           tentativa,
        }

    consulta = pergunta
    if historico:
        consulta = f"{historico[-1][0]}\n{pergunta}"
    h_docs, e_docs, w_docs, fontes = _recuperar_contexto(
        consulta, headers_db, examples_db, wiki_db,
        explicativa=_pergunta_e_explicativa(pergunta),
    )

    for tentativa in range(1, MAX_RETRIES + 2):
        print(f"  [Tentativa {tentativa}] Gerando resposta...")
        _emitir(on_evento, "tentativa", str(tentativa))

        contexto = _formatar_contexto(h_docs, e_docs, w_docs)

        prompt = _montar_prompt(
            pergunta, contexto, system_base, whitelist, headers_whitelist,
            classes_alucinadas, includes_errados, includes_por_classe,
            metodos_suspeitos, methods_whitelist,
            erros_compilacao=erros_compilacao,
            classes_contexto=_classes_do_contexto(h_docs, e_docs, w_docs),
            renames=renames,
            historico=historico,
            destinos=whitelist_destino,
        )

        tokens_estimados = len(prompt) // 4
        if type(llm).__name__ == "OllamaLLM" and tokens_estimados > int(NUM_CTX * 0.9):
            print(f"  ⚠️  Prompt grande (~{tokens_estimados} tokens, NUM_CTX={NUM_CTX}) — risco de truncamento")

        _MAX_RETRIES_API = 2
        for _api_try in range(1, _MAX_RETRIES_API + 1):
            try:
                pedacos = []
                for pedaco in llm.stream(prompt):
                    texto = pedaco.content if hasattr(pedaco, "content") else pedaco
                    if isinstance(texto, list):
                        texto = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in texto)
                    texto = str(texto)
                    pedacos.append(texto)
                    _emitir(on_evento, "token", texto)
                resposta = "".join(pedacos)
                break
            except (AttributeError, NotImplementedError):
                ret = llm.invoke(prompt)
                texto = ret.content if hasattr(ret, "content") else ret
                if isinstance(texto, list):
                    texto = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in texto)
                resposta = str(texto)
                break
            except Exception as e:
                erro_str = str(e)
                if ("503" in erro_str or "429" in erro_str) and _api_try < _MAX_RETRIES_API:
                    print(f"  ⚠️  API do Google indisponível ou limite atingido. Acionando o Ollama local ({OLLAMA_MODEL}) imediatamente...")
                    if OllamaLLM is not None:
                        llm = OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)
                    continue
                raise

        tem_codigo = _resposta_contem_codigo(resposta)
        correcoes_automaticas = []
        if tem_codigo:
            resposta, correcoes_classes = _corrigir_classes_automaticamente(
                resposta, whitelist, renames, destinos=whitelist_destino)
            correcoes_automaticas.extend(correcoes_classes)

            metodos_suspeitos_pre_correcao = _validar_metodos(resposta, methods_whitelist, whitelist)
            resposta, correcoes_metodos = _corrigir_metodos_automaticamente(
                resposta, metodos_suspeitos_pre_correcao, class_methods_index,
            )
            correcoes_automaticas.extend(correcoes_metodos)

            resposta, correcoes_includes = _corrigir_includes_automaticamente(
                resposta, class_header_index, collisions, headers_whitelist,
            )
            correcoes_automaticas.extend(correcoes_includes)

            if correcoes_automaticas:
                print(f"  🔧 Corrigido automaticamente: {', '.join(correcoes_automaticas)}")
                _emitir(on_evento, "status", f"🔧 Corrigido automaticamente: {', '.join(correcoes_automaticas)}")

        classes_alucinadas = _validar_codigo(resposta, whitelist)
        if tem_codigo:
            includes_errados = _validar_includes(resposta, headers_whitelist)
            includes_por_classe = _validar_includes_por_classe(resposta, class_header_index, collisions)
            metodos_suspeitos = _validar_metodos(resposta, methods_whitelist, whitelist)
        else:
            includes_errados = {}
            includes_por_classe = {}
            metodos_suspeitos = []

        classes_legado_usadas = sorted(find_tpz_classes_in_code(resposta) & legacy_classes)

        classes_indisponiveis = (_classes_indisponiveis(resposta, class_header_index)
                                 if tem_codigo else {})

        nomes_ok = not (classes_alucinadas or includes_errados
                        or includes_por_classe or metodos_suspeitos)

        compilacao = {"status": "nao_executada", "erros": [], "ignorados": 0}
        erros_compilacao = None
        if nomes_ok and tem_codigo and classes_indisponiveis:
            fora = "; ".join(f"{c} ({m})" for c, m in sorted(classes_indisponiveis.items()))
            compilacao = {"status": "indisponivel", "erros": [], "ignorados": 0,
                          "motivo": f"código usa classe fora desta instalação: {fora}"}
            print(f"  ⚠️  Compilação pulada — {compilacao['motivo']}")
            _emitir(on_evento, "status", f"⚠️ Compilação pulada — {compilacao['motivo']}")
        elif nomes_ok and tem_codigo:
            _emitir(on_evento, "status", "🛠️ Compilando o código gerado...")
            compilacao = _compilar_codigo(resposta)
            if compilacao["status"] == "erros":
                erros_compilacao = compilacao["erros"]
                print(f"  ❌ O compilador recusou o código: {'; '.join(erros_compilacao)}")
                _emitir(on_evento, "status",
                        "❌ O compilador recusou o código: " + "; ".join(erros_compilacao))
            elif compilacao["status"] == "inconclusivo":
                print(f"  ℹ️  Compilação inconclusiva — {compilacao['ignorados']} diagnóstico(s) "
                      "tratados como artefato do recorte, nenhum acusa API inexistente")
            elif compilacao["status"] == "timeout":
                print(f"  ⚠️  Compilação estourou {TIMEOUT_COMPILACAO}s — ignorada")

        if nomes_ok and not erros_compilacao:
            if compilacao["status"] == "ok":
                print("  ✅ Compilado — o g++ aceitou o código: classes, métodos e assinaturas "
                      "existem de verdade (o resultado físico continua não verificado)")
            else:
                print("  ✅ Nomes verificados — classes, headers e métodos existem no NeoPZ "
                      "(semântica e assinaturas não são checadas)")
            return _resultado(True)

        if nomes_ok and melhor is None:
            melhor = _resultado(False)

        if classes_alucinadas:
            print(f"  ⚠️  Classes não encontradas: {', '.join(classes_alucinadas)}")
        if includes_errados:
            print(f"  ⚠️  Headers não encontrados: {', '.join(includes_errados.keys())}")
        if includes_por_classe:
            print(f"  ⚠️  Header errado/faltando para classe: {includes_por_classe}")
        if metodos_suspeitos:
            print(f"  ⚠️  Métodos não encontrados: {metodos_suspeitos}")

        if tentativa >= MAX_RETRIES + 1:
            print("  ⚠️  Limite de tentativas atingido.")
            break

        classes_reforco = set()
        docs_semanticos = []
        for c in classes_alucinadas or []:
            if c in renames and renames[c] in whitelist_destino:
                classes_reforco.add(renames[c])
            classes_reforco.update(
                difflib.get_close_matches(c, whitelist_destino, n=2, cutoff=0.6))
            try:
                docs_semanticos.extend(headers_db.similarity_search(f"{c} {pergunta}", k=2))
            except Exception:
                pass
        for cls, _metodo in metodos_suspeitos or []:
            classes_reforco.add(cls)
        classes_reforco |= _classes_citadas_em_erros(erros_compilacao or [], whitelist)
        classes_reforco -= {d.metadata.get("classe", "") for d in h_docs}

        extras = _buscar_declaracoes_por_classe(headers_db, pergunta, classes_reforco, limite=K_HEADERS)
        extras = _despriorizar_legado(_dedup_docs(extras + docs_semanticos))
        ja_presentes = {d.page_content for d in h_docs}
        extras = [d for d in extras if d.page_content not in ja_presentes]
        if extras:
            h_docs = _dedup_docs(h_docs + extras)
            fontes |= {d.metadata.get("source", "?") for d in extras}
            nomes = ", ".join(sorted(
                {d.metadata.get("classe") or Path(d.metadata.get("source", "?")).name for d in extras}
            ))
            print(f"  📚 Contexto reforçado com declarações de: {nomes}")

        motivo = ("Compilação reprovada" if erros_compilacao
                  else "Problemas de validação detectados")
        _emitir(on_evento, "status", f"↩️ {motivo} — corrigindo e gerando de novo...")
        print("  ↩️  Corrigindo na próxima tentativa...")

    if melhor is not None and not nomes_ok:
        print("  ↩️  Devolvendo a melhor tentativa (nomes limpos, compilação reprovada).")
        return melhor
    return _resultado(False)


def obter_llm():
    if "GOOGLE_API_KEY" in os.environ and ChatGoogleGenerativeAI is not None:
        print(f"  ☁️  Usando Gemini ({GEMINI_MODEL}) via API...")
        return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=TEMPERATURE, max_retries=0)
    else:
        if OllamaLLM is None:
            print("Erro: Nem o pacote do Gemini nem o do Ollama foram encontrados.")
            exit(1)
        print(f"  💻 Usando modelo local ({OLLAMA_MODEL}) via Ollama...")
        return OllamaLLM(model=OLLAMA_MODEL, temperature=TEMPERATURE, num_ctx=NUM_CTX)


def main():
    print("Carregando modelos e banco de dados...")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    headers_db, examples_db, wiki_db = _carregar_bancos(embeddings)
    whitelist          = _carregar_whitelist()
    headers_whitelist  = _carregar_headers_whitelist()
    class_header_index = _carregar_class_header_index()
    collisions         = _carregar_collisions()
    methods_whitelist  = _carregar_methods_whitelist()
    class_methods_index = _carregar_class_methods_index()
    renames            = _carregar_renames()
    legacy_classes     = _carregar_legacy_classes()
    system_base        = _carregar_system_prompt()
    llm                = obter_llm()

    print("\n" + "=" * 50)
    print("  🤖 Assistente LabMeC Pronto!")
    print("  Digite 'sair' para encerrar.")
    print("=" * 50 + "\n")

    historico = []

    while True:
        pergunta = input("Você: ").strip()

        if pergunta.lower() in ("sair", "exit", "quit"):
            print("Encerrando. Bom trabalho!")
            break

        if not pergunta:
            continue

        print("\n[Pensando: buscando documentação e gerando resposta...]")

        resultado = gerar_codigo(
            pergunta, llm, headers_db, examples_db,
            whitelist, headers_whitelist, system_base,
            class_header_index, collisions, wiki_db,
            methods_whitelist, class_methods_index,
            renames, legacy_classes,
            historico=historico,
        )

        historico.append((pergunta, resultado["resposta"]))
        del historico[:-6]

        print("\nAssistente LabMeC:\n")
        print(resultado["resposta"])
        print()

        if resultado["correcoes_automaticas"]:
            print(f"🔧 Correções automáticas (classes/métodos/headers): {', '.join(resultado['correcoes_automaticas'])}")
        if resultado["alucinacoes"]:
            print(f"⚠️  Classes não verificadas: {', '.join(resultado['alucinacoes'])}")
        if resultado["includes"]:
            print(f"⚠️  Headers não verificados: {', '.join(resultado['includes'].keys())}")
        if resultado["includes_por_classe"]:
            faltando_fmt = ", ".join(f"{c} → {h}" for c, h in resultado["includes_por_classe"].items())
            print(f"⚠️  Header incorreto/faltando para classe (índice determinístico): {faltando_fmt}")
        if resultado["metodos_suspeitos"]:
            metodos_fmt = ", ".join(f"{c}::{m}" for c, m in resultado["metodos_suspeitos"])
            print(f"⚠️  Métodos não encontrados no NeoPZ (whitelist global): {metodos_fmt}")
        if resultado["compilacao"]["erros"]:
            print("❌ O compilador recusou o código (erro que a checagem de nomes não pega):")
            for e in resultado["compilacao"]["erros"]:
                print(f"   - {e}")
        if resultado["classes_legado"]:
            dicas = [
                f"{c} → prefira {renames[c]}" if c in renames else c
                for c in resultado["classes_legado"]
            ]
            print(f"⚠️  API antiga ({'/'.join(_DIRS_LEGADO)}) usada: {', '.join(dicas)}")
            print("   Essas classes existem, mas são do legado — prefira a API atual do NeoPZ")
        if resultado.get("classes_indisponiveis"):
            indisp_fmt = ", ".join(f"{c} ({m})"
                                   for c, m in sorted(resultado["classes_indisponiveis"].items()))
            print(f"⚠️  Classe existe no NeoPZ mas não está disponível aqui: {indisp_fmt}")
            print("   O código não vai compilar sem esse header — a compilação foi pulada,")
            print("   não é alucinação do modelo (ver _classes_indisponiveis)")
        if resultado.get("fontes_nao_api"):
            nomes = ", ".join(Path(f).name for f in resultado["fontes_nao_api"])
            print(f"ℹ️  Fontes de teste/benchmark consultadas: {nomes}")
            print(f"   ({'/'.join(_DIRS_NAO_API)} viram executável separado, não entram na libpz —")
            print("    servem para entender a classe, não como exemplo canônico de uso)")
        if resultado["valido"] and resultado["compilacao"]["status"] == "ok":
            print("✅ Compilado: o g++ aceitou o código — classes, métodos e assinaturas existem de verdade")
            print("   (compilar NÃO verifica o resultado físico — confira se o material/formulação é o adequado ao problema)")
        elif resultado["valido"]:
            print("✅ Nomes verificados: classes, headers e métodos existem no NeoPZ")
            print("   (semântica e assinaturas NÃO são checadas — confira se o material/método é o adequado ao problema)")

        fontes_curtas = [Path(f).name for f in resultado["fontes"]]
        print(f"📄 Fontes ({resultado['tentativas']} tentativa(s)): {', '.join(fontes_curtas)}")
        print("-" * 50 + "\n")

        _registrar_interacao(pergunta, resultado)


if __name__ == "__main__":
    main()
