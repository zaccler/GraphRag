import asyncio
import json
import threading
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.config import (
    ASK_TIMEOUT_SEC,
    CRAWL_DELAY_SEC,
    CRAWL_MAX_PAGES,
    DGRAPH_ADDRESS,
    DHB_DIR,
    DOCS_RAW_DIR,
    DOCS_REGISTRY_PATH,
    GENERATED_DIR,
    PACKAGE_RAW_DIR,
    PACKAGE_REGISTRY_PATH,
    PYTHON_DOCS_ROOT,
    RAW_LIT_DIR,
    REGISTRY_PATH,
    STORAGE_DIR,
)
from api.models import (
    AskDebugResponse,
    AskRequest,
    AskResponse,
    AuthCodeRequest,
    AuthResponse,
    AuthVerifyRequest,
    ChatLogRequest,
    DhbGoogleSheetRequest,
    ExportTextDbRequest,
    HealthResponse,
    IngestFolderRequest,
    IngestJsonRequest,
    ParseDocsRegistryRequest,
    ParsePackagesRequest,
    ParsePythonDocsRequest,
    ParseRegistryRequest,
    ParseUrlRequest,
    StatusResponse,
)
from dhb.chat_logs import CHAT_LOG_PATH, save_chat_log
from dhb.dashboard import sync_google_sheet_dashboard
from dhb.text_db_mirror import mirror_text_db_files
from lms.answer_service import answer_with_timeout
from mgr.auth_service import (
    AUTH_CODE_TTL_SEC,
    generate_auth_code as make_auth_code,
    normalize_email as clean_email,
    send_auth_code_email as send_login_code,
    store_auth_code as save_auth_code,
    verify_auth_code as check_auth_code,
)
from knb.ragu_runtime import (
    build_graph_components,
    has_persisted_index,
    list_text_files,
    migrate_local_runtime_storage_to_dgraph,
    rebuild_transactionally,
)
from xdt.scp.parser import (
    crawl_python_docs,
    parse_package_sources,
    parse_registry_sources,
    parse_single_doc_page,
)


app = FastAPI(title="GraphRAG API", version="0.3.0")


def ensure_dirs():
    RAW_LIT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    DHB_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    CHAT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def activate_runtime_components(components):
    llm, embedder, knowledge_graph, search_engine = components
    app.state.llm = llm
    app.state.embedder = embedder
    app.state.knowledge_graph = knowledge_graph
    app.state.search_engine = search_engine


def has_live_index():
    return app.state.search_engine is not None and app.state.knowledge_graph is not None


def record_background_failure(label: str, exc: Exception):
    app.state.last_error = repr(exc)
    app.state.phase = "idle" if has_live_index() else "error"
    print(f"{label}:", repr(exc))


def should_rebuild_after_parse(result: dict):
    if result.get("count", 0) > 0:
        return True, "new files parsed"

    if result.get("skipped") and not has_persisted_index():
        return True, "local files already exist, but Dgraph index is empty"

    return False, "no new files parsed"


def background_rebuild(folder_path: str):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "rebuild",
            "status": "running",
            "folder_path": folder_path,
        }
        app.state.phase = "indexing"

    try:
        components = rebuild_transactionally(Path(folder_path))
        activate_runtime_components(components)
        app.state.last_result = {
            "kind": "rebuild",
            "status": "done",
            "folder_path": folder_path,
        }
        app.state.last_error = None
        app.state.phase = "idle"
    except Exception as e:
        app.state.last_result = {
            "kind": "rebuild",
            "status": "failed",
            "folder_path": folder_path,
            "error": repr(e),
        }
        record_background_failure("BACKGROUND REBUILD ERROR", e)
    finally:
        app.state.is_processing = False


def background_parse_python_docs(root_url: str, max_pages: int, delay_sec: float, target_dir: str):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "python_docs",
            "status": "running",
            "root_url": root_url,
            "max_pages": max_pages,
            "target_dir": target_dir,
        }
        app.state.phase = "parsing"

    try:
        result = crawl_python_docs(
            root_url=root_url,
            output_dir=target_dir,
            max_pages=max_pages,
            delay_sec=delay_sec,
        )
        sheet_mirror = mirror_text_db_files(result.get("files", []), "python_docs")
        app.state.phase = "indexing"
        components = rebuild_transactionally(Path(target_dir))
        activate_runtime_components(components)
        app.state.last_result = {
            "kind": "python_docs",
            "status": "done",
            "root_url": root_url,
            "max_pages": max_pages,
            "target_dir": target_dir,
            "result": result,
            "text_db_mirror": sheet_mirror,
        }
        app.state.last_error = None
        app.state.phase = "idle"
    except Exception as e:
        app.state.last_result = {
            "kind": "python_docs",
            "status": "failed",
            "root_url": root_url,
            "max_pages": max_pages,
            "target_dir": target_dir,
            "error": repr(e),
        }
        record_background_failure("BACKGROUND PARSE ERROR", e)
    finally:
        app.state.is_processing = False


