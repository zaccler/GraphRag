import asyncio
import json
import re

from api.config import FAST_CONTEXT_CHAR_LIMIT, FAST_CONTEXT_LIMIT, GRAPH_SEARCH_TIMEOUT_SEC, SEARCH_TOP_K
from knb.dgraph_unified_storage import DgraphKVStorage
from knb.package_downloads import package_download_answer
from ragu.common.global_parameters import DEFAULT_FILENAMES


STOP_WORDS = {
    "что", "это", "как", "для", "про", "дай", "или", "при", "надо", "нужно",
    "можно", "какая", "какие", "какой", "где", "если", "версия", "версии",
    "скачать", "ссылку", "package", "download",
}


STOP_WORDS.update({
    'такое', 'такая', 'такой', 'такие',
    'что-то', 'чтонибудь', 'за', 'же',
    'язык', 'языка', 'языке', 'языком',
    'программирования', 'расскажи', 'объясни',
    'programming', 'language', 'tell', 'about',
})

TECH_SHORT_TERMS = {"c", "c++", "c#", "f#", "go", "js", "r"}
NO_CONTEXT_ANSWER = 'В найденном контексте недостаточно информации, чтобы надёжно ответить на вопрос.'


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
        "Если пользователь просит пример, код или использование, приведи пример из контекста."
        "Если вопрос общий/определение, отвечай кратко без примеров."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _search_terms(question):
    words = re.findall(r"[^\W_][\w.@/+:#-]*", question or "", flags=re.UNICODE)
    terms = []
    for word in words:
        value = word.strip(".,!?;:()[]{}<>\\\"'`").lower()
        if not value:
            continue
        if len(value) < 3 and value not in TECH_SHORT_TERMS:
            continue
        if value in STOP_WORDS:
            continue
        terms.append(value)
    return " ".join(dict.fromkeys(terms).keys())


def _term_pattern(term):
    escaped = re.escape(term.lower())
    return rf"(?<![\w+#.]){escaped}(?![\w+#.])"


def _term_count(text, term):
    return len(re.findall(_term_pattern(term), text.lower()))


def _definition_question(question):
    text = (question or "").lower()
    markers = (
        'что такое',
        'что за',
        'кто такой',
        'кто такая',
        'расскажи про',
        'объясни',
        "what is", "what are", "tell me about",
    )
    return any(marker in text for marker in markers)


def _context_headings(context_text):
    lines = []
    for line in (context_text or "").splitlines():
        value = line.strip()
        lower = value.lower()
        if lower.startswith(("title:", "entity:", "package:", "url:", "name:")):
            lines.append(value)
    return "\n".join(lines)


def _has_topic_in_headings(terms, context_text):
    headings = _context_headings(context_text)
    if not headings:
        return False
    return any(_term_count(headings, term) > 0 for term in terms)


def _context_is_relevant(question, context_text):
    if not context_text:
        return False
    if not _definition_question(question):
        return True

    terms = _search_terms(question).split()
    if not terms:
        return False
    if _has_topic_in_headings(terms, context_text):
        return True

    hit_count = sum(_term_count(context_text, term) for term in terms)
    if any(term in TECH_SHORT_TERMS for term in terms):
        return False
    return hit_count >= 4


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
    if fast_context and _context_is_relevant(question, fast_context):
        return await _answer_from_fast_context(question, llm, fast_context)

    try:
        context = await asyncio.wait_for(
            search_engine.a_search(question, top_k=SEARCH_TOP_K),
            timeout=GRAPH_SEARCH_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return NO_CONTEXT_ANSWER, ""

    context_text = search_engine.truncation(str(context)).strip()

    if not _has_context(context) or not _context_is_relevant(question, context_text):
        return NO_CONTEXT_ANSWER, ""

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
