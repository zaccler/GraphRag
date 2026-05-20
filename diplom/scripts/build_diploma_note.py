from __future__ import annotations

import html
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont


SRC_DOCX = Path(
    "d:/work_in_avia_college/4 \u043a\u0443\u0440\u0441/\u0434\u0438\u043f\u043b\u043e\u043c/"
    "\u0414\u0438\u043f\u043b\u043e\u043c\u043d\u0430\u044f_\u0437\u0430\u043f\u0438\u0441\u043a\u0430_\u041a\u043e\u043c\u0430\u0440\u043e\u0432_"
    "\u0440\u0430\u0441\u0448\u0438\u0440\u0435\u043d\u0438\u0435_\u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430.docx"
)
OUT_DOCX = SRC_DOCX.with_name(
    "\u0414\u0438\u043f\u043b\u043e\u043c\u043d\u0430\u044f_\u0437\u0430\u043f\u0438\u0441\u043a\u0430_\u041a\u043e\u043c\u0430\u0440\u043e\u0432_GraphRAG_Dgraph.docx"
)
ASSET_DIR = Path("generated_docs/diploma_assets")

EMU_PER_INCH = 914400


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def paragraph(text: str, bold: bool = False, center: bool = False, italic: bool = False) -> str:
    jc = '<w:jc w:val="center"/>' if center else '<w:jc w:val="both"/>'
    indent = "" if center else '<w:ind w:firstLine="708"/>'
    b = "<w:b/>" if bold else ""
    i = "<w:i/>" if italic else ""
    return (
        "<w:p>"
        "<w:pPr>"
        '<w:spacing w:line="360" w:lineRule="auto"/>'
        f"{indent}{jc}"
        '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
        f"{b}{i}<w:sz w:val=\"28\"/><w:szCs w:val=\"28\"/></w:rPr>"
        "</w:pPr>"
        "<w:r><w:rPr>"
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
        f"{b}{i}<w:sz w:val=\"28\"/><w:szCs w:val=\"28\"/></w:rPr>"
        f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
        "</w:p>"
    )


def heading(text: str) -> str:
    return paragraph(text, bold=True, center=True)


def caption(text: str) -> str:
    return paragraph(text, center=True)


def page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def table(rows: list[list[str]]) -> str:
    grid = "".join('<w:gridCol w:w="2500"/>' for _ in rows[0])
    body = []
    for row_index, row in enumerate(rows):
        cells = []
        for cell in row:
            cells.append(
                "<w:tc>"
                '<w:tcPr><w:tcW w:w="2500" w:type="dxa"/>'
                '<w:tcBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tcBorders></w:tcPr>'
                f"{paragraph(cell, bold=row_index == 0)}"
                "</w:tc>"
            )
        body.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return (
        "<w:tbl>"
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tblBorders></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{''.join(body)}</w:tbl>"
    )


def image_xml(rid: str, name: str, width_px: int, height_px: int, width_inches: float = 5.8) -> str:
    cx = int(width_inches * EMU_PER_INCH)
    cy = int(cx * height_px / max(width_px, 1))
    return f"""
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="{cx}" cy="{cy}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="{rid[3:]}" name="{esc(name)}"/>
        <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic>
              <pic:nvPicPr><pic:cNvPr id="0" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
              <pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
""".strip()


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["consolab.ttf" if bold else "consola.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def make_code_image(filename: str, title: str, code: str) -> Path:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    font = load_font(18)
    title_font = load_font(20, bold=True)
    lines = code.strip("\n").splitlines()
    width = min(1400, max(900, max(len(line) for line in lines + [title]) * 11 + 80))
    height = 72 + len(lines) * 28 + 36
    image = Image.new("RGB", (width, height), "#0f1720")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=18, fill="#111f2b", outline="#45e0a4", width=2)
    draw.text((40, 32), title, font=title_font, fill="#d7fff0")
    y = 72
    for index, line in enumerate(lines, start=1):
        draw.text((40, y), f"{index:02}", font=font, fill="#5d7b8f")
        draw.text((82, y), line, font=font, fill="#e8f4ff")
        y += 28
    path = ASSET_DIR / filename
    image.save(path)
    return path


