import re
import yaml
from pathlib import Path

from .compilation import _extrair_blocos_codigo

_COMENTARIO_RE = re.compile(r'//[^\n]*|/\*.*?\*/', re.DOTALL)

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

def validar_semantica(codigo: str) -> list[str]:
    """
    Verifica se o código gerado pelo modelo fere regras semânticas
    de domínio do NeoPZ.
    Retorna uma lista de mensagens de aviso (strings) para as regras violadas.
    """
    erros = []
    if not codigo:
        return erros
    codigo = _COMENTARIO_RE.sub("", _extrair_blocos_codigo(codigo) or codigo)
        
    regras = _carregar_regras()
    for regra in regras:
        if re.search(regra["padrao"], codigo):
            violado = False
            # Check requer:
            if regra.get("requer"):
                if not re.search(regra["requer"], codigo):
                    violado = True
                    
            # Check incompativel_com:
            if not violado and regra.get("incompativel_com"):
                if re.search(regra["incompativel_com"], codigo):
                    violado = True
                    
            if violado:
                erros.append(regra["aviso"])
                
    return erros
