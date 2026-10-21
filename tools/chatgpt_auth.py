import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

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


async def get_chatgpt_model() -> OpenAIResponsesModel:
    project_dir = Path(__file__).resolve().parent.parent
    auth_path = Path(os.environ.get("CHATGPT_AUTH_FILE", ".env.chatgpt-auth.json")).expanduser()
    if not auth_path.is_absolute():
        auth_path = project_dir / auth_path
    source = FileCredentialSource(auth_path)
    saved = await source.load() if source.path.exists() else None
    if saved is None or not saved.plan_usage_granted:
        flow = OpenAIChatGPTOAuthFlow(
            app_name="AP-V2",
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
