def fallback_routing(user_input: str) -> dict:
    query_lower = user_input.lower()
    sources, queries = [], {}

    if any(w in query_lower for w in ["video", "watch", "youtube", "tutorial", "course"]):
        sources.append("youtube")
        queries["youtube"] = user_input

    if any(w in query_lower for w in ["paper", "research", "study", "arxiv", "academic"]):
        sources.append("arxiv")
        queries["arxiv"] = user_input

    if any(w in query_lower for w in ["book", "novel", "read", "gutenberg", "classic"]):
        sources.append("gutenberg")
        queries["gutenberg"] = user_input

    if not sources:
        sources = ["duckduckgo"]
        queries["duckduckgo"] = user_input

    return {
        "sources": sources,
        "queries": queries,
        "content_type": "mixed",
        "estimated_results": 50,
        "confidence": "low",
        "fallback": True,
    }
