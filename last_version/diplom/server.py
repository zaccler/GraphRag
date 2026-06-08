import asyncio
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.config import (
    ASK_TIMEOUT_SEC,
    DGRAPH_ADDRESS,
    DHB_DIR,
    DOCS_RAW_DIR,
    DOCS_REGISTRY_PATH,
    INDEX_MANIFEST_PATH,
    PACKAGE_RAW_DIR,
    PACKAGE_REGISTRY_PATH,
    RAW_LIT_DIR,
    STORAGE_DIR,
)
from api.models import (
    AskDebugResponse,
    AskRequest,
    AskResponse,
    AuthCodeRequest,
    AuthResponse,
    AuthVerifyRequest,
    ChatHistoryRequest,
    ChatLogRequest,
    ParseDocsRegistryRequest,
    ParsePackagesRequest,
    ParseUrlRequest,
    StatusResponse,
)
from dhb.chat_logs import CHAT_LOG_PATH, load_chat_history, save_chat_log
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
    build_local_llm,
    close_graph_clients,
    filter_unindexed_files,
    has_persisted_index,
    list_text_files,
    mark_files_indexed,
    migrate_local_runtime_storage_to_dgraph,
    rebuild_transactionally_from_files,
)
from xdt.scp.parser import (
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


def select_answer_llm(mode):
    value = (mode or "api").strip().lower()
    if value == "local":
        if app.state.local_llm is None:
            raise HTTPException(status_code=503, detail="Local LLM is not initialized")
        return app.state.local_llm
    return app.state.llm


def record_background_failure(label: str, exc: Exception):
    app.state.last_error = repr(exc)
    app.state.phase = "idle" if has_live_index() else "error"
    print(f"{label}:", repr(exc))


ASK_TIMEOUT_ANSWER = 'Ответ формируется слишком долго. Попробуйте сформулировать вопрос точнее или спросить про конкретный пакет, функцию, версию или ссылку.'


def should_rebuild_after_parse(result: dict):
    if result.get("count", 0) > 0:
        return True, "new files parsed"

    if result.get("skipped") and not has_persisted_index():
        return True, "local files already exist, but Dgraph index is empty"

    return False, "no new files parsed"


def index_text_files(file_paths, force_all=False):
    candidates = []
    for file_path in file_paths or []:
        path = Path(file_path)
        if path.exists() and path.is_file():
            candidates.append(path)

    if force_all:
        files = candidates
        skipped = []
    else:
        files, skipped = filter_unindexed_files(candidates, INDEX_MANIFEST_PATH)

    info = {
        "manifest_path": str(INDEX_MANIFEST_PATH),
        "candidate_count": len(candidates),
        "index_count": len(files),
        "skipped_indexed": len(skipped),
        "force_all": force_all,
        "files": [str(file_path) for file_path in files[:20]],
    }

    if not files:
        info["status"] = "no_new_files"
        return info

    components = rebuild_transactionally_from_files(files)
    activate_runtime_components(components)
    info["manifest"] = mark_files_indexed(files, INDEX_MANIFEST_PATH)
    info["status"] = "indexed"
    return info


def background_rebuild(folder_path: str, force_all: bool = False):
    with app.state.index_lock:
        if app.state.is_processing:
            return
        app.state.is_processing = True
        app.state.last_error = None
        app.state.last_result = {
            "kind": "rebuild",
            "status": "running",
            "folder_path": folder_path,
            "force_all": force_all,
        }
        app.state.phase = "indexing"

    try:
        files = list_text_files(Path(folder_path))
        should_force = force_all or not has_persisted_index()
        index_info = index_text_files(files, force_all=should_force)
        app.state.last_result = {
            "kind": "rebuild",
            "status": "done",
            "folder_path": folder_path,
            "force_all": should_force,
            "index": index_info,
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
            force_all = result.get("count", 0) == 0 and not has_persisted_index()
            candidates = result.get("files") or list_text_files(Path(target_dir))
            index_info = index_text_files(candidates, force_all=force_all)
            app.state.last_result["index"] = index_info
            app.state.last_result["indexed"] = index_info.get("index_count", 0) > 0
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
            force_all = result.get("count", 0) == 0 and not has_persisted_index()
            candidates = result.get("files") or list_text_files(Path(target_dir))
            index_info = index_text_files(candidates, force_all=force_all)
            app.state.last_result["index"] = index_info
            app.state.last_result["indexed"] = index_info.get("index_count", 0) > 0
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






@app.on_event("shutdown")
async def shutdown():
    components = (
        getattr(app.state, "llm", None),
        getattr(app.state, "embedder", None),
        getattr(app.state, "local_llm", None),
    )
    await close_graph_clients(components)
@app.on_event("startup")
async def startup():
    ensure_dirs()
    app.state.last_error = None
    app.state.last_result = None
    app.state.llm = None
    app.state.embedder = None
    app.state.knowledge_graph = None
    app.state.search_engine = None
    app.state.local_llm = None
    app.state.is_processing = False
    app.state.phase = "idle"
    app.state.index_lock = threading.Lock()
    app.state.local_llm = build_local_llm()
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



@app.get("/status", response_model=StatusResponse)
async def status():
    return {
        "is_processing": app.state.is_processing,
        "phase": app.state.phase,
        "last_error": app.state.last_error,
        "last_result": app.state.last_result,
    }



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


@app.post("/dhb/chat-history")
async def dhb_chat_history(request: ChatHistoryRequest):
    email = clean_email(request.email)
    history = await load_chat_history(email, request.limit)
    return {
        "status": "ok",
        "email": email,
        **history,
    }


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail='Индекс сейчас перестраивается')
    if app.state.search_engine is None:
        raise HTTPException(status_code=503, detail="Search engine ещё не инициализирован")

    try:
        answer, _ = await answer_with_timeout(
            request.question,
            app.state.search_engine,
            select_answer_llm(request.llm_mode),
            DGRAPH_ADDRESS,
            ASK_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return {"answer": ASK_TIMEOUT_ANSWER}
    return {"answer": answer}


@app.post("/ask_debug", response_model=AskDebugResponse)
async def ask_debug(request: AskRequest):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail='Индекс сейчас перестраивается')
    if app.state.search_engine is None:
        raise HTTPException(status_code=503, detail="Search engine ещё не инициализирован")

    try:
        answer, retrieved_context = await answer_with_timeout(
            request.question,
            app.state.search_engine,
            select_answer_llm(request.llm_mode),
            DGRAPH_ADDRESS,
            ASK_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return {
            "answer": ASK_TIMEOUT_ANSWER,
            "raw_result": {"question": request.question, "llm_mode": request.llm_mode, "timeout_sec": ASK_TIMEOUT_SEC},
            "response_type": "TimeoutFallbackResponse",
            "retrieved_context": "",
        }
    return {
        "answer": answer,
        "raw_result": {"question": request.question, "llm_mode": request.llm_mode},
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

    force_all = not has_persisted_index()
    if force_all:
        pending = files
        skipped = []
    else:
        pending, skipped = filter_unindexed_files(files, INDEX_MANIFEST_PATH)

    background_tasks.add_task(background_rebuild, str(RAW_LIT_DIR), force_all)
    return {
        "status": "accepted",
        "count": len(files),
        "pending_count": len(pending),
        "skipped_indexed": len(skipped),
        "force_all": force_all,
    }




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

    background_tasks.add_task(background_rebuild, str(target_dir), True)
    return {"status": "accepted", "saved_path": saved_path, "text_db_mirror": sheet_mirror}





@app.post("/parse/docs-registry")
async def parse_docs_registry(request: ParseDocsRegistryRequest, background_tasks: BackgroundTasks):
    if app.state.is_processing:
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

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
        raise HTTPException(status_code=409, detail="Сервис уже выполняет обработку")

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


