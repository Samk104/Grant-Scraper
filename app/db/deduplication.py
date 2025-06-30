import hashlib

def compute_opportunity_hash(title: str, description: str, url: str) -> str:
    snippet = description.strip().lower()[:100]
    combined = (title + snippet + url).strip().lower()
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

