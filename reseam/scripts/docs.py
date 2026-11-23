#!/usr/bin/env python3.14
"""Fetch the Reseam manuals with sync or read their location offline with status.

Print JSON with absolute paths, source commits, and UTC check times. A failed
refresh reports the error on stderr and can return a previous complete copy.
"""

import argparse
import hashlib
import json
import ntpath
import os
import re
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import partial
from http.client import HTTPException
from itertools import chain
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from urllib.parse import quote
from urllib.request import Request, urlopen

FORGE = "https://git.reseam.app/api/v1"
MIRROR = "https://api.github.com"
RAW = {
    FORGE: "https://git.reseam.app/reseam/{repo}/raw/commit",
    MIRROR: "https://raw.githubusercontent.com/Reseam/{repo}",
}
FOLDERS = {"reseam": ("docs", "crates/cli/docs"), "api": ("docs",)}
FETCH_ERRORS = (OSError, HTTPException, ValueError, KeyError, TypeError)
MARKER = b"reseam-skill cache v1\n"
MARKDOWN = (".md", ".markdown")


def download(url: str) -> bytes:
    """Read a public HTTPS resource. Propagate HTTP errors and timeouts."""
    request = Request(url, headers={"User-Agent": "reseam-skill"})
    with urlopen(request, timeout=12) as response:
        return response.read()


def hosts[T](fetch: Callable[[str], T], first: str = FORGE) -> T:
    """Try each official host once. Report both failures if neither succeeds."""
    errors = []
    for host in dict.fromkeys((first, FORGE, MIRROR)):
        try:
            return fetch(host)
        except FETCH_ERRORS as error:
            errors.append(f"{host}: {error}")
    raise OSError(" / ".join(errors))


def git_id(value: str) -> str:
    """Return a full Git object ID suitable for use as a cache filename."""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        raise ValueError(f"Invalid Git object ID: {value!r}")
    return value


def entry(parent: Path, name: str) -> Path:
    """Locate a child in a managed directory. Reject links and junctions."""
    path = parent / name
    if path.is_symlink() or path.is_junction():
        raise ValueError(f"Unexpected link: {path}")
    return path


def filename(name: str) -> str:
    """Accept one portable path component from a repository listing."""
    if (
        name in {"", ".", ".."}
        or ntpath.basename(name) != name
        or ntpath.isreserved(name)
    ):
        raise ValueError(f"Invalid file name: {name!r}")
    return name


@dataclass(frozen=True)
class Source:
    """Identify one repository at a fixed commit and its available host."""

    repo: str
    commit: str
    host: str


@dataclass
class State:
    """Keep the last successful documentation and CLI checks independently."""

    commits: dict[str, str] = field(default_factory=dict)
    snapshot: str = ""
    checked: str = ""
    latest_cli: str = ""
    release_checked: str = ""
    release_published: str = ""

    def catalog(self, cache: Path) -> Path | None:
        """Locate this snapshot's catalog. Return None if the cache was cleared."""
        if self.snapshot:
            root = entry(cache / "docs", filename(self.snapshot))
            index = entry(root, "INDEX.md")
            if index.is_file():
                return index
        return None


def head(repo: str, previous: str, host: str) -> Source:
    """Resolve main. Accept a changed mirror head only if it advances the cached one."""
    api = f"{host}/repos/reseam/{repo}"
    branch = json.loads(download(f"{api}/branches/main"))["commit"]
    commit = git_id(branch.get("id") or branch["sha"])
    if host == MIRROR and previous and previous != commit:
        comparison = json.loads(download(f"{api}/compare/{previous}...{commit}"))
        if comparison["status"] != "ahead":
            raise ValueError(f"The {repo} mirror is behind or diverged")
    return Source(repo, commit, host)


