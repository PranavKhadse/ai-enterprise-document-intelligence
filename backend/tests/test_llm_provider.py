"""
Unit tests for LLM Provider abstraction and MockLLMProvider.
Verifies deterministic mock modes, timeout handling, malformed JSON detection, and factory instantiation.
"""
import pytest
from backend.app.schemas.rag import LLMAnswerProposal, LLMClaimProposal
from backend.app.services.llm_provider import (
    BaseLLMProvider,
    LLMMalformedOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
    MockLLMProvider,
    OpenAICompatibleLLMProvider,
    get_llm_provider,
)


@pytest.mark.asyncio
async def test_mock_provider_default_generation():
    """Verifies default mock generation from parsed XML evidence."""
    provider = MockLLMProvider()
    prompt = (
        '<evidence_corpus>\n'
        '  <evidence id="[1]" document="Doc1.pdf">Multi-factor authentication is mandatory.</evidence>\n'
        '</evidence_corpus>\n'
        '<user_query>What is required?</user_query>'
    )
    resp = await provider.generate(prompt)
    assert "[1]" in resp
    assert "authentication" in resp.lower()


@pytest.mark.asyncio
async def test_mock_provider_structured_default():
    """Verifies default structured proposal generation."""
    provider = MockLLMProvider()
    prompt = (
        '<evidence_corpus>\n'
        '  <evidence id="[1]" document="Doc1.pdf">Multi-factor authentication is mandatory.</evidence>\n'
        '  <evidence id="[2]" document="Doc2.pdf">Database backups are retained for 30 days.</evidence>\n'
        '</evidence_corpus>\n'
        '<user_query>What are the policies?</user_query>'
    )
    proposal = await provider.generate_structured(prompt, response_schema=LLMAnswerProposal)
    assert isinstance(proposal, LLMAnswerProposal)
    assert proposal.citation_ids == [1, 2]
    assert len(proposal.claims) == 2
    assert proposal.insufficient_evidence is False


@pytest.mark.asyncio
async def test_mock_provider_insufficient_evidence_mode():
    """Verifies mock behavior under insufficient evidence mode."""
    provider = MockLLMProvider(mode="insufficient_evidence")
    proposal = await provider.generate_structured("prompt without context", response_schema=LLMAnswerProposal)
    assert proposal.insufficient_evidence is True
    assert len(proposal.claims) == 0


@pytest.mark.asyncio
async def test_mock_provider_simulated_errors():
    """Verifies timeout, failure, and malformed json error handling in mock provider."""
    # Timeout
    p_timeout = MockLLMProvider(mode="timeout")
    with pytest.raises(LLMTimeoutError):
        await p_timeout.generate("test")

    # Failure
    p_fail = MockLLMProvider(mode="failure")
    with pytest.raises(LLMUnavailableError):
        await p_fail.generate("test")

    # Malformed JSON
    p_malformed = MockLLMProvider(mode="malformed_json")
    with pytest.raises(LLMMalformedOutputError):
        await p_malformed.generate_structured("test", response_schema=LLMAnswerProposal)


@pytest.mark.asyncio
async def test_mock_provider_adversarial_modes():
    """Verifies fabricated citation and hallucinated number mock modes."""
    p_fab = MockLLMProvider(mode="fabricated_citation")
    prop_fab = await p_fab.generate_structured("test", response_schema=LLMAnswerProposal)
    assert 99 in prop_fab.citation_ids

    p_num = MockLLMProvider(mode="hallucinated_number")
    prop_num = await p_num.generate_structured("test", response_schema=LLMAnswerProposal)
    assert "90 days" in prop_num.answer


@pytest.mark.asyncio
async def test_mock_provider_custom_handler():
    """Verifies custom callback handler support for fine-grained test injections."""
    def custom_fn(prompt, sys_prompt):
        return LLMAnswerProposal(
            answer="Custom answer [1]",
            claims=[LLMClaimProposal(claim_text="Custom answer", citation_ids=[1])],
            citation_ids=[1],
            insufficient_evidence=False,
            conflicts_detected=False,
        )

    provider = MockLLMProvider(custom_handler=custom_fn)
    prop = await provider.generate_structured("test", response_schema=LLMAnswerProposal)
    assert prop.answer == "Custom answer [1]"


def test_provider_factory():
    """Verifies factory instantiation of providers."""
    mock_p = get_llm_provider("mock")
    assert isinstance(mock_p, MockLLMProvider)

    openai_p = get_llm_provider("openai", api_key="sk-test", base_url="http://localhost:8000/v1")
    assert isinstance(openai_p, OpenAICompatibleLLMProvider)
    assert openai_p.base_url == "http://localhost:8000/v1"
