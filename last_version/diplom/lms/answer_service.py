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
    "скачать", "ссылку", "package", "download", "функция", "функцию", "метод",
    "класс", "модуль", "язык", "программирования", "такое", "значит", "работает",
    "используется", "python", "питон", "пайтон", "встроенная", "встроенный",
    "what", "which", "who", "where", "when", "why", "how", "is", "are",
    "was", "were", "it", "its", "in", "on", "at", "to", "from", "the",
    "a", "an", "and", "or", "of", "about", "tell", "explain",
}

TERM_ALIASES = {
    "питон": ["python", "пайтон"],
    "пайтон": ["python", "питон"],
    "python": ["питон", "пайтон"],
    "javascript": ["js", "джаваскрипт"],
    "js": ["javascript", "джаваскрипт"],
    "джаваскрипт": ["javascript", "js"],
    "node": ["nodejs", "node.js"],
    "nodejs": ["node", "node.js"],
    "node.js": ["node", "nodejs"],
    "nuget": ["нюгет", "нугет"],
    "нюгет": ["nuget", "нугет"],
    "нугет": ["nuget", "нюгет"],
    "docker": ["докер"],
    "докер": ["docker"],
    "npm": ["нпм"],
    "нпм": ["npm"],
    "package": ["пакет", "пакеты"],
    "пакет": ["package", "packages"],
    "пакеты": ["package", "packages"],
}

PYTHON_BUILTIN_HINTS = {
    "map", "filter", "zip", "range", "len", "sum", "min", "max", "sorted", "reversed",
    "enumerate", "int", "str", "list", "dict", "set", "tuple", "float", "bool", "print",
    "input", "open", "abs", "round", "all", "any", "isinstance", "issubclass", "super",
    "iter", "next", "callable", "dir", "help", "type", "id", "hash", "repr", "format",
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
        "Главный приоритет - факты из контекста.\n"
        "Правила:\n"
        "1. Если ответ есть в контексте, опирайся именно на него.\n"
        "2. Если пользователь спрашивает про конкретную функцию, метод, класс, пакет или версию, "
        "ответ должен быть именно про этот объект.\n"
        "3. Если в контексте есть информация про другой объект, не подменяй им ответ.\n"
        "4. Код-примеры давай только если они есть в контексте. "
        "Если примера в контексте нет, не придумывай его.\n"
        "5. Если контекст покрывает вопрос только частично, можно добавить немного общих знаний, "
        "но только в отдельном абзаце, который начинается с 'Дополнение вне контекста:'.\n"
        "6. Не выдавай добавленные сведения за факты из документации.\n"
        "7. Если пользователь описывает нужный пакет без точного имени, сам сопоставь задачу с пакетами из контекста. "
        "Можно выбрать наиболее подходящий вариант, но только если он реально есть в контексте.\n"
        "8. Если уверенность низкая, дай 2-3 кандидата из контекста и коротко объясни различия.\n"
        "9. Если в контексте нет подходящего пакета или факта, прямо скажи, что в найденном контексте информации недостаточно.\n"
        "10. Отвечай по-русски, но имена API, сигнатуры и код не переводи."
    )
    user_prompt = (
        f"Вопрос:\n{question}\n\n"
        f"Контекст:\n{context_text}\n\n"
        "Сформируй краткий ответ по контексту. Если пользователь спрашивает про конкретное имя API, "
        "сначала проверь, что это имя реально есть в контексте. Если его нет, скажи, что информации недостаточно. "
        "Если пользователь дал описание вместо точного имени пакета, сначала пойми, какой пакет из контекста подходит под задачу, "
        "и не предлагай пакеты вне контекста. Если в контексте есть пример кода, приведи именно его. Если примера кода нет, не добавляй новый пример."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _normalize_token(value):
    return value.strip(".,!?;:()[]{}<>\\\"'`").lower()


def _extract_tokens(question):
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_.@/+:-]{2,}", question or "")
    result = []
    for word in words:
        value = _normalize_token(word)
        if len(value) >= 2:
            result.append(value)
    return list(dict.fromkeys(result))


def _expand_terms(terms):
    result = []
    for term in terms:
        result.append(term)
        result.extend(TERM_ALIASES.get(term, []))
    return list(dict.fromkeys(result))


def _search_terms(question):
    tokens = _extract_tokens(question)
    terms = []
    for value in tokens:
        if len(value) < 3 or value in STOP_WORDS:
            continue
        terms.append(value)
    terms = _expand_terms(terms)
    if any(token in {"python", "питон", "пайтон"} for token in tokens):
        terms.append("python")
    return " ".join(dict.fromkeys(terms).keys())


def _quoted_terms(question):
    result = []
    for value in re.findall(r"[`'\"]([^`'\"]{2,80})[`'\"]", question or ""):
        token = _normalize_token(value)
        if token:
            result.append(token)
    return result


def _required_terms(question):
    tokens = _extract_tokens(question)
    quoted = _quoted_terms(question)
    required = []

    for item in quoted:
        if item not in STOP_WORDS:
            required.append(item)

    api_patterns = [
        r"(?:функци[яюи]|метод|класс|модуль|оператор|пакет)\s+[`'\"]?([A-Za-z_][A-Za-z0-9_.-]{1,80})[`'\"]?",
        r"([A-Za-z_][A-Za-z0-9_.-]{1,80})\s*(?:\(|в\s+python)",
    ]
    for pattern in api_patterns:
        for value in re.findall(pattern, question or "", flags=re.IGNORECASE):
            token = _normalize_token(value)
            if token and token not in STOP_WORDS:
                required.append(token)

    for token in tokens:
        if token in PYTHON_BUILTIN_HINTS:
            required.append(token)

    return list(dict.fromkeys(required))


