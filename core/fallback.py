_FRENCH_WORDS = [
    "le", "la", "les", "un", "une", "des", "du", "de", "en", "est", "et",
    "pour", "sur", "dans", "avec", "qui", "que", "par", "au", "aux",
    "revue", "recherche", "article", "livre", "étude", "analyse", "histoire",
    "science", "littérature", "sociologie", "philosophie", "économie",
]

def _is_french(text: str) -> bool:
    words = text.lower().split()
    french_hits = sum(1 for w in words if w in _FRENCH_WORDS)
    # Accent characters are a strong signal
    has_accents = any(c in text for c in "àâäéèêëîïôùûüç")
    return has_accents or french_hits >= 2


def fallback_routing(user_input: str) -> dict:
    query_lower = user_input.lower()
    sources, queries = [], {}
    is_fr = _is_french(user_input)

    # Francophone sources when query is in French
    if is_fr:
        sources.append("hal")
        queries["hal"] = user_input
        if any(w in query_lower for w in ["histoire", "société", "culture", "littérature", "philosophie", "social", "humanités"]):
            sources.append("persee")
            queries["persee"] = user_input
            sources.append("openedition")
            queries["openedition"] = user_input
        if any(w in query_lower for w in ["québec", "québécois", "canada", "francophone"]):
            sources.append("erudit")
            queries["erudit"] = user_input

    # English-primary sources (also relevant for French queries on STEM topics)
    if any(w in query_lower for w in ["paper", "research", "study", "arxiv", "academic", "preprint",
                                       "article", "recherche", "étude", "préprint"]):
        if not is_fr:
            sources.append("arxiv")
            queries["arxiv"] = user_input
        elif "arxiv" not in sources:
            sources.append("arxiv")
            queries["arxiv"] = user_input

    if any(w in query_lower for w in ["journal", "open access", "doaj", "peer", "revue", "accès ouvert"]):
        sources.append("doaj")
        queries["doaj"] = user_input

    if any(w in query_lower for w in ["book", "novel", "read", "gutenberg", "classic", "literature",
                                       "livre", "roman", "classique"]):
        sources.append("gutenberg")
        queries["gutenberg"] = user_input

    if any(w in query_lower for w in ["science", "biology", "chemistry", "physics", "math", "economics",
                                       "biologie", "chimie", "physique", "mathématiques", "économie"]):
        if "openalex" not in sources:
            sources.append("openalex")
            queries["openalex"] = user_input

    if not sources:
        if is_fr:
            sources = ["hal", "openalex"]
            queries["hal"] = user_input
            queries["openalex"] = user_input
        else:
            sources = ["arxiv", "openalex"]
            queries["arxiv"] = user_input
            queries["openalex"] = user_input

    return {
        "sources":           sources,
        "queries":           queries,
        "content_type":      "paper",
        "query_language":    "fr" if is_fr else "en",
        "estimated_results": 20,
        "confidence":        "low",
        "fallback":          True,
    }
