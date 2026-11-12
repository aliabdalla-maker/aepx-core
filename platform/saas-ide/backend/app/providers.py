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
}

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
    if provider == "openai":
        from openai import OpenAI
        with OpenAI(timeout=30, max_retries=0) as client:
            response = client.responses.create(model=model, input=prompt, max_output_tokens=max_tokens)
            return response.output_text
    if provider == "anthropic":
        from anthropic import Anthropic
        with Anthropic(timeout=30, max_retries=0) as client:
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
