from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


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


class IngestJsonRequest(BaseModel):
    data: list


class IngestFolderRequest(BaseModel):
    folder_path: str


class ParseUrlRequest(BaseModel):
    url: str
    target_dir: str | None = None


class DhbGoogleSheetRequest(BaseModel):
    url: str | None = None
    csv_url: str | None = None
    sheet_id: str | None = None
    gid: str | None = None
    output_dir: str | None = None


class ExportTextDbRequest(BaseModel):
    folder_path: str | None = None
    max_files: int | None = None


class ParseRegistryRequest(BaseModel):
    registry_path: str | None = None
    target_dir: str | None = None
    max_sources: int | None = None
    force: bool = False


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


class ParsePythonDocsRequest(BaseModel):
    root_url: str | None = None
    max_pages: int | None = None
    delay_sec: float | None = None
    target_dir: str | None = None


class StatusResponse(BaseModel):
    is_processing: bool
    phase: str
    last_error: str | None
    last_result: dict | list | str | None = None


class HealthResponse(BaseModel):
    status: str
