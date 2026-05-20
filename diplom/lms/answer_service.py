import asyncio
import json

from knb.package_downloads import package_download_answer


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
        "5. Если в контексте ответа нет, прямо скажи, что в найденном контексте информации недостаточно.\n"
        "6. Отвечай по-русски, но имена API, сигнатуры и код не переводи."
    )
    user_prompt = (
        f"Вопрос:\n{question}\n\n"
        f"Контекст:\n{context_text}\n\n"
        "Сформируй краткий ответ строго по контексту. Если в контексте есть пример кода, приведи именно его."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def answer_with_context(question, search_engine, llm, dgraph_address):
    direct_answer = package_download_answer(question, dgraph_address)
    if direct_answer is not None:
        return direct_answer

    context = await search_engine.a_search(question)
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
