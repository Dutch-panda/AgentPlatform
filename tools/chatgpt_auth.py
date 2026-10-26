import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from pydantic_ai.models import infer_model, Model
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai_chatgpt import (
    OpenAIChatGPTCredentials,
    OpenAIChatGPTCredentialSource,
    OpenAIChatGPTOAuthFlow,
    OpenAIChatGPTProvider,
)


class FileCredentialSource(OpenAIChatGPTCredentialSource):
    def __init__(self, path: Path):
        self.path = path

    async def load(self) -> OpenAIChatGPTCredentials:
        return OpenAIChatGPTCredentials(**json.loads(self.path.read_text(encoding="utf-8")))

    async def save(self, credentials: OpenAIChatGPTCredentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                os.fchmod(temporary.fileno(), 0o600)
                json.dump(asdict(credentials), temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def resolve_model_name(name: str) -> str:
    """Normalize model names by adding appropriate provider prefix if missing."""
    if ":" in name:
        return name
    lower = name.lower()
    if lower.startswith("claude"):
        return f"anthropic:{name}"
    if lower.startswith("gemini"):
        return f"google:{name}"
    if lower.startswith(("gpt-", "o1", "o3", "chatgpt", "text-embedding")):
        return f"openai:{name}"
    return name


async def get_model(model_name: str | None = None) -> Model:
    """
    Resolves the execution model according to priority:
    1. Explicit model string or CLI argument (e.g. 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet-latest')
    2. Environment model (LLM_MODEL or MODEL_NAME)
    3. Direct API Keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY
    4. ChatGPT OAuth sign-in flow (fallback)
    """
    model_override = model_name or os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME")
    if model_override:
        return infer_model(resolve_model_name(model_override))

    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("USE_CHATGPT_OAUTH"):
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        return infer_model(resolve_model_name(openai_model if ":" in openai_model else f"openai:{openai_model}"))

    if os.environ.get("ANTHROPIC_API_KEY"):
        anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        return infer_model(resolve_model_name(anthropic_model if ":" in anthropic_model else f"anthropic:{anthropic_model}"))

    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        return infer_model(resolve_model_name(gemini_model if ":" in gemini_model else f"google:{gemini_model}"))

    project_dir = Path(__file__).resolve().parent.parent
    auth_path = Path(os.environ.get("CHATGPT_AUTH_FILE", ".env.chatgpt-auth.json")).expanduser()
    if not auth_path.is_absolute():
        auth_path = project_dir / auth_path
    source = FileCredentialSource(auth_path)
    saved = await source.load() if source.path.exists() else None
    if saved is None or not saved.plan_usage_granted:
        flow = OpenAIChatGPTOAuthFlow(
            app_name="BuildRelay",
            client_id=saved.client_id if saved else None,
            id_token_hint=saved.id_token if saved else None,
        )
        print("Open this URL in your browser and sign in with ChatGPT:")
        print(flow.authorization_url(extra_params={"prompt": "consent"}))
        await source.save(await flow.exchange_code_from_callback())
    return OpenAIResponsesModel(
        os.environ.get("OPENAI_MODEL", "gpt-6.1-sol"),
        provider=OpenAIChatGPTProvider(credential_source=source),
    )


async def get_chatgpt_model(model_name: str | None = None) -> Model:
    """Backward-compatible wrapper for get_model."""
    return await get_model(model_name)