def background_parse_registry(
    registry_path: str,
    target_dir: str,
    error_label: str = "BACKGROUND REGISTRY ERROR",
    max_sources: int | None = None,
    force: bool = False,
):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "registry",
            "status": "running",
            "registry_path": registry_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
        }
        app.state.phase = "parsing"

    try:
        result = parse_registry_sources(registry_path, target_dir, max_sources=max_sources, force=force)
        sheet_mirror = mirror_text_db_files(result.get("files", []), "registry")
        app.state.last_result = {
            "kind": "registry",
            "status": "parsed",
            "registry_path": registry_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
            "result": result,
            "text_db_mirror": sheet_mirror,
        }
        print(f"REGISTRY PARSE RESULT: {app.state.last_result!r}")
        should_index, index_reason = should_rebuild_after_parse(result)
        app.state.last_result["indexed"] = False
        app.state.last_result["index_reason"] = index_reason
        if should_index:
            app.state.phase = "indexing"
            app.state.last_result["status"] = "indexing"
            components = rebuild_transactionally(Path(target_dir))
            activate_runtime_components(components)
            app.state.last_result["indexed"] = True
            app.state.last_result["status"] = "done"
        else:
            app.state.last_result["status"] = "done"
        app.state.last_error = None
        app.state.phase = "idle"
    except Exception as e:
        app.state.last_result = {
            "kind": "registry",
            "status": "failed",
            "registry_path": registry_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
            "error": repr(e),
        }
        record_background_failure(error_label, e)
    finally:
        app.state.is_processing = False


def background_parse_packages(
    package_list_path: str,
    target_dir: str,
    max_sources: int | None = None,
    force: bool = False,
):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "packages",
            "status": "running",
            "package_list_path": package_list_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
        }
        app.state.phase = "parsing"

    try:
        result = parse_package_sources(package_list_path, target_dir, max_sources=max_sources, force=force)
        sheet_mirror = mirror_text_db_files(result.get("files", []), "packages")
        app.state.last_result = {
            "kind": "packages",
            "status": "parsed",
            "package_list_path": package_list_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
            "result": result,
            "text_db_mirror": sheet_mirror,
        }
        print(f"PACKAGE PARSE RESULT: {app.state.last_result!r}")
        should_index, index_reason = should_rebuild_after_parse(result)
        app.state.last_result["indexed"] = False
        app.state.last_result["index_reason"] = index_reason
        if should_index:
            app.state.phase = "indexing"
            app.state.last_result["status"] = "indexing"
            components = rebuild_transactionally(Path(target_dir))
            activate_runtime_components(components)
            app.state.last_result["indexed"] = True
            app.state.last_result["status"] = "done"
        else:
            app.state.last_result["status"] = "done"
        app.state.last_error = None
        app.state.phase = "idle"
    except Exception as e:
        app.state.last_result = {
            "kind": "packages",
            "status": "failed",
            "package_list_path": package_list_path,
            "target_dir": target_dir,
            "max_sources": max_sources,
            "force": force,
            "error": repr(e),
        }
        record_background_failure("BACKGROUND PACKAGE PARSE ERROR", e)
    finally:
        app.state.is_processing = False


def background_export_text_db(folder_path: str, max_files: int | None = None):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "text_db_export",
            "status": "running",
            "folder_path": folder_path,
            "max_files": max_files,
        }
        app.state.phase = "syncing"

    try:
        files = list_text_files(Path(folder_path))
        result = mirror_text_db_files(files, "manual_export", max_files=max_files)
        app.state.last_result = {
            "kind": "text_db_export",
            "status": "done",
            "folder_path": folder_path,
            "max_files": max_files,
            "files_found": len(files),
            "text_db_mirror": result,
        }
        app.state.last_error = None
        app.state.phase = "idle"
    except Exception as e:
        app.state.last_result = {
            "kind": "text_db_export",
            "status": "failed",
            "folder_path": folder_path,
            "max_files": max_files,
            "error": repr(e),
        }
        record_background_failure("BACKGROUND TEXT DB EXPORT ERROR", e)
    finally:
        app.state.is_processing = False


