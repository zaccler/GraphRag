import json
import re

from ragu.common.global_parameters import DEFAULT_FILENAMES

from knb.dgraph_unified_storage import DgraphKVStorage


def _query_parts(question):
    version_match = re.search(r"\b\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?\b", question)
    package_matches = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+\b", question)
    package = next((item for item in package_matches if not re.fullmatch(r"\d+(?:\.\d+)+", item)), None)
    version = version_match.group(0) if version_match else None
    return package, version


def _is_download_question(question):
    text = question.lower()
    return any(word in text for word in ("скач", "ссыл", "download", "nupkg", "архив"))


def _chunk_texts(dgraph_address, limit=2000):
    storage = DgraphKVStorage(
        address=dgraph_address,
        filename=DEFAULT_FILENAMES["chunks_kv_storage_name"],
    )
    try:
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


def _download_url(value):
    return value.strip().rstrip(".")


def package_download_answer(question, dgraph_address):
    if not _is_download_question(question):
        return None

    package, version = _query_parts(question)
    if not package or not version:
        return None

    package_lower = package.lower()
    version_line = f"VERSION: {version}".lower()

    for chunk_text in _chunk_texts(dgraph_address):
        text_lower = chunk_text.lower()
        if package_lower not in text_lower or version_line not in text_lower:
            continue

        for block in chunk_text.split("\n\n"):
            block_lower = block.lower()
            if package_lower not in block_lower or version_line not in block_lower:
                continue

            download_url = ""
            install_command = ""
            for line in block.splitlines():
                if line.startswith("DOWNLOAD_URL:"):
                    download_url = _download_url(line.split(":", 1)[1])
                elif line.startswith("INSTALL_COMMAND:"):
                    install_command = line.split(":", 1)[1].strip().rstrip(".")

            if not download_url:
                continue

            answer = [f"Скачать {package} {version}:", download_url]
            if install_command:
                answer.extend(["", f"Команда установки: {install_command}"])
            return "\n".join(answer), block

    return None