@dataclass(frozen=True)
class File:
    """Describe a regular file in one of the documentation trees."""

    source: Source
    path: str
    digest: str
    link: str

    def content(self, host: str) -> bytes:
        """Read this file at its recorded commit and verify its Git blob ID."""
        base = RAW[host].format(repo=self.source.repo)
        data = download(f"{base}/{self.source.commit}/{quote(self.path)}")
        algorithm = "sha1" if len(self.digest) == 40 else "sha256"
        digest = hashlib.new(algorithm, f"blob {len(data)}\0".encode() + data)
        if digest.hexdigest() != self.digest:
            raise ValueError(f"Git blob mismatch for {self.path}")
        return data


def files(source: Source, folder: str) -> Iterator[File]:
    """List files below a pinned folder. Reject names that could escape it."""
    route = f"/repos/reseam/{source.repo}/contents/{quote(folder)}?ref={source.commit}"
    entries = hosts(lambda host: json.loads(download(host + route)), source.host)
    for item in entries:
        path = f"{folder}/{filename(item['name'])}"
        match item["type"]:
            case "dir":
                yield from files(source, path)
            case "file":
                yield File(source, path, git_id(item["sha"]), item["html_url"])


def outline(text: str) -> str:
    """Extract a page title, description, and headings. Skip fenced examples."""
    fences = r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$"
    prose = re.sub(fences, "", text)
    title = re.search(r"(?m)^(?:title: +|# +)(.+)$", prose)
    summary = re.search(r"(?m)^description: +(.+)$", prose)
    headings = re.findall(r"(?m)^#{2,3} +(.+)$", prose)
    return " · ".join([m[1].strip() for m in (title, summary) if m] + headings)


def materialize(item: File, stage: Path, objects: Path) -> str:
    """Restore one file and return its catalog row. Reuse bytes and headings by blob ID."""
    blob = entry(objects, item.digest)
    if not blob.exists():
        publish(blob, hosts(item.content, item.source.host))
    relative = f"{item.source.repo}/{item.path}"
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    blob.copy(target)
    if target.suffix.lower() not in MARKDOWN:
        return ""
    card = entry(objects, f"{item.digest}.outline")
    if not card.exists():
        publish(card, outline(target.read_text(encoding="utf-8-sig")).encode())
    description = card.read_text(encoding="utf-8")
    return f"- [{relative}]({quote(relative)}) — {description} [Source]({item.link})"


def publish(path: Path, data: bytes) -> None:
    """Replace a cache file atomically. Discard incomplete writes on failure."""
    with TemporaryDirectory(dir=path.parent) as temp:
        saved = Path(temp) / "data"
        saved.write_bytes(data)
        saved.replace(path)


def collection(source: Source) -> Iterator[File]:
    """Return each requested tree in numeric filename order. Require a manual in each."""
    for folder in FOLDERS[source.repo]:
        group = sorted(
            files(source, folder),
            key=lambda f: re.sub(r"\d+", lambda n: n[0].zfill(12), f.path),
        )
        if not any(f.path.lower().endswith(MARKDOWN) for f in group):
            raise ValueError(f"No Markdown files in {source.repo}/{folder}")
        yield from group


def snapshot(cache: Path, sources: list[Source], state: State) -> None:
    """Publish a complete collection. Preserve previous or partially cleared copies."""
    commits = {source.repo: source.commit for source in sources}
    if commits == state.commits and state.catalog(cache):
        return
    docs = cache / "docs"
    with TemporaryDirectory(dir=docs) as temp, ThreadPoolExecutor(8) as pool:
        stage = Path(temp) / "_".join(commits.values())
        stage.mkdir()
        items = chain.from_iterable(map(collection, sources))
        rows = pool.map(
            partial(materialize, stage=stage, objects=cache / "objects"), items
        )
        catalog = "\n".join(filter(None, rows))
        (stage / "INDEX.md").write_text(
            f"# Reseam documentation\n\n{catalog}\n", encoding="utf-8"
        )
        target = entry(docs, stage.name)
        if target.exists():
            target = docs / f"{stage.name}.{Path(temp).name}"
        stage.rename(target)
    state.commits, state.snapshot = commits, target.name


