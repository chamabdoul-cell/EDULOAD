COSTS_PER_MILLION = {
    "claude-3-5-sonnet-20241022": {"input": 3.0,  "output": 15.0},
    "claude-3-5-haiku-20241022":  {"input": 0.8,  "output":  4.0},
}


class CostTracker:
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.calls = 0

    def record(self, model: str, input_tokens: int, output_tokens: int):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.calls += 1

    def cost(self, model: str) -> float:
        rates = COSTS_PER_MILLION.get(model, {"input": 3.0, "output": 15.0})
        return (
            self.total_input * rates["input"] + self.total_output * rates["output"]
        ) / 1_000_000

    def summary(self, model: str) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.total_input,
            "output_tokens": self.total_output,
            "estimated_cost_usd": round(self.cost(model), 6),
        }


cost_tracker = CostTracker()
