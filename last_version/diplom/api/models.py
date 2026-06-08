from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    llm_mode: str = "api"


class AskResponse(BaseModel):
    answer: str


class AuthCodeRequest(BaseModel):
    email: str


class AuthVerifyRequest(BaseModel):
    email: str
    code: str


class AuthResponse(BaseModel):
    status: str
    email: str
    role: str
    ttl_sec: int | None = None


class ChatLogRequest(BaseModel):
    email: str
    question: str
    answer: str


class ChatHistoryRequest(BaseModel):
    email: str
    limit: int = 200


class AskDebugResponse(BaseModel):
    answer: str
    raw_result: dict | list | str | None
    response_type: str
    retrieved_context: str | None = None


class ParseUrlRequest(BaseModel):
    url: str
    target_dir: str | None = None


class ParsePackagesRequest(BaseModel):
    package_list_path: str | None = None
    target_dir: str | None = None
    max_sources: int | None = None
    force: bool = False


class ParseDocsRegistryRequest(BaseModel):
    registry_path: str | None = None
    target_dir: str | None = None
    max_sources: int | None = None
    force: bool = False


class StatusResponse(BaseModel):
    is_processing: bool
    phase: str
    last_error: str | None
    last_result: dict | list | str | None = None