def cache_location() -> Path:
    """Resolve the XDG cache outside the working project and all Git worktrees."""
    base = Path(os.environ.get("XDG_CACHE_HOME", ""))
    base = base if base.is_absolute() else Path.home() / ".cache"
    root = entry(base.resolve(), "reseam-skill")
    cwd = Path.cwd()
    inside_project = cwd not in {Path.home(), Path(cwd.anchor)} and root.is_relative_to(
        cwd
    )
    if inside_project or any((p / ".git").exists() for p in (root, *root.parents)):
        raise ValueError(f"The cache is inside a project: {root}")
    return root


def initialize(root: Path) -> None:
    """Publish a marked, private directory. Concurrent creators may use the winner."""
    root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root.parent) as temp:
        ready = Path(temp) / "cache"
        ready.mkdir(mode=0o700)
        (ready / ".managed").write_bytes(MARKER)
        try:
            ready.rename(root)
        except OSError:
            if not entry(root, ".managed").is_file():
                raise


def cache_marker(root: Path) -> Path:
    """Create or recognize the skill's cache and check its ownership on POSIX."""
    if not root.exists():
        initialize(root)
    marker = entry(root, ".managed")
    if not marker.is_file() or marker.read_bytes() != MARKER:
        raise ValueError(f"Unrecognized cache: {root}")
    info = root.stat()
    if os.name == "posix" and (info.st_uid, info.st_mode & 0o077) != (os.getuid(), 0):
        raise ValueError(f"The cache must be private and owned by this user: {root}")
    return marker


@contextmanager
def cache_directory() -> Iterator[Path]:
    """Lock the cache and prepare its managed directories until the caller returns."""
    root = cache_location()
    with cache_marker(root).open("r+b") as lock:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
        for name in ("docs", "objects"):
            entry(root, name).mkdir(exist_ok=True)
        yield root


def release(state: State, host: str) -> tuple[str, str]:
    """Read a stable engine tag and UTC publication date. Detect a lagging mirror."""
    info = json.loads(download(f"{host}/repos/reseam/reseam/releases/latest"))
    if info["draft"] or info["prerelease"]:
        raise ValueError("No stable CLI release in the response")
    published = datetime.fromisoformat(info["published_at"]).astimezone(UTC).isoformat()
    tag = filename(info["tag_name"])
    if (
        host == MIRROR
        and tag != state.latest_cli
        and published < state.release_published
    ):
        raise ValueError("The release mirror is behind the cached release")
    return tag, published


def refresh(cache: Path, state: State) -> None:
    """Refresh docs and release metadata independently. Keep usable offline values."""
    now = datetime.now(UTC).isoformat()
    with ThreadPoolExecutor(3) as pool:
        heads = [
            pool.submit(hosts, partial(head, repo, state.commits.get(repo, "")))
            for repo in FOLDERS
        ]
        tag = pool.submit(hosts, partial(release, state))
        try:
            snapshot(cache, [future.result() for future in heads], state)
            state.checked = now
        except FETCH_ERRORS as error:
            print(f"Docs refresh failed: {error}", file=sys.stderr)
        try:
            state.latest_cli, state.release_published = tag.result()
            state.release_checked = now
        except FETCH_ERRORS as error:
            print(f"Release check failed: {error}", file=sys.stderr)
    publish(entry(cache, "state.json"), json.dumps(asdict(state)).encode())


def main() -> None:
    """Print the cache paths, revisions, and check times. Exit 1 without usable docs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("sync", "status"), help="Refresh if due, or read offline"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Check upstream now during sync"
    )
    args = parser.parse_args()
    with cache_directory() as cache:
        path = entry(cache, "state.json")
        state = (
            State(**json.loads(path.read_text(encoding="utf-8")))
            if path.is_file()
            else State()
        )
        due = not state.catalog(cache) or time() - path.stat().st_mtime >= 1800
        if args.action == "sync" and (args.refresh or due):
            refresh(cache, state)
        catalog = state.catalog(cache)
        if catalog is None:
            raise ValueError(
                "No complete documentation copy. Run sync with network access."
            )
        paths = {
            "cache_root": str(cache),
            "docs_root": str(catalog.parent),
            "catalog_path": str(catalog),
        }
        print(json.dumps(asdict(state) | paths, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