def make_architecture_image() -> Path:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSET_DIR / "architecture_graphrag_dgraph.png"
    image = Image.new("RGB", (1300, 760), "#f7fbff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(30, bold=True)
    font = load_font(22, bold=True)
    small = load_font(18)
    draw.text((40, 30), "Архитектура разработанной системы", font=title_font, fill="#183246")
    boxes = [
        ("Browser extension\nChat + MGR", (60, 130, 320, 250), "#5ee6b1"),
        ("FastAPI server\n/auth /ask /parse", (500, 130, 800, 250), "#70d6ff"),
        ("RAGU / GraphRAG\nпоиск контекста", (500, 340, 800, 470), "#ffd166"),
        ("Dgraph\nграф + векторы + KV", (960, 330, 1240, 470), "#b8f2e6"),
        ("XDT parsers\npackages + docs + URL", (60, 470, 360, 620), "#ffb3c1"),
        ("Google Sheets\nchat logs", (940, 120, 1240, 230), "#cdb4db"),
    ]
    for text, box, color in boxes:
        draw.rounded_rectangle(box, radius=22, fill=color, outline="#183246", width=3)
        draw.multiline_text((box[0] + 24, box[1] + 30), text, font=font, fill="#183246", spacing=8)
    arrows = [
        ((320, 190), (500, 190), "HTTP"),
        ((650, 250), (650, 340), "query"),
        ((800, 405), (960, 405), "storage"),
        ((360, 545), (500, 410), "raw data"),
        ((800, 185), (940, 175), "logs"),
    ]
    for start, end, label in arrows:
        draw.line((start, end), fill="#183246", width=4)
        draw.polygon([(end[0], end[1]), (end[0] - 14, end[1] - 8), (end[0] - 14, end[1] + 8)], fill="#183246")
        draw.text(((start[0] + end[0]) // 2 - 20, (start[1] + end[1]) // 2 - 26), label, font=small, fill="#183246")
    image.save(path)
    return path


def build_added_content(image_refs: dict[str, tuple[str, int, int]]) -> str:
    blocks: list[str] = [page_break()]
    blocks.append(heading("4 Расширенное описание реализованной системы"))
    for text in [
        "Разработанная система представляет собой программный комплекс для интеллектуального поиска информации по базе знаний с использованием подхода GraphRAG, графовой СУБД Dgraph и пользовательского интерфейса в виде расширения для браузера. В отличие от обычного чат-бота, система не должна отвечать только за счет внутренних знаний языковой модели. Перед формированием ответа она извлекает релевантный контекст из загруженных документов, сведений о пакетах и данных, сохраненных в графовой базе.",
        "В процессе разработки исходная схема была адаптирована под практические ограничения дипломного проекта. Вместо Telegram-бота был реализован браузерный интерфейс, так как он удобнее для демонстрации, не требует внешнего мессенджера и позволяет объединить пользовательский чат с административной панелью. При этом назначение блока bot из схемы сохранено: пользователь получает диалоговый интерфейс для обращения к GraphRAG.",
        "Серверная часть объединяет несколько контуров: контур авторизации, контур обработки вопросов, контур сбора данных, контур индексации и контур логирования. Такое решение выполнено в виде монолитного FastAPI-приложения. Для дипломного проекта это упрощает запуск и сопровождение, но при дальнейшем развитии система может быть разделена на самостоятельные сервисы.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId23", "architecture_graphrag_dgraph.png", *image_refs["architecture"]))
    blocks.append(caption("Рисунок 4.1 - Архитектура разработанной системы GraphRAG и Dgraph"))

    blocks.append(heading("4.1 Сравнение с конкурентными решениями"))
    for text in [
        "На рынке уже существуют системы, решающие близкие задачи интеллектуального поиска по корпоративным данным. К таким решениям относятся Notion AI Enterprise Search, Glean, Elastic AI Assistant, Microsoft Copilot и ChatGPT Enterprise. Данные продукты позволяют искать сведения в рабочих пространствах, документах, репозиториях и подключенных сервисах, однако обычно требуют платной подписки, облачной инфраструктуры и не всегда дают возможность контролировать внутреннюю структуру индекса.",
        "Разрабатываемая система ориентирована на учебный и прикладной сценарий, где важно показать полный цикл работы: получение данных из источников, построение графа знаний, хранение в Dgraph, генерацию ответа и административное управление обновлением. Поэтому главным отличием проекта является не только наличие чат-интерфейса, но и возможность управлять источниками данных, повторно индексировать базу и просматривать состояние обработки.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(table([
        ["Решение", "Назначение", "Ограничения", "Отличие разработанной системы"],
        ["Notion AI Enterprise Search", "Поиск по рабочему пространству Notion и подключенным источникам", "Зависимость от облачной платформы и коммерческой подписки", "Локальная серверная часть, собственная база Dgraph и управляемые источники"],
        ["Glean", "Корпоративный поиск и ассистент по внутренним знаниям организации", "Ориентация на enterprise-инфраструктуру и внешние интеграции", "Проект можно развернуть локально и адаптировать под учебную инфраструктуру"],
        ["Elastic AI Assistant", "Поиск, аналитика и ответы на основе данных Elastic", "Требует настройки Elastic Stack и ориентирован на другой стек хранения", "Используется графовая модель Dgraph и GraphRAG-подход"],
        ["Microsoft Copilot", "Помощник по данным Microsoft 365", "Сильно связан с экосистемой Microsoft", "Система не привязана к одному офисному пакету и может парсить разные источники"],
        ["Разработанная система", "GraphRAG-поиск по документации, пакетам и внутренним данным", "Часть компонентов реализована в упрощенном виде", "Открытая архитектура, Dgraph, расширение браузера, MGR и Google Sheets-логирование"],
    ]))
    blocks.append(caption("Таблица 4.1 - Сравнение разработанной системы с аналогами"))
    blocks.append(paragraph("Место для вставки рисунка 4.2 - скриншот интерфейса Notion AI Enterprise Search.", italic=True))
    blocks.append(paragraph("Место для вставки рисунка 4.3 - скриншот интерфейса Glean или Elastic AI Assistant.", italic=True))

    blocks.append(heading("4.2 Реализация авторизации по email-коду"))
    for text in [
        "В расширении предусмотрено два режима входа. Первый режим предназначен для администратора и использует постоянный код из локального файла access_codes.json. Такой подход оставлен для быстрой отладки MGR-панели. Второй режим предназначен для обычного пользователя и использует одноразовый код, отправляемый на электронную почту.",
        "При запросе кода пользователь вводит email в расширении. Расширение отправляет запрос на серверный маршрут /auth/request-code. Backend проверяет корректность адреса, генерирует случайный числовой код и отправляет письмо через SMTP. Код хранится только в оперативной памяти сервера и имеет ограниченный срок действия. После успешной проверки через /auth/verify-code запись удаляется, поэтому при повторном выходе из аккаунта требуется новый код.",
        "Такой механизм является более безопасным, чем постоянный пользовательский пароль в расширении. Пользователь не хранит секрет в браузере, а сессия сохраняется только в chrome.storage.session. Это означает, что при закрытии браузера состояние входа сбрасывается, но закрытие popup не приводит к потере уже отправленного кода.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId24", "code_auth_endpoints.png", *image_refs["auth"]))
    blocks.append(caption("Рисунок 4.4 - Фрагмент реализации маршрутов email-авторизации"))

    blocks.append(heading("4.3 Реализация браузерного расширения"))
    for text in [
        "Пользовательский интерфейс реализован как расширение браузера на Manifest V3. Оно состоит из popup.html, styles.css, popup.js и access_codes.json. Расширение не выполняет тяжелую обработку данных самостоятельно. Его задача заключается в отправке HTTP-запросов к FastAPI-серверу, отображении ответов и предоставлении администратору элементов управления.",
        "В режиме пользователя отображается только чат. Пользователь вводит вопрос, расширение отправляет его на маршрут /ask и отображает ответ. Ссылки в ответах автоматически распознаются и становятся кликабельными. История диалога сохраняется локально в браузере отдельно для каждого email, поэтому разные пользователи на одном компьютере не смешивают переписку.",
        "В режиме администратора доступна вкладка MGR. В ней размещены кнопки проверки статуса, перестроения базы знаний, отладочного запроса, парсинга пакетов из файла, загрузки документации из реестра и парсинга одиночной страницы по URL. Для удобства у кнопок есть визуальные состояния Start, Started, OK и Error.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId25", "code_extension_login.png", *image_refs["extension"]))
    blocks.append(caption("Рисунок 4.5 - Фрагмент логики входа и сохранения пользовательской истории в расширении"))
    blocks.append(paragraph("Место для вставки рисунка 4.6 - скриншот окна расширения в режиме пользователя.", italic=True))
    blocks.append(paragraph("Место для вставки рисунка 4.7 - скриншот вкладки MGR в режиме администратора.", italic=True))

    blocks.append(heading("4.4 Интеграция с Google Sheets"))
    for text in [
        "В соответствии с исходной схемой проекта был предусмотрен блок dashboard Google Sheet. В итоговой реализации Google Sheets используется не как основное хранилище базы знаний, а как журнал пользовательских обращений. Это соответствует более безопасной логике: база знаний хранится в Dgraph, а таблица применяется для контроля запросов и ответов.",
        "После получения ответа расширение отправляет на backend адрес пользователя, вопрос и ответ. Сервер сохраняет запись локально в файл dhb/data/chat_logs.jsonl и при наличии переменной GOOGLE_SHEETS_LOG_WEBHOOK_URL отправляет те же данные в Google Apps Script webhook. Сам пользователь не получает прав на редактирование таблицы. Таблица может быть открыта только на просмотр, а запись выполняется скриптом от имени владельца.",
        "Данный подход удобен для демонстрации и сопровождения. Руководитель или администратор может открыть Google Sheets и увидеть историю обращений без прямого доступа к серверным логам. При этом отсутствие настроенного webhook не останавливает работу системы, потому что локальный JSONL-журнал остается резервным вариантом.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId26", "code_google_sheets_log.png", *image_refs["sheets"]))
    blocks.append(caption("Рисунок 4.8 - Фрагмент логирования вопросов и ответов в Google Sheets"))
    blocks.append(paragraph("Место для вставки рисунка 4.9 - скриншот таблицы Google Sheets с колонками timestamp, email, question, answer.", italic=True))

    blocks.append(heading("4.5 Парсинг документации и установочных пакетов"))
    for text in [
        "Отдельной частью проекта является модуль XDT, отвечающий за получение внешних данных. В нем реализованы два основных сценария: парсинг документации и парсинг сведений об установочных пакетах. Документация может загружаться по одиночному URL, из реестра источников или через обход разделов Python-документации. Пакеты загружаются из текстового списка packages.txt.",
        "Список пакетов содержит источники разных типов: NuGet, PyPI, npm, Maven, Docker, Go modules, crates.io и GitHub releases. Для каждого источника парсер получает сведения о версиях, ссылках на загрузку и командах установки. После парсинга данные сохраняются в текстовом виде и индексируются через GraphRAG. Если источник уже был обработан и новых данных нет, повторная индексация может быть пропущена.",
        "Для запросов вида «дай ссылку на пакет определенной версии» добавлена детерминированная проверка по данным Dgraph. Это позволяет возвращать прямую ссылку на скачивание .nupkg, tarball или другой установочный артефакт, если она присутствует в базе. Такой механизм дополняет GraphRAG и повышает точность ответов для точных package-запросов.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId27", "code_package_parser.png", *image_refs["parser"]))
    blocks.append(caption("Рисунок 4.10 - Фрагмент обработки источников установочных пакетов"))

    blocks.append(heading("4.6 Хранение данных в Dgraph"))
    for text in [
        "Dgraph используется как основное итоговое хранилище данных, с которыми работает LLM-контур. В базе сохраняются не только сущности и отношения графа, но также runtime-данные GraphRAG: chunks, community summaries, vector rows и key-value записи. Это было сделано для устранения рассинхронизации между локальными JSON-файлами и Dgraph.",
        "В процессе разработки была выявлена проблема, при которой namespace runtime-хранилища зависел от полного пути staging-каталога. Из-за этого данные физически существовали в Dgraph, но поисковый движок не находил их при обычном запросе. Ошибка была исправлена нормализацией namespace до имени файла, например vdb_chunk.json или kv_chunks.json.",
        "Для предотвращения ошибок gRPC при больших объемах данных была увеличена допустимая длина сообщений и добавлена постраничная выборка векторных строк. Это позволило избежать ситуации, когда Dgraph возвращал слишком большой ответ при поиске по embedding-таблице.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(image_xml("rId28", "code_dgraph_storage.png", *image_refs["dgraph"]))
    blocks.append(caption("Рисунок 4.11 - Фрагмент унифицированного хранилища Dgraph"))
    blocks.append(paragraph("Место для вставки рисунка 4.12 - скриншот Dgraph Ratel с узлами и связями графа знаний.", italic=True))

    blocks.append(heading("4.7 Тестирование разработанного решения"))
    for text in [
        "Тестирование проводилось по нескольким направлениям: проверка запуска backend-сервера, проверка подключения Dgraph, проверка построения индекса, проверка пользовательских запросов, проверка MGR-команд и проверка email-авторизации. Для каждого сценария фиксировались типичные ошибки и способы их устранения.",
        "При тестировании внешних LLM-провайдеров были выявлены ошибки rate limit, timeout и service tier capacity exceeded. Для повышения устойчивости добавлены retry/backoff, ограничение параллельных запросов и увеличенные таймауты. Это особенно важно при больших rebuild-процессах, когда система выполняет много последовательных обращений к модели.",
        "Отдельно проверялись запросы по пакетам. Например, пользователь мог спросить ссылку на Newtonsoft.Json версии 13.0.3. При наличии данных в Dgraph система должна вернуть прямую ссылку на установочный файл и команду установки. Если информации нет в найденном контексте, система сообщает о недостаточности данных, а не выдумывает ответ.",
        "Пользовательское расширение проверялось на корректность отображения длинных ссылок, сохранение истории, работу скроллов, переключение ролей и отображение состояния кнопок. Для администратора проверялись кнопки Status, Rebuild KB, Ask Debug, Parse file и Parse URL.",
    ]:
        blocks.append(paragraph(text))
    blocks.append(table([
        ["Проверяемый сценарий", "Ожидаемый результат", "Фактический результат"],
        ["Запуск FastAPI при недоступном Dgraph", "Сервер не должен аварийно завершаться", "Добавлена обработка ошибки подключения"],
        ["Парсинг пакетов из packages.txt", "Новые источники добавляются, существующие пропускаются", "Реализована проверка skipped/already exists"],
        ["Запрос ссылки на пакет", "Возвращается конкретный URL загрузки", "Добавлен детерминированный поиск package/version"],
        ["Закрытие popup после отправки email-кода", "Состояние ввода кода сохраняется", "Используется chrome.storage.session"],
        ["Запись истории в Google Sheets", "Строка появляется в таблице", "Реализован webhook через Apps Script"],
    ]))
    blocks.append(caption("Таблица 4.2 - Результаты функционального тестирования"))

    blocks.append(heading("Заключение"))
    for text in [
        "В ходе выполнения дипломного проекта была разработана система интеллектуального доступа к данным на основе GraphRAG, Dgraph и расширения для браузера. Реализован серверный API, механизм построения графа знаний, парсинг документации и установочных пакетов, пользовательский чат, административная панель MGR, email-авторизация и логирование пользовательских обращений.",
        "Практическая значимость проекта заключается в возможности объединить разрозненные сведения о документации, пакетах и программных ресурсах в единую базу знаний. Пользователь получает простой интерфейс для вопроса на естественном языке, а администратор получает инструменты обновления данных и контроля состояния системы.",
        "Разработанное решение не полностью повторяет исходную схему в части отдельных микросервисов observability, resource pool и account automation. Эти блоки были реализованы частично или оставлены как направления дальнейшего развития. При этом основная функциональность схемы выполнена: сбор данных, хранение в Dgraph, GraphRAG-поиск, пользовательский интерфейс, MGR и интеграция с Google Sheets.",
        "В дальнейшем систему можно развивать за счет добавления полноценного планировщика обновлений, расширенной observability-подсистемы, защиты Google Sheets webhook секретным токеном, поддержки дополнительных package registry и выделения XDT-компонентов в отдельный сервис.",
    ]:
        blocks.append(paragraph(text))
    return "".join(blocks)


def main() -> None:
    if not SRC_DOCX.exists():
        raise FileNotFoundError(SRC_DOCX)

    arch = make_architecture_image()
    auth = make_code_image(
        "code_auth_endpoints.png",
        "server.py: email authorization",
        """
@app.post("/auth/request-code")
async def auth_request_code(request: AuthCodeRequest):
    email = normalize_email(request.email)
    code = generate_auth_code()
    await asyncio.to_thread(send_auth_code_email, email, code)
    store_auth_code(email, code)
    return {"status": "sent", "email": email}

@app.post("/auth/verify-code")
async def auth_verify_code(request: AuthVerifyRequest):
    if not verify_auth_code(email, request.code):
        raise HTTPException(status_code=401)
    return {"status": "verified", "role": "user"}
""",
    )
    extension = make_code_image(
        "code_extension_login.png",
        "popup.js: user session and history",
        """
const sessionData = await chrome.storage.session.get(["role", "userEmail"]);
role = sessionData.role || "";
userEmail = sessionData.userEmail || "";

function currentHistoryKey() {
  if (role === "admin") return "__admin__";
  return userEmail || "__guest__";
}

await chrome.storage.session.set({ role, userEmail });
await chrome.storage.local.set({ chatLogsByUser });
""",
    )
    sheets = make_code_image(
        "code_google_sheets_log.png",
        "server.py: Google Sheets logging",
        """
@app.post("/dhb/log-chat")
async def dhb_log_chat(request: ChatLogRequest):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email": normalize_email(request.email),
        "question": request.question,
        "answer": request.answer,
    }
    await asyncio.to_thread(append_local_chat_log, payload)
    return await append_google_sheet_chat_log(payload)
""",
    )
    parser = make_code_image(
        "code_package_parser.png",
        "xdt parser: package records",
        """
def parse_package_sources(package_list_path, output_dir, max_sources=None, force=False):
    sources = read_package_sources(package_list_path)
    for source in sources[:max_sources]:
        if source_exists(source) and not force:
            skipped.append({"code": source.code, "reason": "already exists"})
            continue
        text = fetch_package_metadata(source)
        save_package_record(output_dir, source, text)
    return {"count": count, "skipped": skipped, "errors": errors}
""",
    )
    dgraph = make_code_image(
        "code_dgraph_storage.png",
        "Dgraph unified vector storage",
        """
GRPC_MAX_MESSAGE_BYTES = 128 * 1024 * 1024
VECTOR_QUERY_PAGE_SIZE = 100

def _namespace_name(filename: str) -> str:
    return Path(str(filename)).name

def query(self, query_embedding, top_k=5):
    for row in self._iter_rows(page_size=VECTOR_QUERY_PAGE_SIZE):
        score = cosine_similarity(query_embedding, row["embedding"])
        heap.push((score, row))
""",
    )

    image_refs = {}
    for key, path in {
        "architecture": arch,
        "auth": auth,
        "extension": extension,
        "sheets": sheets,
        "parser": parser,
        "dgraph": dgraph,
    }.items():
        with Image.open(path) as img:
            image_refs[key] = img.size

    additions = build_added_content(image_refs)

    with ZipFile(SRC_DOCX, "r") as src:
        document_xml = src.read("word/document.xml").decode("utf-8")
        rels_xml = src.read("word/_rels/document.xml.rels").decode("utf-8")

        if "xmlns:pic=" not in document_xml[:3000]:
            document_xml = document_xml.replace(
                "<w:document ",
                '<w:document xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" ',
                1,
            )
        if "xmlns:a=" not in document_xml[:3000]:
            document_xml = document_xml.replace(
                "<w:document ",
                '<w:document xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
                1,
            )

        insert_at = document_xml.rfind("<w:sectPr")
        if insert_at == -1:
            insert_at = document_xml.rfind("</w:body>")
        document_xml = document_xml[:insert_at] + additions + document_xml[insert_at:]

        new_rels = [
            ("rId23", "architecture_graphrag_dgraph.png"),
            ("rId24", "code_auth_endpoints.png"),
            ("rId25", "code_extension_login.png"),
            ("rId26", "code_google_sheets_log.png"),
            ("rId27", "code_package_parser.png"),
            ("rId28", "code_dgraph_storage.png"),
        ]
        rel_items = "".join(
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
            for rid, name in new_rels
        )
        rels_xml = rels_xml.replace("</Relationships>", rel_items + "</Relationships>")

        tmp = OUT_DOCX.with_suffix(".tmp.docx")
        with ZipFile(tmp, "w", ZIP_DEFLATED) as out:
            for item in src.infolist():
                if item.filename in {"word/document.xml", "word/_rels/document.xml.rels"}:
                    continue
                out.writestr(item, src.read(item.filename))
            out.writestr("word/document.xml", document_xml.encode("utf-8"))
            out.writestr("word/_rels/document.xml.rels", rels_xml.encode("utf-8"))
            for rid, filename in new_rels:
                out.writestr(f"word/media/{filename}", (ASSET_DIR / filename).read_bytes())

    shutil.move(str(tmp), str(OUT_DOCX))
    print(OUT_DOCX)


if __name__ == "__main__":
    main()
