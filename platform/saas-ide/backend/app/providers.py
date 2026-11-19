"""Explicit provider adapters. Never silently fall back to another paid provider."""
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    key_env: str

MODELS = {
    "openai": ModelConfig("openai", "IDE_OPENAI_MODEL", "OPENAI_API_KEY"),
    "anthropic": ModelConfig("anthropic", "IDE_ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"),
    "gemini": ModelConfig("gemini", "IDE_GEMINI_MODEL", "GEMINI_API_KEY"),
    "oci": ModelConfig("oci", "IDE_OCI_MODEL", "OCI_CONFIG_FILE"),
    "openrouter": ModelConfig("openrouter", "IDE_OPENROUTER_MODEL", "OPENROUTER_API_KEY"),
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def configured_model(provider: str) -> str:
    if provider not in MODELS:
        raise ValueError("Unsupported provider")
    cfg = MODELS[provider]
    model = os.getenv(cfg.model, "").strip()
    if not model or not os.getenv(cfg.key_env):
        raise RuntimeError(f"{provider} model/credentials not configured")
    return model

def generate(provider: str, prompt: str, max_tokens: int = 1200) -> str:
    """Text-only provider-specific SDK calls; caller enforces approvals, budgets and timeouts."""
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true":
        raise PermissionError("External model execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    if not 1 <= max_tokens <= 2000 or len(prompt) > 16000:
        raise ValueError("Model budget exceeded")
    model = configured_model(provider)
    from .transport211 import sdk_http_client
    if provider == "openrouter":
        return generate_metered(provider, prompt, max_tokens=max_tokens)["text"]
    if provider not in ("openai", "anthropic"):
        raise PermissionError("Provider SDK transport not gateway-integrated; disabled")
    if provider == "openai":
        from openai import OpenAI
        with sdk_http_client() as transport, OpenAI(timeout=30, max_retries=0, http_client=transport) as client:
            response = client.responses.create(model=model, input=prompt, max_output_tokens=max_tokens)
            return response.output_text
    if provider == "anthropic":
        from anthropic import Anthropic
        with sdk_http_client() as transport, Anthropic(timeout=30, max_retries=0, http_client=transport) as client:
            response = client.messages.create(model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}])
            return "".join(x.text for x in response.content if x.type == "text")
    if provider == "gemini":
        from google import genai
        from google.genai import types
        with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
            response = client.models.generate_content(model=model, contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens))
            return response.text or ""
    if provider == "oci":
        import oci
        config = oci.config.from_file(os.environ["OCI_CONFIG_FILE"],
                                      os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"))
        compartment = os.environ["IDE_OCI_COMPARTMENT_OCID"]
        endpoint = os.environ["IDE_OCI_GENAI_ENDPOINT"]
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(config, service_endpoint=endpoint,
            retry_strategy=oci.retry.NoneRetryStrategy())
        details = oci.generative_ai_inference.models.ChatDetails(
            compartment_id=compartment,
            serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(model_id=model),
            chat_request=oci.generative_ai_inference.models.GenericChatRequest(
                messages=[oci.generative_ai_inference.models.UserMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=prompt)])],
                max_tokens=max_tokens))
        response = client.chat(details)
        return "\n".join(item.text for choice in response.data.chat_response.choices
                         for item in choice.message.content if hasattr(item, "text"))
    raise ValueError("Unsupported provider")


def generate_metered(provider: str, prompt: str, max_tokens: int = 1200, *,
                     system: str = "", client=None) -> dict:
    """OpenRouter chat completion through the verified gateway, with the provider's own usage
    receipt (tokens and USD cost) so spend is reconciled per call rather than estimated.

    Returns {"text", "model", "request_id", "prompt_tokens", "completion_tokens", "cost_microusd"}.
    cost_microusd is None when the provider did not report a cost; callers must then charge the
    full reservation.
    """
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true":
        raise PermissionError("External model execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    if provider != "openrouter":
        raise PermissionError("Metered transport is only integrated for OpenRouter")
    if not 1 <= max_tokens <= 2000 or len(prompt) > 16000 or len(system) > 4000:
        raise ValueError("Model budget exceeded")
    model = configured_model(provider)
    body = {"model": model, "max_tokens": max_tokens, "usage": {"include": True},
            "messages": ([{"role": "system", "content": system}] if system else [])
                        + [{"role": "user", "content": prompt}]}
    headers = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
               "HTTP-Referer": os.getenv("IDE_PUBLIC_URL", "https://ide.softwareequality.com"),
               "X-Title": "AEP-X IDE"}
    if client is None:
        from .transport211 import sdk_http_client
        with sdk_http_client() as http:
            response = http.post(OPENROUTER_URL, json=body, headers=headers)
    else:
        response = client.post(OPENROUTER_URL, json=body, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Provider returned HTTP {response.status_code}")
    data = response.json()
    choices = data.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") if choices else None) or ""
    if not isinstance(text, str):
        raise ValueError("Provider output must be text")
    usage = data.get("usage") or {}
    cost = usage.get("cost")
    cost_microusd = None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
        cost_microusd = int(round(cost * 1_000_000))
    def _count(key):
        value = usage.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return {"text": text, "model": str(data.get("model") or model)[:120],
            "request_id": str(data.get("id") or "")[:160] or None,
            "prompt_tokens": _count("prompt_tokens"),
            "completion_tokens": _count("completion_tokens"),
            "cost_microusd": cost_microusd}
