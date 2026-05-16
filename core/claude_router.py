import json
import re
import jinja2
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import ClaudeConfig
from core.fallback import fallback_routing
from utils.cache import ResponseCache
from utils.cost_tracker import cost_tracker
from monitoring.claude_monitor import log_routing, log_error, log_fallback


class ClaudeSearchRouter:
    """Natural language search router using Claude 3.5"""

    def __init__(self, model: str = ClaudeConfig.MODEL):
        self.client = Anthropic(api_key=ClaudeConfig.API_KEY)
        self.model = model
        self.system_prompt = Path("prompts/claude_search_system.txt").read_text()
        self.examples = Path("prompts/claude_search_examples.txt").read_text()
        self.template = jinja2.Template(
            Path("prompts/claude_search_user.jinja2").read_text()
        )
        self.cache = ResponseCache(ttl=ClaudeConfig.CACHE_TTL)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call_api(self, system: str, user_prompt: str):
        return self.client.messages.create(
            model=self.model,
            max_tokens=ClaudeConfig.MAX_TOKENS,
            temperature=ClaudeConfig.TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )

    def route(self, user_input: str) -> dict:
        cache_key = user_input.lower().strip()
        cached = self.cache.get(cache_key)
        if cached:
            log_routing(user_input, cached, self.model, cached=True)
            return cached

        user_prompt = self.template.render(
            user_input=user_input,
            current_time=datetime.now().isoformat(),
        )

        try:
            response = self._call_api(
                self.system_prompt + "\n\n" + self.examples, user_prompt
            )
            response_text = response.content[0].text
            if "<output>" in response_text:
                match = re.search(r"<output>(.*?)</output>", response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            result = json.loads(response_text)
            cost_tracker.record(
                self.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            self.cache.set(cache_key, result)
            log_routing(user_input, result, self.model)
            return result
        except Exception as e:
            log_error(user_input, e)
            if ClaudeConfig.FALLBACK_ENABLED:
                log_fallback(user_input)
                return fallback_routing(user_input)
            raise
