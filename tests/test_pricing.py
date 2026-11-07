import tempfile
import unittest
from pathlib import Path

from tokonomy import pricing


class PricingTests(unittest.TestCase):
    def test_openai_input_includes_cache_anthropic_does_not(self):
        table = pricing.load_pricing()
        codex = pricing.estimate("codex", "gpt-5", 1_000_000, 900_000, 0, 100_000, table)
        self.assertAlmostEqual(codex, 1.2375, places=4)
        claude = pricing.estimate("claude-code", "claude-sonnet-5", 1_000, 9_000, 0, 1_000, table)
        self.assertAlmostEqual(claude, 0.0207, places=4)

    def test_unknown_model_returns_none(self):
        self.assertIsNone(pricing.estimate("codex", "unknown-9000", 1, 0, 0, 1, pricing.load_pricing()))

    def test_local_override_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pricing.json"
            path.write_text('{"my-model": {"input": 1, "cached_input": 0.1, "cache_write": 2, "output": 3}}', encoding="utf-8")
            table = pricing.load_pricing(Path(directory))
            self.assertAlmostEqual(
                pricing.estimate("codex", "my-model", 1_000_000, 0, 0, 0, table), 1.0, places=6
            )


if __name__ == "__main__":
    unittest.main()
