# Add to imports
import os
import json
import jinja2
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ClaudeSearchRouter:
    """Natural language search router using Claude 3.5"""
    
    def __init__(self, model="claude-3-5-sonnet-20241022"):
        """
        Initialize Claude router.
        
        Args:
            model: Use 'claude-3-5-sonnet-20241022' for best quality
                  or 'claude-3-5-haiku-20241022' for lower cost/faster
        """
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model
        
        # Load prompts
        self.system_prompt = Path("prompts/claude_search_system.txt").read_text()
        self.examples = Path("prompts/claude_search_examples.txt").read_text()
        self.template = jinja2.Template(
            Path("prompts/claude_search_user.jinja2").read_text()
        )
        
        # Cache for repeated queries (TTL 5 minutes)
        self.cache = {}
    
    def route(self, user_input: str) -> dict:
        """Route user query to appropriate sources using Claude"""
        
        # Check cache first
        cache_key = user_input.lower().strip()
        if cache_key in self.cache:
            cached_at, result = self.cache[cache_key]
            if (datetime.now() - cached_at).seconds < 300:  # 5 min TTL
                return result
        
        # Prepare user prompt
        user_prompt = self.template.render(
            user_input=user_input,
            current_time=datetime.now().isoformat()
        )
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.1,  # Low temp for deterministic routing
                system=self.system_prompt + "\n\n" + self.examples,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            
            # Handle XML-wrapped responses
            if "<output>" in response_text:
                import re
                match = re.search(r'<output>(.*?)</output>', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            
            # Parse JSON
            result = json.loads(response_text)
            
            # Cache result
            self.cache[cache_key] = (datetime.now(), result)
            
            return result
            
        except Exception as e:
            print(f"Claude routing error: {e}")
            # Return fallback routing
            return self._fallback_routing(user_input)
    
    def _fallback_routing(self, user_input: str) -> dict:
        """Simple keyword-based fallback when Claude fails"""
        query_lower = user_input.lower()
        
        sources = []
        queries = {}
        
        # Keyword-based source selection
        if any(word in query_lower for word in ['video', 'watch', 'youtube', 'tutorial', 'course']):
            sources.append("youtube")
            queries["youtube"] = user_input
        
        if any(word in query_lower for word in ['paper', 'research', 'study', 'arxiv', 'academic']):
            sources.append("arxiv")
            queries["arxiv"] = user_input
        
        if any(word in query_lower for word in ['book', 'novel', 'read', 'gutenberg', 'classic']):
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
            "fallback": True
        }


# Replace your existing /api/nl_search endpoint
@app.post("/api/nl_search")
async def nl_search(request: Request):
    """Natural language search using Claude for intelligent source routing"""
    
    body = await request.json()
    user_query = body.get("query", "")
    
    if not user_query:
        return {"error": "No query provided", "results": []}
    
    # Initialize Claude router
    router = ClaudeSearchRouter()
    
    # Get routing decision
    routing = router.route(user_query)
    
    # If this is a conversion request (no sources), handle appropriately
    if not routing.get("sources"):
        return {
            "routing": routing,
            "results": [],
            "message": "This appears to be a conversion request. Use the /api/convert endpoint."
        }
    
    # Execute searches based on routing
    results = []
    for source in routing["sources"]:
        if source in routing["queries"]:
            query = routing["queries"][source]
            # Call your existing search function for this source
            source_results = await search_source(source, query)
            results.extend(source_results)
    
    # Limit results
    results = results[:50]
    
    return {
        "success": True,
        "routing": routing,
        "results": results,
        "claude_model": router.model
    }


# Helper function you need to implement/adjust based on your existing code
async def search_source(source: str, query: str) -> list:
    """Route to appropriate source-specific search function"""
    
    # Map source names to your existing search functions
    search_functions = {
        "youtube": search_youtube,
        "arxiv": search_arxiv,
        "gutenberg": search_gutenberg,
        "doaj": search_doaj,
        "openalex": search_openalex,
        "internet_archive": search_internet_archive,
        "duckduckgo": search_duckduckgo
    }
    
    if source in search_functions:
        return await search_functions[source](query)
    else:
        return []
