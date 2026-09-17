import json
from pathlib import Path

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

def _analyze_collection(collection_name, embeddings, index_dir):
    try:
        db = Chroma(
            persist_directory=str(index_dir),
            embedding_function=embeddings,
            collection_name=collection_name,
        )
    except Exception as e:
        print(f"  [HealthCheck] Error loading {collection_name}: {e}")
        return []

    try:
        data = db.get() # Get all ids, documents, metadatas
    except Exception as e:
        print(f"  [HealthCheck] Error getting data for {collection_name}: {e}")
        return []

    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])
    ids = data.get("ids", [])

    inefficient_chunks = []
    
    for i in range(len(documents)):
        doc = documents[i]
        meta = metadatas[i] or {}
        chunk_id = ids[i]
        
        reasons = []
        
        # 1. Very short chunks
        if len(doc.strip()) < 50:
            reasons.append("Muito curto (< 50 caracteres)")
            
        # 2. Boilerplate license text dominating the chunk
        if "This file is part of the PZ environment" in doc or "Universidade Estadual de Campinas" in doc:
            if len(doc) < 1000:
                reasons.append("Contém apenas/maioria de licença boilerplate")
                
        # 3. Examples with no classes used
        if collection_name == "neopz_examples":
            classes = meta.get("classes_usadas", "").strip()
            if not classes:
                lines = doc.splitlines()
                include_lines = [l for l in lines if l.startswith("#include")]
                if len(include_lines) == len([l for l in lines if l.strip()]):
                    reasons.append("Exemplo contendo apenas includes (sem código real)")
                elif len(doc.strip()) < 150:
                     reasons.append("Exemplo curto sem classes TPZ")
                     
        # 4. Headers empty or just includes
        if collection_name == "neopz_headers":
            if not meta.get("classe"):
                if "class " not in doc and "struct " not in doc:
                     reasons.append("Header chunk sem definições de classe/struct e metadata vazio")

        if reasons:
            inefficient_chunks.append({
                "id": chunk_id,
                "collection": collection_name,
                "source": meta.get("source", "unknown"),
                "reasons": reasons,
                "length": len(doc),
                "snippet": doc[:100].replace("\n", " ") + "..."
            })
            
    return inefficient_chunks

def run_health_check(embeddings, index_dir: Path, log_dir: Path) -> list:
    """Roda a análise de sanidade nas coleções e salva o resultado no diretório de logs.
    Retorna a lista de anomalias encontradas."""
    print(f"\n🩺 Iniciando Health Check do Banco de Dados...")
    all_inefficient = []
    
    for col in ["neopz_headers", "neopz_examples", "neopz_wiki"]:
        inefficient = _analyze_collection(col, embeddings, index_dir)
        all_inefficient.extend(inefficient)
        
    log_dir.mkdir(parents=True, exist_ok=True)
    report_file = log_dir / "chroma_health.json"
    
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(all_inefficient, f, indent=2, ensure_ascii=False)
        
    return all_inefficient
