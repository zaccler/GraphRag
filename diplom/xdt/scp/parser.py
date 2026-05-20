from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote, urlparse

from xdt.pul import get_auth_headers, request_get
from xdt.scp.web_docs import (
    crawl_python_docs,
    fetch_json,
    fetch_text,
    parse_single_doc_page,
    sanitize_filename,
    save_doc,
)


PACKAGE_MAX_VERSIONS_DEFAULT = int(os.getenv("PACKAGE_MAX_VERSIONS", "30"))
GITHUB_MAX_RELEASES_DEFAULT = int(os.getenv("GITHUB_MAX_RELEASES", "10"))


def google_sheet_csv_url(item: Dict) -> str:
    if item.get("csv_url"):
        return str(item["csv_url"])
    if item.get("url") and "output=csv" in str(item["url"]):
        return str(item["url"])

    sheet_id = item.get("sheet_id")
    if not sheet_id and item.get("url"):
        match = re.search(r"/spreadsheets/d/([^/]+)", str(item["url"]))
        if match:
            sheet_id = match.group(1)

    if not sheet_id:
        raise ValueError("google_sheet source must define csv_url, sheet_id, or Google Sheets url")

    gid = item.get("gid", "0")
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def format_google_sheet_text(title: str, source_url: str, csv_text: str, max_rows: int = 1000) -> str:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if max_rows:
        rows = rows[:max_rows]

    lines = [
        "SOURCE_TYPE: google_sheet",
        f"TITLE: {title}",
        f"SOURCE_URL: {source_url}",
        "",
        "Google Sheet rows converted to text records.",
    ]

    for index, row in enumerate(rows, start=1):
        lines.extend(["", f"ROW: {index}"])
        for key, value in row.items():
            column = (key or "column").strip()
            cell = (value or "").strip()
            if cell:
                lines.append(f"{column}: {cell}")

    return "\n".join(lines).strip()


def parse_google_sheet(item: Dict, output_dir: str) -> str:
    csv_url = google_sheet_csv_url(item)
    title = str(item.get("title") or item.get("code") or "Google Sheet")
    max_rows = int(item.get("max_rows", 1000))

    response = request_get(csv_url)
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError(f"Google Sheet returned empty CSV: {csv_url}")

    text = format_google_sheet_text(title, csv_url, response.text, max_rows=max_rows)
    slug = sanitize_filename(item.get("code") or title)
    return save_doc(output_dir, slug, csv_url, title, text)


