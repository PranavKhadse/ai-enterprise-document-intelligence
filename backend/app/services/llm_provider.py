"""
LLM Provider Abstraction Layer.
Defines BaseLLMProvider interface and provides:
1. MockLLMProvider: Deterministic, 100% offline test double with programmable behaviors.
2. OpenAICompatibleLLMProvider: Async client using httpx for OpenAI, vLLM, Ollama, and LocalAI endpoints.
3. ProviderFactory: Dynamic factory instantiating configured providers.
"""
import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type
import httpx
from pydantic import BaseModel, ValidationError
from backend.app.core.config import settings
from backend.app.schemas.rag import LLMAnswerProposal, LLMClaimProposal

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM provider request times out."""
    pass


class LLMUnavailableError(LLMProviderError):
    """Raised when the LLM provider service cannot be reached."""
    pass


class LLMMalformedOutputError(LLMProviderError):
    """Raised when the LLM produces unparseable or invalid structured output."""
    pass


class BaseLLMProvider(ABC):
    """
    Abstract interface for LLM synthesis engines.
    Decouples the RAG synthesis pipeline from underlying model vendors.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """
        Generates a plain-text completion for the given prompt.
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> BaseModel:
        """
        Generates a structured response strictly validated against a Pydantic schema.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Checks connectivity and availability of the LLM provider.
        """
        pass


class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic, offline test double for LLM synthesis.
    Supports programmable behavior modes and canned responses for robust CI testing.
    """

    def __init__(
        self,
        canned_response: Optional[str] = None,
        canned_proposal: Optional[LLMAnswerProposal] = None,
        mode: str = "default",
        simulated_latency_ms: float = 0.0,
        custom_handler: Optional[Callable[[str, Optional[str]], Any]] = None,
    ):
        self.canned_response = canned_response
        self.canned_proposal = canned_proposal
        self.mode = mode  # 'default', 'insufficient_evidence', 'timeout', 'failure', 'malformed_json', 'fabricated_citation', 'hallucinated_number', 'conflict'
        self.simulated_latency_ms = simulated_latency_ms
        self.custom_handler = custom_handler

    async def _apply_simulated_delay(self) -> None:
        if self.simulated_latency_ms > 0:
            await asyncio.sleep(self.simulated_latency_ms / 1000.0)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        await self._apply_simulated_delay()

        if self.mode == "timeout":
            raise LLMTimeoutError("Mock provider simulated timeout after 10.0s")
        if self.mode == "failure":
            raise LLMUnavailableError("Mock provider simulated connection failure")
        if self.mode == "malformed_json":
            return "{invalid_json: true,"

        if self.custom_handler:
            res = self.custom_handler(prompt, system_prompt)
            if isinstance(res, str):
                return res
            elif isinstance(res, BaseModel):
                return res.model_dump_json()

        if self.canned_response:
            return self.canned_response

        # Default heuristic response generation from prompt evidence
        evidence_matches = re.findall(r'<evidence id="(\[\d+\])"[^>]*>(.*?)</evidence>', prompt, re.DOTALL)
        if not evidence_matches:
            return "I don't have sufficient evidence in the provided documents to answer this confidently."

        first_id, first_text = evidence_matches[0]
        cleaned_text = " ".join(first_text.strip().split()[:20])
        return f"{cleaned_text} {first_id}"

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> BaseModel:
        await self._apply_simulated_delay()

        if self.mode == "timeout":
            raise LLMTimeoutError("Mock provider simulated timeout")
        if self.mode == "failure":
            raise LLMUnavailableError("Mock provider simulated service failure")
        if self.mode == "malformed_json":
            raise LLMMalformedOutputError("Failed to parse malformed JSON into schema")

        if self.canned_proposal and response_schema == LLMAnswerProposal:
            return self.canned_proposal

        if self.custom_handler:
            res = self.custom_handler(prompt, system_prompt)
            if isinstance(res, response_schema):
                return res
            elif isinstance(res, dict):
                return response_schema.model_validate(res)

        # Mode specific structured behaviors
        if self.mode == "insufficient_evidence":
            return LLMAnswerProposal(
                answer="I don't have sufficient evidence in the provided documents to answer this confidently.",
                claims=[],
                citation_ids=[],
                insufficient_evidence=True,
                conflicts_detected=False,
            )

        if self.mode == "fabricated_citation":
            return LLMAnswerProposal(
                answer="The system mandates MFA for all accounts. [99]",
                claims=[LLMClaimProposal(claim_text="The system mandates MFA for all accounts.", citation_ids=[99])],
                citation_ids=[99],
                insufficient_evidence=False,
                conflicts_detected=False,
            )

        if self.mode == "hallucinated_number":
            return LLMAnswerProposal(
                answer="Retention is 90 days. [1]",
                claims=[LLMClaimProposal(claim_text="Retention is 90 days.", citation_ids=[1])],
                citation_ids=[1],
                insufficient_evidence=False,
                conflicts_detected=False,
            )

        if self.mode == "conflict":
            return LLMAnswerProposal(
                answer="Document A specifies retention is 30 days [1], whereas Document B specifies retention is 90 days [2].",
                claims=[
                    LLMClaimProposal(claim_text="Document A specifies retention is 30 days.", citation_ids=[1]),
                    LLMClaimProposal(claim_text="Document B specifies retention is 90 days.", citation_ids=[2]),
                ],
                citation_ids=[1, 2],
                insufficient_evidence=False,
                conflicts_detected=True,
                conflict_details="Discrepancy in retention periods between Document A and Document B.",
            )

        # Default grounded proposal construction from parsed XML evidence
        evidence_matches = re.findall(r'<evidence id="\[(\d+)\]"[^>]*>(.*?)</evidence>', prompt, re.DOTALL)
        if not evidence_matches:
            return LLMAnswerProposal(
                answer="I don't have sufficient evidence in the provided documents to answer this confidently.",
                claims=[],
                citation_ids=[],
                insufficient_evidence=True,
                conflicts_detected=False,
            )

        claims: List[LLMClaimProposal] = []
        citation_ids: List[int] = []
        answer_parts: List[str] = []

        for cid_str, ev_text in evidence_matches:
            cid = int(cid_str)
            citation_ids.append(cid)
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", ev_text.strip()) if s.strip()]
            first_sent = sentences[0] if sentences else ev_text.strip()
            answer_parts.append(f"{first_sent} [{cid}]")
            claims.append(LLMClaimProposal(claim_text=first_sent, citation_ids=[cid]))

        full_answer = " ".join(answer_parts)
        return LLMAnswerProposal(
            answer=full_answer,
            claims=claims,
            citation_ids=citation_ids,
            insufficient_evidence=False,
            conflicts_detected=False,
        )

    async def health_check(self) -> bool:
        return self.mode not in {"failure", "timeout"}


