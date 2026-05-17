def fallback_routing(user_input: str) -> dict:
    query_lower = user_input.lower()
    sources, queries = [], {}

    if any(w in query_lower for w in ["paper", "research", "study", "arxiv", "academic", "preprint"]):
        sources.append("arxiv")
        queries["arxiv"] = user_input

    if any(w in query_lower for w in ["journal", "article", "open access", "doaj", "peer"]):
        sources.append("doaj")
        queries["doaj"] = user_input

    if any(w in query_lower for w in ["book", "novel", "read", "gutenberg", "classic", "literature"]):
        sources.append("gutenberg")
        queries["gutenberg"] = user_input

    if any(w in query_lower for w in ["science", "biology", "chemistry", "physics", "math", "economics"]):
        if "openalex" not in sources:
            sources.append("openalex")
            queries["openalex"] = user_input

    if not sources:
        sources = ["arxiv", "openalex"]
        queries["arxiv"] = user_input
        queries["openalex"] = user_input

    return {
        "sources":           sources,
        "queries":           queries,
        "content_type":      "paper",
        "query_language":    "en",
        "estimated_results": 20,
        "confidence":        "low",
        "fallback":          True,
    }