def write_json_docs(items: list):
    ensure_dirs()
    created = 0
    for item in items:
        file_name = f"{uuid.uuid4().hex}.txt"
        path = GENERATED_DIR / file_name
        if isinstance(item, str):
            text = item
        else:
            text = json.dumps(item, ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
        created += 1
    return created


@app.on_event("startup")
async def startup():
    ensure_dirs()
    app.state.last_error = None
    app.state.last_result = None
    app.state.llm = None
    app.state.embedder = None
    app.state.knowledge_graph = None
    app.state.search_engine = None
    app.state.is_processing = False
    app.state.phase = "idle"
    app.state.index_lock = threading.Lock()
    try:
        await migrate_local_runtime_storage_to_dgraph()
    except Exception as exc:
        app.state.last_error = f"LOCAL STORAGE MIGRATION ERROR: {exc!r}"
    if not has_persisted_index():
        return

    app.state.phase = "loading"
    try:
        activate_runtime_components(build_graph_components())
        app.state.phase = "idle"
    except Exception as exc:
        app.state.last_error = repr(exc)
        app.state.phase = "error"


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
async def status():
    return {
        "is_processing": app.state.is_processing,
        "phase": app.state.phase,
        "last_error": app.state.last_error,
        "last_result": app.state.last_result,
    }


@app.get("/debug/error")
async def debug_error():
    return {"last_error": app.state.last_error}


@app.post("/auth/request-code")
async def auth_request_code(request: AuthCodeRequest):
    email = clean_email(request.email)
    code = make_auth_code()

    try:
        await asyncio.to_thread(send_login_code, email, code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Не удалось отправить код: {exc}") from exc

    save_auth_code(email, code)
    return {"status": "sent", "email": email, "ttl_sec": AUTH_CODE_TTL_SEC}


@app.post("/auth/verify-code", response_model=AuthResponse)
async def auth_verify_code(request: AuthVerifyRequest):
    email = clean_email(request.email)
    if not check_auth_code(email, request.code):
        raise HTTPException(status_code=401, detail="Неверный или просроченный код")

    return {"status": "verified", "email": email, "role": "user", "ttl_sec": None}


@app.post("/dhb/log-chat")
async def dhb_log_chat(request: ChatLogRequest):
    email = clean_email(request.email)
    return await save_chat_log(email, request.question, request.answer)


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Индекс сейчас перестраивается")
    if app.state.search_engine is None:
        raise HTTPException(status_code=503, detail="Search engine ещё не инициализирован")

    try:
        answer, _ = await answer_with_timeout(
            request.question,
            app.state.search_engine,
            app.state.llm,
            DGRAPH_ADDRESS,
            ASK_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Ответ формируется слишком долго. Попробуйте упростить вопрос или повторить позже (timeout {ASK_TIMEOUT_SEC:.0f}s).",
        ) from exc
    return {"answer": answer}


@app.post("/ask_debug", response_model=AskDebugResponse)
async def ask_debug(request: AskRequest):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Индекс сейчас перестраивается")
    if app.state.search_engine is None:
        raise HTTPException(status_code=503, detail="Search engine ещё не инициализирован")

    try:
        answer, retrieved_context = await answer_with_timeout(
            request.question,
            app.state.search_engine,
            app.state.llm,
            DGRAPH_ADDRESS,
            ASK_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Ответ формируется слишком долго. Попробуйте упростить вопрос или повторить позже (timeout {ASK_TIMEOUT_SEC:.0f}s).",
        ) from exc
    return {
        "answer": answer,
        "raw_result": {"question": request.question},
        "response_type": "GroundedServerResponse",
        "retrieved_context": retrieved_context,
    }


@app.post("/rebuild")
async def rebuild(background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    files = list_text_files(RAW_LIT_DIR)
    if not files:
        raise HTTPException(status_code=404, detail="В raw/lit нет документов")

    background_tasks.add_task(background_rebuild, str(RAW_LIT_DIR))
    return {"status": "accepted", "count": len(files)}


@app.post("/ingest/folder")
async def ingest_folder(request: IngestFolderRequest, background_tasks: BackgroundTasks):
    folder = Path(request.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Указанная папка не найдена")

    files = list_text_files(folder)
    if not files:
        raise HTTPException(status_code=404, detail="В указанной папке не найдено файлов")

    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    background_tasks.add_task(background_rebuild, str(folder))
    return {"status": "accepted", "count": len(files)}


@app.post("/ingest/json")
async def ingest_json(request: IngestJsonRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    count = write_json_docs(request.data)
    background_tasks.add_task(background_rebuild, str(GENERATED_DIR))
    return {"status": "accepted", "count": count}


@app.post("/parse/url")
async def parse_url(request: ParseUrlRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    target_dir = Path(request.target_dir or str(RAW_LIT_DIR / "manual"))
    target_dir.mkdir(parents=True, exist_ok=True)

    for old_file in target_dir.glob("*.txt"):
        old_file.unlink()

    saved_path = parse_single_doc_page(request.url, str(target_dir))
    sheet_mirror = await asyncio.to_thread(mirror_text_db_files, [saved_path], "manual_url")

    background_tasks.add_task(background_rebuild, str(target_dir))
    return {"status": "accepted", "saved_path": saved_path, "text_db_mirror": sheet_mirror}


@app.post("/dhb/sync-google-sheet")
async def dhb_sync_google_sheet(request: DhbGoogleSheetRequest):
    source = {
        "url": request.url,
        "csv_url": request.csv_url,
        "sheet_id": request.sheet_id,
        "gid": request.gid or "0",
    }
    result = sync_google_sheet_dashboard(source, request.output_dir or str(DHB_DIR))
    return {"status": "synced", **result}


@app.post("/dhb/export-text-db")
async def dhb_export_text_db(request: ExportTextDbRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Service is already processing another task")

    folder_path = request.folder_path or str(RAW_LIT_DIR)
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    background_tasks.add_task(background_export_text_db, folder_path, request.max_files)
    return {
        "status": "accepted",
        "folder_path": folder_path,
        "max_files": request.max_files,
    }


@app.post("/parse/registry")
async def parse_registry(request: ParseRegistryRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    registry_path = request.registry_path or str(REGISTRY_PATH)
    target_dir = request.target_dir or str(DOCS_RAW_DIR)
    background_tasks.add_task(
        background_parse_registry,
        registry_path,
        target_dir,
        "BACKGROUND REGISTRY ERROR",
        request.max_sources,
        request.force,
    )
    return {
        "status": "accepted",
        "registry_path": registry_path,
        "target_dir": target_dir,
        "max_sources": request.max_sources,
        "force": request.force,
    }


@app.post("/parse/docs-registry")
async def parse_docs_registry(request: ParseDocsRegistryRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="РЎРµСЂРІРёСЃ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚ РѕР±СЂР°Р±РѕС‚РєСѓ")

    registry_path = request.registry_path or str(DOCS_REGISTRY_PATH)
    target_dir = request.target_dir or str(DOCS_RAW_DIR)
    background_tasks.add_task(
        background_parse_registry,
        registry_path,
        target_dir,
        "BACKGROUND DOCS REGISTRY ERROR",
        request.max_sources,
        request.force,
    )
    return {
        "status": "accepted",
        "registry_path": registry_path,
        "target_dir": target_dir,
        "max_sources": request.max_sources,
        "force": request.force,
    }


@app.post("/parse/packages")
async def parse_packages(request: ParsePackagesRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="РЎРµСЂРІРёСЃ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚ РѕР±СЂР°Р±РѕС‚РєСѓ")

    package_list_path = request.package_list_path or str(PACKAGE_REGISTRY_PATH)
    target_dir = request.target_dir or str(PACKAGE_RAW_DIR)
    background_tasks.add_task(
        background_parse_packages,
        package_list_path,
        target_dir,
        request.max_sources,
        request.force,
    )
    return {
        "status": "accepted",
        "package_list_path": package_list_path,
        "target_dir": target_dir,
        "max_sources": request.max_sources,
        "force": request.force,
    }


@app.post("/parse/python-docs")
async def parse_python_docs(request: ParsePythonDocsRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

    root_url = request.root_url or PYTHON_DOCS_ROOT
    max_pages = request.max_pages or CRAWL_MAX_PAGES
    delay_sec = request.delay_sec if request.delay_sec is not None else CRAWL_DELAY_SEC
    target_dir = request.target_dir or str(RAW_LIT_DIR / "python312")

    background_tasks.add_task(
        background_parse_python_docs,
        root_url,
        max_pages,
        delay_sec,
        target_dir,
    )

    return {
        "status": "accepted",
        "root_url": root_url,
        "max_pages": max_pages,
        "target_dir": target_dir,
    }
