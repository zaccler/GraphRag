import json
import re

from ragu.common.global_parameters import DEFAULT_FILENAMES

from knb.dgraph_unified_storage import DgraphKVStorage


OVERVIEW_LIMIT = 40
OVERVIEW_EXAMPLES = 18


def _norm(value):
    return (value or "").strip().rstrip(".").lower()


def _query_parts(question):
    version_match = re.search(r"\b\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?\b", question)
    package_matches = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+\b", question)
    package = next((item for item in package_matches if not re.fullmatch(r"\d+(?:\.\d+)+", item)), None)
    version = version_match.group(0) if version_match else None
    return package, version


def _version_key(version):
    main, _, suffix = version.partition("-")
    nums = []
    for part in main.split("."):
        match = re.match(r"\d+", part)
        nums.append(int(match.group(0)) if match else 0)
    while len(nums) < 4:
        nums.append(0)
    return nums, 0 if suffix else 1, suffix


def _package_search_terms(question, package=None, version=None):
    skip = {"download", "package", "latest", "newest", "nupkg", "nuget"}
    if package:
        terms = [package]
        if version:
            terms.append(version)
        return " ".join(dict.fromkeys(terms).keys())

    terms = []
    if version:
        terms.append(version)
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.-]{2,}\b", question or ""):
        if token.lower() not in skip:
            terms.append(token)
    return " ".join(dict.fromkeys(terms).keys())


def _is_download_question(question):
    text = question.lower()
    return any(word in text for word in ("\u0441\u043a\u0430\u0447", "\u0441\u0441\u044b\u043b", "download", "nupkg", "\u0430\u0440\u0445\u0438\u0432"))


def _is_overview_question(question):
    text = question.lower()
    return any(
        phrase in text
        for phrase in (
            "\u0447\u0442\u043e \u0442\u044b \u043c\u043e\u0436\u0435\u0448\u044c",
            "\u0447\u0442\u043e \u043c\u043e\u0436\u0435\u0448\u044c",
            "\u0447\u0442\u043e \u0443\u043c\u0435\u0435\u0448\u044c",
            "\u0447\u0442\u043e \u0443 \u0442\u0435\u0431\u044f \u0435\u0441\u0442\u044c",
            "\u043a\u0430\u043a\u0438\u0435 \u043f\u0430\u043a\u0435\u0442\u044b",
            "\u043a\u0430\u043a\u0438\u0435 \u0431\u0438\u0431\u043b\u0438\u043e\u0442\u0435\u043a\u0438",
            "\u043a \u043a\u0430\u043a\u0438\u043c \u043f\u0430\u043a\u0435\u0442\u0430\u043c",
            "\u0447\u0442\u043e \u0435\u0441\u0442\u044c \u0432 \u0431\u0430\u0437\u0435",
            "\u0447\u0442\u043e \u0432 \u0431\u0430\u0437\u0435",
            "\u0447\u0442\u043e \u043b\u0435\u0436\u0438\u0442 \u0432 \u0431\u0430\u0437\u0435",
            "\u0447\u0442\u043e \u0437\u043d\u0430\u0435\u0448\u044c",
            "available packages",
        )
    )


def _chunk_texts(dgraph_address, terms=None, limit=20):
    storage = DgraphKVStorage(
        address=dgraph_address,
        filename=DEFAULT_FILENAMES["chunks_kv_storage_name"],
    )
    try:
        if terms:
            rows = storage.search_text_rows(terms, limit=limit)
        else:
            query = f"""
            query q($kind: string) {{
              rows(func: eq(ragu_store_kind, $kind), first: {limit}) @filter(type(RaguKV)) {{
                ragu_key
                ragu_value_json
              }}
            }}
            """
            rows = storage._query(query, {"$kind": storage.namespace}).get("rows", [])
        for row in rows:
            value = row.get("ragu_value_json")
            if not isinstance(value, str):
                continue
            try:
                value = json.loads(value)
            except Exception:
                continue
            if isinstance(value, dict) and isinstance(value.get("content"), str):
                yield value["content"]
    finally:
        storage.close()