def _text_has_term(text, term):
    text_l = (text or "").lower()
    term_l = term.lower()
    if not term_l:
        return True
    if re.search(rf"(?<![a-zа-яё0-9_]){re.escape(term_l)}(?![a-zа-яё0-9_])", text_l, flags=re.IGNORECASE):
        return True
    if f"`{term_l}`" in text_l:
        return True
    if f"{term_l}(" in text_l:
        return True
    return False


def _context_has_required_terms(context_text, question):
    required = _required_terms(question)
    if not required:
        return True
    return all(_text_has_term(context_text, term) for term in required)


def _api_name_score(content, term):
    term_l = term.lower()
    if not re.match(r"^[a-z_][a-z0-9_]*$", term_l):
        return 0

    text_l = (content or "").lower()
    compact = re.sub(r"\s+", "", text_l)
    score = 0

    if f"#{term_l}" in text_l:
        score += 180
    if re.search(rf"(^|\n)\s*(?:class\s+|def\s+)?{re.escape(term_l)}\s*\(", text_l):
        score += 180
    if f"{term_l}(" in compact:
        score += 160

    return score

def _question_asks_example(question):
    text = (question or "").lower()
    return any(word in text for word in ("Пример", "Пример?", "???", "example", "examples", "code"))


def _context_has_code_example(context_text):
    text = context_text or ""
    return any(marker in text for marker in (">>>", "```", "For example:", "Example:"))


def _strip_generated_examples(answer_text, question, context_text):
    if _question_asks_example(question):
        return answer_text

    patterns = [
        r"\n+\*\*Пример[^\n]*:\*\*\s*```[\s\S]*?```",
        r"\n+Пример[^\n]*:\s*```[\s\S]*?```",
        r"\n+\*\*Example[^\n]*:\*\*\s*```[\s\S]*?```",
        r"\n+Example[^\n]*:\s*```[\s\S]*?```",
    ]
    cleaned = answer_text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _row_content(row):
    value = row.get("ragu_value_json")
    if not isinstance(value, str):
        return ""

    try:
        payload = json.loads(value)
    except Exception:
        return value

    if isinstance(payload, dict):
        parts = []
        for key in ("title", "name", "content", "text", "description", "summary"):
            item = payload.get(key)
            if item:
                parts.append(str(item))
        return "\n".join(parts)
    return str(payload)


def _score_content(content, question):
    content_l = (content or "").lower()
    tokens = [token for token in _extract_tokens(question) if token not in STOP_WORDS]
    terms = _expand_terms(tokens)
    required = _required_terms(question)
    score = 0

    for term in required:
        if _text_has_term(content_l, term):
            score += 100
            score += _api_name_score(content, term)
        else:
            score -= 200

    for term in terms:
        if len(term) >= 2 and _text_has_term(content_l, term):
            score += 10

    if any(token in {"python", "питон", "пайтон"} for token in _extract_tokens(question)) and "python" in content_l:
        score += 25

    return score


def _fast_context_from_dgraph(question, dgraph_address):
    terms = _search_terms(question)
    if not terms:
        return ""

    required = _required_terms(question)
    storage = DgraphKVStorage(
        address=dgraph_address,
        filename=DEFAULT_FILENAMES["chunks_kv_storage_name"],
    )
    try:
        rows = storage.search_text_rows(terms, limit=50)
    except Exception:
        return ""
    finally:
        storage.close()

    candidates = []
    for row in rows:
        content = _row_content(row).strip()
        if not content:
            continue
        if required and not all(_text_has_term(content, term) for term in required):
            continue
        score = _score_content(content, question)
        candidates.append((score, row, content))

    candidates.sort(key=lambda item: item[0], reverse=True)
    chunks = []
    for _, row, content in candidates[:FAST_CONTEXT_LIMIT]:
        chunks.append(f"CHUNK_ID: {row.get('ragu_key', '')}\n{content}")

    context_text = "\n\n---\n\n".join(chunks).strip()
    return context_text[:FAST_CONTEXT_CHAR_LIMIT]


async def _answer_from_fast_context(question, llm, context_text):
    if not _context_has_required_terms(context_text, question):
        return (
            "В найденном контексте информации недостаточно, чтобы надёжно ответить именно на этот вопрос.",
            context_text,
        )
    answer = await llm.chat_completion(
        conversation=_conversation(question, context_text),
        output_schema=str,
        temperature=0,
    )
    answer_text = _strip_generated_examples(_answer_text(answer), question, context_text)
    return answer_text, context_text


async def answer_with_context(question, search_engine, llm, dgraph_address):
    direct_answer = package_download_answer(question, dgraph_address)
    if direct_answer is not None:
        return direct_answer

    fast_context = _fast_context_from_dgraph(question, dgraph_address)
    if fast_context:
        return await _answer_from_fast_context(question, llm, fast_context)

    context = await search_engine.a_search(question, top_k=SEARCH_TOP_K)
    context_text = search_engine.truncation(str(context)).strip()

    if not _has_context(context) or not context_text or not _context_has_required_terms(context_text, question):
        return (
            "В найденном контексте информации недостаточно, чтобы надёжно ответить именно на этот вопрос.",
            context_text,
        )

    answer = await llm.chat_completion(
        conversation=_conversation(question, context_text),
        output_schema=str,
        temperature=0,
    )
    answer_text = _strip_generated_examples(_answer_text(answer), question, context_text)
    return answer_text, context_text


async def answer_with_timeout(question, search_engine, llm, dgraph_address, timeout):
    return await asyncio.wait_for(
        answer_with_context(question, search_engine, llm, dgraph_address),
        timeout=timeout,
    )