class OpenAICompatibleLLMProvider(BaseLLMProvider):
    """
    Production-grade asynchronous LLM provider targeting OpenAI-compatible endpoints
    (OpenAI API, Azure OpenAI, vLLM, Ollama, LocalAI) using httpx.AsyncClient.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY or ""
        self.base_url = (base_url or settings.LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        self.model_name = model_name or settings.LLM_MODEL_NAME or "gpt-4o-mini"
        self.timeout_seconds = timeout_seconds or settings.LLM_TIMEOUT_SECONDS

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, headers=self._get_headers(), json=payload)
                if response.status_code != 200:
                    raise LLMUnavailableError(
                        f"LLM provider returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise LLMTimeoutError(f"Request to LLM provider timed out after {self.timeout_seconds}s")
        except httpx.RequestError as e:
            raise LLMUnavailableError(f"Failed to connect to LLM provider: {str(e)}")

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> BaseModel:
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        json_instruction = (
            "\n\nCRITICAL INSTRUCTIONS FOR STRUCTURED JSON RESPONSE:\n"
            "1. You MUST respond ONLY with a single valid JSON object instance matching the schema below.\n"
            "2. Never output the JSON schema itself, markdown fences (like ```json), or explanatory commentary.\n"
            "3. The 'answer' field MUST contain the complete synthesized answer with inline citation markers like [1], [2].\n"
            "4. In the 'claims' array, extract each distinct factual statement asserted in your answer into a claim object with 'claim_text' containing the factual statement and 'citation_ids' containing the supporting evidence integer IDs (e.g. {\"claim_text\": \"All corporate documents must be stored in encrypted repositories with multi-factor authentication enforced.\", \"citation_ids\": [1]}). Never leave 'citation_ids' empty if the claim is derived from evidence.\n"
            "5. The top-level 'citation_ids' array MUST contain all unique integer citation IDs referenced in the answer (e.g. [1]).\n\n"
            f"Target JSON Schema Reference:\n{schema_json}"
        )
        augmented_prompt = prompt + json_instruction

        raw_output = await self.generate(
            prompt=augmented_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        # Parse JSON from raw output with robust fence stripping and fallback extraction
        cleaned_json = raw_output.strip()
        if cleaned_json.startswith("```json"):
            cleaned_json = cleaned_json[7:]
        elif cleaned_json.startswith("```"):
            cleaned_json = cleaned_json[3:]
        if cleaned_json.endswith("```"):
            cleaned_json = cleaned_json[:-3]
        cleaned_json = cleaned_json.strip()

        parsed_dict: Optional[Dict[str, Any]] = None
        try:
            parsed_dict = json.loads(cleaned_json)
        except json.JSONDecodeError:
            # Fallback: extract outermost JSON object between first '{' and last '}'
            start = raw_output.find("{")
            end = raw_output.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed_dict = json.loads(raw_output[start : end + 1])
                except json.JSONDecodeError as json_err:
                    logger.warning("Failed to parse extracted JSON block from LLM: %s", json_err)
                    raise LLMMalformedOutputError(f"Invalid structured JSON response from LLM: {str(json_err)}")
            else:
                raise LLMMalformedOutputError(f"LLM produced unparseable non-JSON output: {raw_output[:200]}")

        if not isinstance(parsed_dict, dict):
            raise LLMMalformedOutputError(f"Expected JSON object from LLM, got {type(parsed_dict).__name__}")

        # Guard against LLM regurgitating JSON schema definition instead of an actual instance
        if "$defs" in parsed_dict or ("properties" in parsed_dict and "answer" not in parsed_dict):
            raise LLMMalformedOutputError("LLM returned JSON schema definition instead of response instance.")

        try:
            return response_schema.model_validate(parsed_dict)
        except ValidationError as err:
            logger.warning("Failed to validate parsed LLM dict against schema: %s", err)
            raise LLMMalformedOutputError(f"LLM output failed schema validation: {str(err)}")

    async def health_check(self) -> bool:
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 3.0)) as client:
                resp = await client.get(url, headers=self._get_headers())
                return resp.status_code == 200
        except Exception:
            return False


def get_llm_provider(
    provider_name: Optional[str] = None,
    **kwargs: Any,
) -> BaseLLMProvider:
    """
    Factory function returning the configured LLM provider instance.
    """
    p_type = (provider_name or settings.LLM_PROVIDER).lower().strip()
    if p_type == "mock":
        return MockLLMProvider(**kwargs)
    elif p_type in {"openai", "openai_compatible", "ollama", "vllm", "localai"}:
        return OpenAICompatibleLLMProvider(**kwargs)
    else:
        logger.warning("Unrecognized LLM provider '%s'. Defaulting to MockLLMProvider.", p_type)
        return MockLLMProvider(**kwargs)


# Global default provider instance
llm_provider = get_llm_provider()