def _field(text, *names):
    names = "|".join(re.escape(name) for name in names)
    match = re.search(rf"^(?:{names}):\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _download_url(value):
    return value.strip().rstrip(".")


def _block_record(block):
    package = _field(block, "PACKAGE")
    version = _field(block, "VERSION")
    download_url = _field(block, "DOWNLOAD_URL")
    install_command = _field(block, "INSTALL_COMMAND")
    if not package or not version or not download_url:
        return None
    return {
        "package": package.rstrip(".").strip(),
        "version": version.rstrip(".").strip(),
        "download_url": _download_url(download_url),
        "install_command": install_command.rstrip(".").strip(),
        "block": block,
    }


PACKAGE_RECORD_RE = re.compile(
    r"PACKAGE:\s*(?P<package>.*?)\.\s+"
    r"VERSION:\s*(?P<version>.*?)\.\s+"
    r"INSTALLER_TYPE:\s*(?P<installer_type>.*?)\.\s+"
    r"DOWNLOAD_URL:\s*(?P<download_url>.*?)\.\s+"
    r"NUSPEC_URL:\s*(?P<nuspec_url>.*?)\.\s+"
    r"INSTALL_COMMAND:\s*(?P<install_command>.*?)(?=\s+PACKAGE:\s|$)",
    flags=re.DOTALL,
)


def _record_from_match(match):
    return {
        "package": match.group("package").strip().rstrip("."),
        "version": match.group("version").strip().rstrip("."),
        "download_url": _download_url(match.group("download_url")),
        "install_command": match.group("install_command").strip().rstrip("."),
        "block": match.group(0).strip(),
    }


def _records_from_chunk(chunk_text):
    records = []
    seen = set()

    for block in chunk_text.split("\n\n"):
        record = _block_record(block)
        if not record:
            continue
        key = (record["package"].lower(), record["version"].lower(), record["download_url"].lower())
        if key not in seen:
            seen.add(key)
            records.append(record)

    for match in PACKAGE_RECORD_RE.finditer(chunk_text):
        record = _record_from_match(match)
        key = (record["package"].lower(), record["version"].lower(), record["download_url"].lower())
        if key not in seen:
            seen.add(key)
            records.append(record)

    return records


def _package_name_from_question(question, chunks):
    names = []
    seen = set()
    for chunk_text in chunks:
        for record in _records_from_chunk(chunk_text):
            name = record["package"]
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                names.append(name)

    question_lower = question.lower()
    matches = []
    for name in names:
        pattern = rf"(?<![\w.]){re.escape(name.lower())}(?![\w.])"
        if re.search(pattern, question_lower):
            matches.append(name)
    if not matches:
        return None
    return max(matches, key=len)


def _answer_for_record(record):
    answer = [
        f"\u0421\u043a\u0430\u0447\u0430\u0442\u044c {record['package']} {record['version']}:",
        record["download_url"],
    ]
    if record["install_command"]:
        answer.extend(["", f"\u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438: {record['install_command']}"])
    return "\n".join(answer), record["block"]


def _package_record(chunk_text):
    source_type = _field(chunk_text, "SOURCE_TYPE")
    package_manager = _field(chunk_text, "PACKAGE_MANAGER")
    package_id = _field(chunk_text, "PACKAGE_ID", "REPOSITORY", "MODULE", "IMAGE")

    group_id = _field(chunk_text, "GROUP_ID")
    artifact_id = _field(chunk_text, "ARTIFACT_ID")
    if not package_id and group_id and artifact_id:
        package_id = f"{group_id}:{artifact_id}"

    if not package_id or "\n" in package_id:
        return None

    package_id = package_id.rstrip(".").strip()
    if not package_id or len(package_id) > 120:
        return None

    if not package_manager:
        if source_type.startswith("github"):
            package_manager = "GitHub"
        elif source_type.endswith("_package"):
            package_manager = source_type.replace("_package", "").upper()
        elif source_type == "go_module":
            package_manager = "Go modules"
        elif source_type == "docker_image":
            package_manager = "Docker Hub"
        else:
            package_manager = source_type or "package"

    return {
        "manager": package_manager.rstrip(".").strip(),
        "name": package_id,
    }


def _package_records(dgraph_address, limit=1000):
    records = []
    seen = set()
    for chunk_text in _chunk_texts(dgraph_address, limit=limit):
        record = _package_record(chunk_text)
        if not record:
            continue
        key = (record["manager"].lower(), record["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    return records


def package_overview_answer(question, dgraph_address):
    if not _is_overview_question(question):
        return None

    records = _package_records(dgraph_address)
    if not records:
        return (
            "\u0412 \u0431\u0430\u0437\u0435 \u043f\u043e\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0441\u043f\u0438\u0441\u043e\u043a \u043f\u0430\u043a\u0435\u0442\u043e\u0432. \u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0443\u0441\u0442\u0438 \u043f\u0430\u0440\u0441\u0438\u043d\u0433 packages.txt \u0438 rebuild/indexing.",
            "",
        )

    records.sort(key=lambda item: (item["manager"].lower(), item["name"].lower()))
    shown = records[:OVERVIEW_LIMIT]
    examples = ", ".join(item["name"] for item in shown[:OVERVIEW_EXAMPLES])

    managers = []
    for record in records:
        if record["manager"] not in managers:
            managers.append(record["manager"])

    manager_text = ", ".join(managers[:6])
    if len(managers) > 6:
        manager_text += f" \u0438 \u0435\u0449\u0451 {len(managers) - 6}"

    answer = (
        f"\u0412 \u0431\u0430\u0437\u0435 \u0441\u0435\u0439\u0447\u0430\u0441 \u0435\u0441\u0442\u044c {len(records)} \u043f\u0430\u043a\u0435\u0442\u043e\u0432/\u0440\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0435\u0432; \u043e\u0441\u043d\u043e\u0432\u043d\u044b\u0435 \u0433\u0440\u0443\u043f\u043f\u044b: {manager_text}. "
        f"\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: {examples}. "
        "\u041c\u043e\u0436\u0435\u0448\u044c \u0441\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u0440\u043e \u0432\u0435\u0440\u0441\u0438\u044e, \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0441\u043a\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u0435 \u0438\u043b\u0438 \u043e\u043f\u0438\u0441\u0430\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443 \u0441\u0432\u043e\u0438\u043c\u0438 \u0441\u043b\u043e\u0432\u0430\u043c\u0438."
    )
    context = "\n".join(f"{item['manager']}: {item['name']}" for item in shown)
    return answer, context


def package_download_answer(question, dgraph_address):
    if not _is_download_question(question):
        return None

    package, version = _query_parts(question)
    terms = _package_search_terms(question, package, version)
    chunks = list(_chunk_texts(dgraph_address, terms, limit=80))
    if not chunks:
        return None

    if not package:
        package = _package_name_from_question(question, chunks)
    if not package:
        return None

    records = []
    for chunk_text in chunks:
        for record in _records_from_chunk(chunk_text):
            if _norm(record["package"]) != _norm(package):
                continue
            records.append(record)

    if not records:
        return None

    if version:
        for record in records:
            if _norm(record["version"]) == _norm(version):
                return _answer_for_record(record)
        return None

    latest = max(records, key=lambda item: _version_key(item["version"]))
    return _answer_for_record(latest)