def github_repo_from_url(url: str) -> Tuple[str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.netloc != "github.com" or len(parts) < 2:
        raise ValueError(f"Unsupported GitHub repository URL: {url}")
    return parts[0], parts[1]


def github_auth_headers() -> Dict[str, str]:
    return get_auth_headers("github")


def format_github_release_text(repo: str, releases: List[Dict], source_url: str) -> str:
    lines = [
        "SOURCE_TYPE: github_releases",
        f"REPOSITORY: {repo}",
        f"SOURCE_URL: {source_url}",
        "",
        "GitHub releases with installer and package asset links.",
    ]

    for release in releases:
        tag = release.get("tag_name") or release.get("name") or ""
        name = release.get("name") or tag
        lines.extend(
            [
                "",
                f"RELEASE: {name}",
                f"TAG: {tag}",
                f"VERSION: {tag}",
                f"PRERELEASE: {release.get('prerelease', False)}",
                f"PUBLISHED_AT: {release.get('published_at') or ''}",
                f"HTML_URL: {release.get('html_url') or ''}",
                f"SOURCE_ZIP_URL: {release.get('zipball_url') or ''}",
                f"SOURCE_TARBALL_URL: {release.get('tarball_url') or ''}",
            ]
        )

        body = (release.get("body") or "").strip()
        if body:
            lines.extend(["RELEASE_NOTES:", body])

        assets = release.get("assets") or []
        if assets:
            lines.append("ASSETS:")
        for asset in assets:
            lines.extend(
                [
                    f"- ASSET_NAME: {asset.get('name') or ''}",
                    f"  DOWNLOAD_URL: {asset.get('browser_download_url') or ''}",
                    f"  CONTENT_TYPE: {asset.get('content_type') or ''}",
                    f"  SIZE_BYTES: {asset.get('size') or 0}",
                ]
            )

    return "\n".join(lines).strip()


def parse_github_releases(item: Dict, output_dir: str) -> str:
    if item.get("owner") and item.get("repo"):
        owner = item["owner"]
        repo_name = item["repo"]
        repo_url = item.get("url") or f"https://github.com/{owner}/{repo_name}"
    else:
        repo_url = item["url"]
        owner, repo_name = github_repo_from_url(repo_url)

    max_releases = int(item.get("max_releases", GITHUB_MAX_RELEASES_DEFAULT))
    include_prerelease = bool(item.get("include_prerelease", True))
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases"
    releases = fetch_json(api_url, headers=github_auth_headers())
    if not include_prerelease:
        releases = [release for release in releases if not release.get("prerelease")]
    releases = releases[:max_releases]

    repo = f"{owner}/{repo_name}"
    text = format_github_release_text(repo, releases, repo_url)
    slug = sanitize_filename(item.get("code") or f"github_{owner}_{repo_name}_releases")
    return save_doc(output_dir, slug, repo_url, f"GitHub releases: {repo}", text)


def format_nuget_package_text(package_id: str, versions: List[str], source_url: str) -> str:
    package_lower = package_id.lower()
    lines = [
        "SOURCE_TYPE: nuget_package",
        f"PACKAGE_MANAGER: NuGet",
        f"PACKAGE_ID: {package_id}",
        f"SOURCE_URL: {source_url}",
        "",
        "NuGet package versions with direct .nupkg installer/package download links.",
    ]

    for version in versions:
        version_lower = version.lower()
        download_url = (
            f"https://api.nuget.org/v3-flatcontainer/{package_lower}/"
            f"{version_lower}/{package_lower}.{version_lower}.nupkg"
        )
        nuspec_url = (
            f"https://api.nuget.org/v3-flatcontainer/{package_lower}/"
            f"{version_lower}/{package_lower}.nuspec"
        )
        lines.extend(
            [
                "",
                f"PACKAGE: {package_id}",
                f"VERSION: {version}",
                f"INSTALLER_TYPE: nupkg",
                f"DOWNLOAD_URL: {download_url}",
                f"NUSPEC_URL: {nuspec_url}",
                f"INSTALL_COMMAND: dotnet add package {package_id} --version {version}",
            ]
        )

    return sentence_safe_record_text("\n".join(lines).strip())


def parse_nuget_package(item: Dict, output_dir: str) -> str:
    package_id = item.get("package_id") or item.get("id") or item.get("code")
    if not package_id:
        raise ValueError("nuget_package source must define package_id or code")

    package_lower = str(package_id).lower()
    source_url = item.get("url") or f"https://www.nuget.org/packages/{package_id}"
    index_url = f"https://api.nuget.org/v3-flatcontainer/{package_lower}/index.json"
    payload = fetch_json(index_url)
    versions = payload.get("versions") or []
    if item.get("versions"):
        requested = {str(version).lower() for version in item["versions"]}
        versions = [version for version in versions if str(version).lower() in requested]
    else:
        max_versions = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
        versions = versions[-max_versions:]

    text = format_nuget_package_text(str(package_id), versions, source_url)
    slug = sanitize_filename(item.get("code") or f"nuget_{package_id}")
    return save_doc(output_dir, slug, source_url, f"NuGet package: {package_id}", text)


def format_pypi_package_text(package_id: str, payload: Dict, max_versions: int) -> str:
    info = payload.get("info") or {}
    releases = payload.get("releases") or {}
    versions = list(releases.keys())[-max_versions:]
    source_url = info.get("package_url") or f"https://pypi.org/project/{package_id}/"

    lines = [
        "SOURCE_TYPE: pypi_package",
        "PACKAGE_MANAGER: PyPI",
        f"PACKAGE_ID: {package_id}",
        f"SOURCE_URL: {source_url}",
        f"SUMMARY: {info.get('summary') or ''}",
        f"HOMEPAGE: {info.get('home_page') or ''}",
        f"PROJECT_URLS: {_json_for_text(info.get('project_urls') or {})}",
        "",
        "PyPI package versions with distribution file download links.",
    ]

    for version in versions:
        files = releases.get(version) or []
        lines.extend(
            [
                "",
                f"PACKAGE: {package_id}",
                f"VERSION: {version}",
                f"INSTALL_COMMAND: pip install {package_id}=={version}",
            ]
        )
        if files:
            lines.append("FILES:")
        for file_info in files:
            lines.extend(
                [
                    f"- FILENAME: {file_info.get('filename') or ''}",
                    f"  PACKAGE_TYPE: {file_info.get('packagetype') or ''}",
                    f"  DOWNLOAD_URL: {file_info.get('url') or ''}",
                    f"  PYTHON_VERSION: {file_info.get('python_version') or ''}",
                    f"  SIZE_BYTES: {file_info.get('size') or 0}",
                ]
            )
    return sentence_safe_record_text("\n".join(lines).strip())


def parse_pypi_package(item: Dict, output_dir: str) -> str:
    package_id = item.get("package_id") or item.get("id") or item.get("code")
    if not package_id:
        raise ValueError("pypi_package source must define package_id or code")

    api_url = f"https://pypi.org/pypi/{package_id}/json"
    payload = fetch_json(api_url)
    max_versions = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    text = format_pypi_package_text(str(package_id), payload, max_versions)
    slug = sanitize_filename(item.get("code") or f"pypi_{package_id}")
    source_url = (payload.get("info") or {}).get("package_url") or f"https://pypi.org/project/{package_id}/"
    return save_doc(output_dir, slug, source_url, f"PyPI package: {package_id}", text)


def format_npm_package_text(package_id: str, payload: Dict, max_versions: int) -> str:
    versions_map = payload.get("versions") or {}
    versions = list(versions_map.keys())[-max_versions:]
    dist_tags = payload.get("dist-tags") or {}
    source_url = f"https://www.npmjs.com/package/{package_id}"

    lines = [
        "SOURCE_TYPE: npm_package",
        "PACKAGE_MANAGER: npm",
        f"PACKAGE_ID: {package_id}",
        f"SOURCE_URL: {source_url}",
        f"DIST_TAGS: {_json_for_text(dist_tags)}",
        f"DESCRIPTION: {payload.get('description') or ''}",
        "",
        "npm package versions with tarball download links.",
    ]

    for version in versions:
        data = versions_map.get(version) or {}
        dist = data.get("dist") or {}
        lines.extend(
            [
                "",
                f"PACKAGE: {package_id}",
                f"VERSION: {version}",
                f"INSTALLER_TYPE: tgz",
                f"DOWNLOAD_URL: {dist.get('tarball') or ''}",
                f"INTEGRITY: {dist.get('integrity') or ''}",
                f"INSTALL_COMMAND: npm install {package_id}@{version}",
            ]
        )
    return sentence_safe_record_text("\n".join(lines).strip())


def parse_npm_package(item: Dict, output_dir: str) -> str:
    package_id = item.get("package_id") or item.get("id") or item.get("code")
    if not package_id:
        raise ValueError("npm_package source must define package_id or code")

    api_id = str(package_id).replace("/", "%2f")
    payload = fetch_json(f"https://registry.npmjs.org/{api_id}")
    max_versions = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    text = format_npm_package_text(str(package_id), payload, max_versions)
    slug = sanitize_filename(item.get("code") or f"npm_{package_id}")
    return save_doc(output_dir, slug, f"https://www.npmjs.com/package/{package_id}", f"npm package: {package_id}", text)


def parse_maven_coord(value: str) -> Tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("maven source must use group_id:artifact_id format")
    return parts[0], parts[1]


def format_maven_package_text(group_id: str, artifact_id: str, docs: List[Dict]) -> str:
    source_url = f"https://search.maven.org/artifact/{group_id}/{artifact_id}"
    group_path = group_id.replace(".", "/")
    lines = [
        "SOURCE_TYPE: maven_package",
        "PACKAGE_MANAGER: Maven",
        f"GROUP_ID: {group_id}",
        f"ARTIFACT_ID: {artifact_id}",
        f"SOURCE_URL: {source_url}",
        "",
        "Maven package versions with jar, pom and Gradle/Maven install snippets.",
    ]

    for doc in docs:
        version = doc.get("v") or doc.get("latestVersion") or ""
        if not version:
            continue
        base_url = f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/{version}"
        lines.extend(
            [
                "",
                f"PACKAGE: {group_id}:{artifact_id}",
                f"VERSION: {version}",
                f"JAR_URL: {base_url}/{artifact_id}-{version}.jar",
                f"POM_URL: {base_url}/{artifact_id}-{version}.pom",
                f"MAVEN_DEPENDENCY: <dependency><groupId>{group_id}</groupId><artifactId>{artifact_id}</artifactId><version>{version}</version></dependency>",
                f"GRADLE_DEPENDENCY: implementation '{group_id}:{artifact_id}:{version}'",
            ]
        )

    return sentence_safe_record_text("\n".join(lines).strip())


def parse_maven_package(item: Dict, output_dir: str) -> str:
    coord = item.get("coord") or item.get("package_id") or item.get("id") or item.get("code")
    if not coord:
        raise ValueError("maven_package source must define coord in group_id:artifact_id format")
    group_id, artifact_id = parse_maven_coord(str(coord))
    rows = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    api_url = (
        "https://search.maven.org/solrsearch/select"
        f"?q=g:%22{quote(group_id)}%22+AND+a:%22{quote(artifact_id)}%22&core=gav&rows={rows}&wt=json"
    )
    payload = fetch_json(api_url)
    docs = ((payload.get("response") or {}).get("docs") or [])[:rows]
    text = format_maven_package_text(group_id, artifact_id, docs)
    slug = sanitize_filename(item.get("code") or f"maven_{group_id}_{artifact_id}")
    return save_doc(output_dir, slug, api_url, f"Maven package: {group_id}:{artifact_id}", text)


def format_crates_package_text(crate_id: str, payload: Dict, max_versions: int) -> str:
    crate = payload.get("crate") or {}
    versions = (payload.get("versions") or [])[:max_versions]
    source_url = f"https://crates.io/crates/{crate_id}"
    lines = [
        "SOURCE_TYPE: crates_package",
        "PACKAGE_MANAGER: Cargo",
        f"PACKAGE_ID: {crate_id}",
        f"SOURCE_URL: {source_url}",
        f"DESCRIPTION: {crate.get('description') or ''}",
        f"HOMEPAGE: {crate.get('homepage') or ''}",
        f"REPOSITORY: {crate.get('repository') or ''}",
        "",
        "Rust crate versions with crate download links.",
    ]

    for version_info in versions:
        version = version_info.get("num") or ""
        if not version:
            continue
        lines.extend(
            [
                "",
                f"PACKAGE: {crate_id}",
                f"VERSION: {version}",
                f"DOWNLOAD_URL: https://crates.io/api/v1/crates/{crate_id}/{version}/download",
                f"INSTALL_COMMAND: cargo add {crate_id}@{version}",
                f"YANKED: {version_info.get('yanked', False)}",
            ]
        )

    return sentence_safe_record_text("\n".join(lines).strip())


def parse_crates_package(item: Dict, output_dir: str) -> str:
    crate_id = item.get("package_id") or item.get("id") or item.get("code")
    if not crate_id:
        raise ValueError("crates_package source must define package_id or code")
    payload = fetch_json(f"https://crates.io/api/v1/crates/{crate_id}")
    max_versions = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    text = format_crates_package_text(str(crate_id), payload, max_versions)
    slug = sanitize_filename(item.get("code") or f"crates_{crate_id}")
    return save_doc(output_dir, slug, f"https://crates.io/crates/{crate_id}", f"Cargo crate: {crate_id}", text)


def docker_repo_parts(value: str) -> Tuple[str, str, str]:
    image = value.strip()
    if "/" in image:
        namespace, name = image.split("/", 1)
        display_name = image
    else:
        namespace, name = "library", image
        display_name = image
    return namespace, name, display_name


def format_docker_image_text(display_name: str, payload: Dict, max_tags: int) -> str:
    tags = (payload.get("results") or [])[:max_tags]
    source_url = f"https://hub.docker.com/r/{display_name}" if "/" in display_name else f"https://hub.docker.com/_/{display_name}"
    lines = [
        "SOURCE_TYPE: docker_image",
        "PACKAGE_MANAGER: Docker Hub",
        f"IMAGE: {display_name}",
        f"SOURCE_URL: {source_url}",
        "",
        "Docker image tags with pull commands.",
    ]

    for tag in tags:
        tag_name = tag.get("name") or ""
        if not tag_name:
            continue
        lines.extend(
            [
                "",
                f"IMAGE: {display_name}",
                f"VERSION: {tag_name}",
                f"TAG: {tag_name}",
                f"LAST_UPDATED: {tag.get('last_updated') or ''}",
                f"INSTALL_COMMAND: docker pull {display_name}:{tag_name}",
            ]
        )

    return sentence_safe_record_text("\n".join(lines).strip())


def parse_docker_image(item: Dict, output_dir: str) -> str:
    image = item.get("image") or item.get("package_id") or item.get("id") or item.get("code")
    if not image:
        raise ValueError("docker_image source must define image or package_id")
    namespace, name, display_name = docker_repo_parts(str(image))
    max_tags = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    api_url = f"https://registry.hub.docker.com/v2/repositories/{namespace}/{name}/tags?page_size={max_tags}"
    payload = fetch_json(api_url)
    text = format_docker_image_text(display_name, payload, max_tags)
    slug = sanitize_filename(item.get("code") or f"docker_{display_name}")
    return save_doc(output_dir, slug, api_url, f"Docker image: {display_name}", text)


def format_go_module_text(module_id: str, versions: List[str], max_versions: int) -> str:
    versions = versions[-max_versions:]
    source_url = f"https://pkg.go.dev/{module_id}"
    proxy_module = quote(module_id, safe="/")
    lines = [
        "SOURCE_TYPE: go_module",
        "PACKAGE_MANAGER: Go modules",
        f"MODULE: {module_id}",
        f"SOURCE_URL: {source_url}",
        "",
        "Go module versions with proxy download links.",
    ]

    for version in versions:
        lines.extend(
            [
                "",
                f"MODULE: {module_id}",
                f"VERSION: {version}",
                f"ZIP_URL: https://proxy.golang.org/{proxy_module}/@v/{version}.zip",
                f"MOD_URL: https://proxy.golang.org/{proxy_module}/@v/{version}.mod",
                f"INFO_URL: https://proxy.golang.org/{proxy_module}/@v/{version}.info",
                f"INSTALL_COMMAND: go get {module_id}@{version}",
            ]
        )

    return sentence_safe_record_text("\n".join(lines).strip())


def parse_go_module(item: Dict, output_dir: str) -> str:
    module_id = item.get("module") or item.get("package_id") or item.get("id") or item.get("code")
    if not module_id:
        raise ValueError("go_module source must define module or package_id")
    proxy_module = quote(str(module_id), safe="/")
    versions_text = fetch_text(f"https://proxy.golang.org/{proxy_module}/@v/list")
    versions = [line.strip() for line in versions_text.splitlines() if line.strip()]
    max_versions = int(item.get("max_versions", PACKAGE_MAX_VERSIONS_DEFAULT))
    text = format_go_module_text(str(module_id), versions, max_versions)
    slug = sanitize_filename(item.get("code") or f"go_{module_id}")
    return save_doc(output_dir, slug, f"https://pkg.go.dev/{module_id}", f"Go module: {module_id}", text)


def _json_for_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def sentence_safe_record_text(text: str) -> str:
    safe_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.endswith((".", "!", "?")):
            safe_lines.append(line)
        else:
            safe_lines.append(f"{stripped}.")
    return "\n".join(safe_lines).strip()


def package_source_from_line(line: str) -> Dict | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split()
    kind = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""

    if kind == "github":
        return {
            "type": "github_releases",
            "url": value,
            "code": sanitize_filename(value),
            "max_releases": GITHUB_MAX_RELEASES_DEFAULT,
        }
    if kind == "nuget":
        return {"type": "nuget_package", "package_id": value, "code": sanitize_filename(f"nuget_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind in {"pypi", "python"}:
        return {"type": "pypi_package", "package_id": value, "code": sanitize_filename(f"pypi_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind == "npm":
        return {"type": "npm_package", "package_id": value, "code": sanitize_filename(f"npm_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind in {"maven", "gradle"}:
        return {"type": "maven_package", "coord": value, "code": sanitize_filename(f"maven_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind in {"crates", "cargo", "rust"}:
        return {"type": "crates_package", "package_id": value, "code": sanitize_filename(f"crates_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind in {"docker", "dockerhub"}:
        return {"type": "docker_image", "image": value, "code": sanitize_filename(f"docker_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}
    if kind in {"go", "gomod"}:
        return {"type": "go_module", "module": value, "code": sanitize_filename(f"go_{value}"), "max_versions": PACKAGE_MAX_VERSIONS_DEFAULT}

    if line.startswith("https://github.com/"):
        return {
            "type": "github_releases",
            "url": line,
            "code": sanitize_filename(line),
            "max_releases": GITHUB_MAX_RELEASES_DEFAULT,
        }

    raise ValueError(f"Unsupported package list line: {line}")


def load_package_sources(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        return []

    if p.suffix.lower() == ".json":
        return load_registry(path)

    sources: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        source = package_source_from_line(line)
        if source is not None:
            sources.append(source)
    return sources


def _has_existing_text(output_dir: str) -> bool:
    return any(Path(output_dir).glob("*.txt"))


def parse_package_sources(
    package_list_path: str,
    raw_root: str,
    max_sources: int | None = None,
    force: bool = False,
) -> Dict:
    sources = load_package_sources(package_list_path)
    registry = {"sources": sources}
    temp_registry_path = Path(raw_root) / "_packages_registry.generated.json"
    temp_registry_path.parent.mkdir(parents=True, exist_ok=True)
    temp_registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        return parse_registry_sources(str(temp_registry_path), raw_root, max_sources=max_sources, force=force)
    finally:
        temp_registry_path.unlink(missing_ok=True)


def load_registry(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("sources", [])


def parse_registry_sources(
    registry_path: str,
    raw_root: str,
    max_sources: int | None = None,
    force: bool = False,
) -> Dict:
    sources = load_registry(registry_path)
    saved_files: List[str] = []
    crawled: List[Dict] = []
    errors: List[Dict] = []
    skipped: List[Dict] = []
    checked = 0
    attempted = 0
    limit = max_sources if max_sources is not None and max_sources > 0 else None

    for item in sources:
        if not item.get("enabled", True):
            continue

        checked += 1
        source_type = item.get("type", "doc_page")
        code = item.get("code", "source")
        output_dir = str(Path(raw_root) / code)
        if not force and _has_existing_text(output_dir):
            skipped.append({"code": code, "type": source_type, "reason": "already exists"})
            continue

        if limit is not None and attempted >= limit:
            break

        attempted += 1
        try:
            if source_type == "python_docs":
                result = crawl_python_docs(
                    root_url=item["root_url"],
                    output_dir=output_dir,
                    max_pages=int(item.get("max_pages", 300)),
                    delay_sec=float(item.get("delay_sec", 0.15)),
                )
                saved_files.extend(result["files"])
                crawled.append(result)
                continue

            if source_type == "doc_page":
                saved = parse_single_doc_page(item["url"], output_dir)
            elif source_type == "google_sheet":
                saved = parse_google_sheet(item, output_dir)
            elif source_type == "github_releases":
                saved = parse_github_releases(item, output_dir)
            elif source_type == "nuget_package":
                saved = parse_nuget_package(item, output_dir)
            elif source_type == "pypi_package":
                saved = parse_pypi_package(item, output_dir)
            elif source_type == "npm_package":
                saved = parse_npm_package(item, output_dir)
            elif source_type == "maven_package":
                saved = parse_maven_package(item, output_dir)
            elif source_type == "crates_package":
                saved = parse_crates_package(item, output_dir)
            elif source_type == "docker_image":
                saved = parse_docker_image(item, output_dir)
            elif source_type == "go_module":
                saved = parse_go_module(item, output_dir)
            else:
                raise ValueError(f"Unsupported source type: {source_type}")

            saved_files.append(saved)
            crawled.append(
                {
                    "root_url": item.get("url") or item.get("csv_url") or saved,
                    "pages_saved": 1,
                    "visited": 1,
                    "files": [saved],
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "code": code,
                    "type": source_type,
                    "error": repr(exc),
                }
            )
            print(f"PACKAGE SOURCE ERROR [{source_type}:{code}]: {exc!r}")
            continue

    return {
        "count": len(saved_files),
        "attempted": attempted,
        "checked": checked,
        "total_sources": len([source for source in sources if source.get("enabled", True)]),
        "files": saved_files,
        "sources": crawled,
        "errors": errors,
        "skipped": skipped,
    }
