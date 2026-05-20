import json
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

from bs4 import BeautifulSoup

from xdt.pul import request_get


def sanitize_filename(value):
    value = re.sub(r"[^a-zA-Z0-9а-яА-Я._-]+", "_", str(value))
    value = value.strip("_")
    return value or "document"


def normalize_url(url):
    url = urldefrag(url).url
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(fragment="", query="", path=path).geturl()


def is_same_docs_scope(url, root_url):
    current = urlparse(url)
    root = urlparse(root_url)

    if current.scheme not in {"http", "https"}:
        return False
    if current.netloc != root.netloc:
        return False
    if not current.path.startswith(root.path):
        return False
    if not current.path.endswith(".html") and not current.path.endswith("/"):
        return False
    if "/_sources/" in current.path or "/_static/" in current.path:
        return False
    return True


def fetch_html(url, timeout=30):
    response = request_get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_json(url, timeout=30, headers=None):
    response = request_get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def fetch_text(url, timeout=30, headers=None):
    response = request_get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def _clean_soup(soup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()


def _main_container(soup):
    return (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find("article")
        or soup.find("div", class_=re.compile("body|content|main|article", re.I))
        or soup.body
        or soup
    )


def _node_text(node):
    text = node.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title(soup):
    if soup.title and soup.title.text:
        return soup.title.get_text(" ", strip=True)
    return ""


def _extract_fragment_block(main, fragment):
    target = main.find(id=fragment)
    if not target:
        return "", ""

    if target.name == "dt":
        parts = [target.get_text("\n", strip=True)]
        sibling = target.find_next_sibling()
        if sibling is not None:
            sibling = BeautifulSoup(str(sibling), "html.parser")
            for tag in sibling.find_all(["table"]):
                tag.decompose()
            text = _node_text(sibling)
            if text:
                parts.append(text)
        return fragment, re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()

    section = target.find_parent("section")
    if section is not None:
        return fragment, _node_text(section)

    parent = target.find_parent(["dl", "div", "article"])
    if parent is not None:
        return fragment, _node_text(parent)

    return fragment, _node_text(target)


def extract_page_text(html, fragment=None):
    soup = BeautifulSoup(html, "html.parser")
    _clean_soup(soup)

    title = _extract_title(soup)
    main = _main_container(soup)

    if fragment:
        fragment_title, fragment_text = _extract_fragment_block(main, fragment)
        if fragment_text:
            title = f"{title} - {fragment_title}" if title else fragment_title
            return title.strip(), fragment_text

    return title.strip(), _node_text(main)


def extract_links(html, current_url, root_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        absolute = normalize_url(urljoin(current_url, href))
        if is_same_docs_scope(absolute, root_url):
            links.append(absolute)

    result = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(link)
    return result


def page_slug(url, root_url):
    parsed = urlparse(url)
    root = urlparse(root_url)

    rel = parsed.path.replace(root.path, "", 1).strip("/") or "index"
    if rel.endswith(".html"):
        rel = rel[:-5]
    rel = rel.replace("/", "__")
    if parsed.fragment:
        rel = f"{rel}__{parsed.fragment}"
    return sanitize_filename(rel)


def save_doc(output_dir, slug, url, title, text):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / f"{slug}.txt"
    path.write_text(f"URL: {url}\nTITLE: {title}\n\n{text}", encoding="utf-8")
    return str(path)


def save_manifest(output_dir, manifest):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def crawl_python_docs(root_url, output_dir, max_pages=300, delay_sec=0.15):
    root_url = normalize_url(root_url)
    queue = deque([root_url])
    visited = set()
    saved_files = []
    manifest = []

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue

        try:
            html = fetch_html(url)
        except Exception:
            visited.add(url)
            continue

        visited.add(url)
        title, text = extract_page_text(html)
        if text:
            slug = page_slug(url, root_url)
            saved_path = save_doc(output_dir, slug, url, title, text)
            saved_files.append(saved_path)
            manifest.append({"url": url, "title": title, "slug": slug, "file": saved_path})

        for link in extract_links(html, url, root_url):
            if link not in visited:
                queue.append(link)

        if delay_sec > 0:
            time.sleep(delay_sec)

    return {
        "root_url": root_url,
        "pages_saved": len(saved_files),
        "visited": len(visited),
        "files": saved_files,
        "manifest": save_manifest(output_dir, manifest),
    }


def parse_single_doc_page(url, output_dir):
    parsed = urlparse(url)
    base_url = parsed._replace(fragment="").geturl()
    fragment = parsed.fragment or None

    html = fetch_html(base_url)
    title, text = extract_page_text(html, fragment=fragment)
    slug = page_slug(url, base_url)
    return save_doc(output_dir, slug, url, title, text)
