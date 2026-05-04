from .models import SearchDoc, SearchResult


def _snippet(text: str, query: str, window: int = 80) -> str:
    idx = text.find(query)
    if idx == -1:
        return text[:window].strip()
    start = max(0, idx - 20)
    end = min(len(text), start + window)
    fragment = text[start:end].strip()
    return ("..." if start > 0 else "") + fragment + ("..." if end < len(text) else "")


def search(docs: list[SearchDoc], query: str, kinds: list[str] | None = None, limit: int = 20) -> list[SearchResult]:
    q = query.lower()
    results: list[SearchResult] = []

    name_hits: list[SearchResult] = []
    body_hits: list[SearchResult] = []

    for doc in docs:
        if kinds and doc["kind"] not in kinds:
            continue
        name_match = q in doc["name"].lower()
        body_match = q in doc["text"]
        if name_match:
            name_hits.append({"kind": doc["kind"], "slug": doc["slug"], "name": doc["name"], "snippet": _snippet(doc["text"], q)})
        elif body_match:
            body_hits.append({"kind": doc["kind"], "slug": doc["slug"], "name": doc["name"], "snippet": _snippet(doc["text"], q)})

    results = name_hits + body_hits
    return results[:limit]
