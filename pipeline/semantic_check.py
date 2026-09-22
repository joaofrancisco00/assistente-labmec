import re

# Regras semânticas de domínio para o NeoPZ
# Formato: 
# "nome": Nome descritivo da regra
# "padrao": Regex que ativa a regra (se for encontrado no código gerado)
# "requer": Regex que DEVE existir no código se o padrão for encontrado
# "incompativel_com": Regex que NÃO PODE existir se o padrão for encontrado
# "aviso": Mensagem que será repassada ao modelo para correção
REGRAS_SEMANTICAS = [
    {
        "nome": "Elasticidade 2D - Construtor Completo",
        "padrao": r"\bTPZElasticity2D\b",
        "requer": r"TPZElasticity2D\s*\([^)]*,[^)]*,[^)]*,[^)]*,[^)]*,[^)]*\)", 
        "incompativel_com": r"\bSetElasticity\b",
        "aviso": "Para TPZElasticity2D, use sempre o construtor completo com 6 argumentos (id, E, nu, fx, fy, planestress) e NUNCA use SetElasticity(), pois ele não inicializa a lei constitutiva."
    },
    {
        "nome": "Darcy Misto - Malha Multifísica",
        "padrao": r"\bTPZMixedDarcyFlow\b|\bTPZMultiphysicsCompMesh\b",
        "requer": r"\bBuildMultiphysicsSpace\b",
        "incompativel_com": None,
        "aviso": "Na formulação mista (TPZMixedDarcyFlow / TPZMultiphysicsCompMesh), você DEVE usar cmesh->BuildMultiphysicsSpace() e não AutoBuild()."
    },
    {
        "nome": "Darcy Misto - Solver",
        "padrao": r"\bTPZMixedDarcyFlow\b",
        "requer": r"\bELDLt\b|\bELU\b",
        "incompativel_com": r"\bECholesky\b",
        "aviso": "Sistemas mistos são de ponto de sela (indefinidos). O solver DEVE usar ELDLt ou ELU, NUNCA ECholesky."
    },
    {
        "nome": "Poisson - Não usar API antiga",
        "padrao": r"\bTPZMatPoisson\b",
        "requer": None,
        "incompativel_com": r"\bTPZDummyFunction\b|\bTPZMatLaplacian\b",
        "aviso": "A API atual do TPZMatPoisson usa std::function diretamente. Não use TPZDummyFunction ou TPZMatLaplacian."
    },
    {
        "nome": "Darcy H1 - Permeabilidade",
        "padrao": r"\bTPZDarcyFlow\b",
        "requer": r"\bSetConstantPermeability\b",
        "incompativel_com": r"\bTPZHybridDarcyFlow\b|\bTPZMixedDarcyFlow\b",
        "aviso": "Você está usando TPZDarcyFlow (formulação H1), mas esqueceu de chamar SetConstantPermeability(). Adicione a chamada a esse método. Mantenha a classe TPZDarcyFlow, não mude o material."
    }
]

def validar_semantica(codigo: str) -> list[str]:
    """
    Verifica se o código gerado pelo modelo fere regras semânticas
    de domínio do NeoPZ.
    Retorna uma lista de mensagens de aviso (strings) para as regras violadas.
    """
    erros = []
    if not codigo:
        return erros
        
    for regra in REGRAS_SEMANTICAS:
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
