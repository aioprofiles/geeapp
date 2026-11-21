import json
import logging
import os
import re

log = logging.getLogger("llm")


class LLM:
    """Optional Claude helper. Every feature has a non-LLM fallback, so the bot runs without a key."""

    def __init__(self, model: str):
        self.model, self.client = model, None
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.AsyncAnthropic()
            except ImportError:
                log.warning("anthropic package missing; LLM features disabled")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def ask(self, system: str, user: str, max_tokens=600) -> str | None:
        if not self.client:
            return None
        try:
            r = await self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                                  messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in r.content if b.type == "text").strip()
        except Exception as e:  # network / quota: degrade, never crash a handler
            log.warning("llm error: %s", e)
            return None

    async def json(self, system: str, user: str, max_tokens=400) -> dict | None:
        txt = await self.ask(system + "\nReply with ONLY a JSON object.", user, max_tokens)
        if not txt:
            return None
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None
