import asyncio
import json
import re

from api.config import FAST_CONTEXT_CHAR_LIMIT, FAST_CONTEXT_LIMIT, SEARCH_TOP_K
from knb.dgraph_unified_storage import DgraphKVStorage
from knb.package_downloads import package_download_answer
from ragu.common.global_parameters import DEFAULT_FILENAMES


STOP_WORDS = {
    "что", "это", "как", "для", "про", "дай", "или", "при", "надо", "нужно",
    "можно", "какая", "какие", "какой", "где", "если", "версия", "версии",
    "скачать", "ссылку", "package", "download",
}


def _answer_text(answer):
    if isinstance(answer, dict):
        if "answer" in answer:
            return str(answer["answer"])
        return json.dumps(answer, ensure_ascii=False, indent=2)

    if hasattr(answer, "response"):
        return str(answer.response)

    return str(answer)


def _has_context(context):
    return any(
        (
            getattr(context, "entities", None),
            getattr(context, "relations", None),
            getattr(context, "summaries", None),
            getattr(context, "chunks", None),
        )
    )


def _conversation(question, context_text):
    system_prompt = (
        "Ты отвечаешь по извлечённому контексту из документации и графа знаний. "
        "Главный приоритет — факты из контекста.\n"
        "Правила:\n"
        "1. Если ответ есть в контексте, опирайся именно на него.\n"
        "2. Не придумывай собственные примеры, если в контексте уже есть пример; "
        "используй именно пример из контекста.\n"
        "3. Если контекст покрывает вопрос только частично, можно добавить немного общих знаний, "
        "но только в отдельном абзаце, который начинается с 'Дополнение вне контекста:'.\n"
        "4. Не выдавай добавленные сведения за факты из документации.\n"
        "5. Если пользователь описывает нужный пакет без точного имени, сам сопоставь задачу с пакетами из контекста. "
        "Можно выбрать наиболее подходящий вариант, но только если он реально есть в контексте.\n"
        "6. Если уверенность низкая, дай 2-3 кандидата из контекста и коротко объясни различия.\n"
        "7. Если в контексте нет подходящего пакета или факта, прямо скажи, что в найденном контексте информации недостаточно.\n"
        "8. Отвечай по-русски, но имена API, сигнатуры и код не переводи."
    )
    user_prompt = (
        f"Вопрос:\n{question}\n\n"
        f"Контекст:\n{context_text}\n\n"
        "Сформируй краткий ответ по контексту. Если пользователь дал описание вместо точного имени пакета, "
        "сначала пойми, какой пакет из контекста подходит под задачу, и не предлагай пакеты вне контекста. "
        "Если в контексте есть пример кода, приведи именно его."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _search_terms(question):
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_.@/+:-]{3,}", question or "")
    terms = []
    for word in words:
        value = word.strip(".,!?;:()[]{}<>\\\"'`").lower()
        if len(value) < 3 or value in STOP_WORDS:
            continue
        terms.append(value)
    return " ".join(dict.fromkeys(terms).keys())


def _row_content(row):
    value = row.get("ragu_value_json")
    if not isinstance(value, str):
        return ""

    try:
        payload = json.loads(value)
    except Exception:
        return value

    if isinstance(payload, dict):
        return str(payload.get("content") or payload.get("text") or "")
    return str(payload)


def _fast_context_from_dgraph(question, dgraph_address):
    terms = _search_terms(question)
    if not terms:
        return ""

    storage = DgraphKVStorage(
        address=dgraph_address,
        filename=DEFAULT_FILENAMES["chunks_kv_storage_name"],
    )
    try:
        rows = storage.search_text_rows(terms, limit=FAST_CONTEXT_LIMIT)
    except Exception:
        return ""
    finally:
        storage.close()

    chunks = []
    for row in rows:
        content = _row_content(row).strip()
        if content:
            chunks.append(f"CHUNK_ID: {row.get('ragu_key', '')}\n{content}")

    context_text = "\n\n---\n\n".join(chunks).strip()
    return context_text[:FAST_CONTEXT_CHAR_LIMIT]


async def _answer_from_fast_context(question, llm, context_text):
    answer = await llm.chat_completion(
        conversation=_conversation(question, context_text),
        output_schema=str,
        temperature=0,
    )
    return _answer_text(answer), context_text


async def answer_with_context(question, search_engine, llm, dgraph_address):
    direct_answer = package_download_answer(question, dgraph_address)
    if direct_answer is not None:
        return direct_answer

    fast_context = _fast_context_from_dgraph(question, dgraph_address)
    if fast_context:
        return await _answer_from_fast_context(question, llm, fast_context)

    context = await search_engine.a_search(question, top_k=SEARCH_TOP_K)
    context_text = search_engine.truncation(str(context)).strip()

    if not _has_context(context) or not context_text:
        return (
            "В найденном контексте недостаточно информации, чтобы надёжно ответить на вопрос.",
            context_text,
        )

    answer = await llm.chat_completion(
        conversation=_conversation(question, context_text),
        output_schema=str,
        temperature=0,
    )
    return _answer_text(answer), context_text


async def answer_with_timeout(question, search_engine, llm, dgraph_address, timeout):
    return await asyncio.wait_for(
        answer_with_context(question, search_engine, llm, dgraph_address),
        timeout=timeout,
    )
