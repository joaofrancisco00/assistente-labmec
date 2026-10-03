import re
import yaml
from pathlib import Path

from .compilation import _extrair_blocos_codigo
from .retrieval import _pergunta_e_explicativa

_COMENTARIO_RE = re.compile(r'//[^\n]*|/\*.*?\*/', re.DOTALL)

_PERGUNTA_COMPARATIVA_RE = re.compile(
    r'(?i)diferen[çc]a|difference|\bcompar|\bvs\.?\b|versus')

_RULES_FILE = Path(__file__).parent / "rules" / "semantic.yaml"
_regras_cache = None

def _carregar_regras() -> list[dict]:
    global _regras_cache
    if _regras_cache is not None:
        return _regras_cache
    
    if not _RULES_FILE.exists():
        _regras_cache = []
        return _regras_cache

    with open(_RULES_FILE, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
        _regras_cache = doc.get("rules", [])
        
    return _regras_cache

def validar_semantica(codigo: str, pergunta: str = None) -> list[str]:
    """
    Verifica se o código gerado pelo modelo fere regras semânticas
    de domínio do NeoPZ.
    Retorna uma lista de mensagens de aviso (strings) para as regras violadas.
    """
    erros = []
    if not codigo:
        return erros
    codigo = _COMENTARIO_RE.sub("", _extrair_blocos_codigo(codigo) or codigo)
    pedido_de_codigo = (bool(pergunta) and not _pergunta_e_explicativa(pergunta)
                        and not _PERGUNTA_COMPARATIVA_RE.search(pergunta))

    for regra in _carregar_regras():
        if regra.get("pergunta"):
            if not pedido_de_codigo or not re.search(regra["pergunta"], pergunta):
                continue
        if regra.get("padrao") and not re.search(regra["padrao"], codigo):
            continue
        # Check requer:
        violado = bool(regra.get("requer")) and not re.search(regra["requer"], codigo)
        # Check incompativel_com:
        if not violado and regra.get("incompativel_com"):
            violado = bool(re.search(regra["incompativel_com"], codigo))
        if violado:
            erros.append(regra["aviso"])

    return erros
