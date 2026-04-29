"""
Groq SDK wrapper — call_vision_model + call_text_model.
Handles retries, timeouts, and structured JSON parsing.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from groq import AsyncGroq, APIError, APIConnectionError, RateLimitError

from app.config import settings
from app.utils.exceptions import LLMError

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class LLMClient:
    """Async Groq LLM client with vision and text model support."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or settings.groq_api_key
        self._client: Optional[AsyncGroq] = None
        self._vision_model = settings.vision_model
        self._text_model = settings.text_model
        self._total_calls = 0
        self._total_tokens = 0

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def call_vision_model(
        self,
        system_prompt: str,
        user_prompt: str,
        image_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Call Llama 4 Scout with an image for vision tasks."""
        messages = [{"role": "system", "content": system_prompt}]

        # Build user message with image
        content_parts: list[dict[str, Any]] = []
        if image_base64:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            })
        elif image_url:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
        content_parts.append({"type": "text", "text": user_prompt})

        messages.append({"role": "user", "content": content_parts})

        return await self._call_with_retry(
            model=self._vision_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def call_text_model(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Call Llama 3.3 70B for text-only reasoning tasks."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self._call_with_retry(
            model=self._text_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _call_with_retry(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call the Groq API with retry logic and JSON parsing."""
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                start_time = time.time()
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                elapsed = (time.time() - start_time) * 1000

                self._total_calls += 1
                tokens = response.usage.total_tokens if response.usage else 0
                self._total_tokens += tokens

                raw_content = response.choices[0].message.content or "{}"

                logger.info(
                    f"LLM call [{model}] attempt={attempt} "
                    f"tokens={tokens} time={elapsed:.0f}ms"
                )

                # Parse JSON
                try:
                    parsed = json.loads(raw_content)
                    return parsed
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error on attempt {attempt}: {e}")
                    # Try to extract JSON from the response
                    parsed = self._extract_json(raw_content)
                    if parsed:
                        return parsed
                    if attempt == MAX_RETRIES:
                        raise LLMError(
                            f"Failed to parse LLM response as JSON after {MAX_RETRIES} attempts",
                            details={"raw_content": raw_content[:500]},
                        )

            except RateLimitError as e:
                last_error = e
                logger.warning(f"Rate limited on attempt {attempt}, waiting...")
                if attempt < MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY * attempt * 2)
            except APIConnectionError as e:
                last_error = e
                logger.warning(f"Connection error on attempt {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY * attempt)
            except APIError as e:
                last_error = e
                logger.error(f"API error on attempt {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY)
            except LLMError:
                raise
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    break

        raise LLMError(
            f"LLM call failed after {MAX_RETRIES} attempts: {last_error}",
            details={"model": model, "last_error": str(last_error)},
        )

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Try to extract JSON from text that may have markdown or extra content."""
        # Try to find JSON between curly braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return None

    @property
    def stats(self) -> dict[str, int]:
        return {"total_calls": self._total_calls, "total_tokens": self._total_tokens}
