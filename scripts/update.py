#!/usr/bin/env python3
"""
公司常用软件自动更新脚本
- 从官方源下载最新 Windows 安装包
- 计算 SHA256 校验值
- 更新 software.json
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

# ============================================================
# Configuration
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
MANIFEST_PATH = REPO_ROOT / "software.json"
DOWNLOADS_DIR = REPO_ROOT / "downloads"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============================================================
# Helpers
# ============================================================

def sha256_file(path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, timeout: int = 600) -> bool:
    """Download a file with progress logging."""
    print(f"  ⬇ 下载: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct % 25 == 0:
                        print(f"    {pct}% ({downloaded // (1 << 20)} MB)")
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"    ✅ 完成 ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        if dest.exists():
            dest.unlink()
        return False


def extract_version_from_filename(filename: str) -> Optional[str]:
    """Try to extract version from a filename or URL."""
    patterns = [
        r"(\d+\.\d+\.\d+\.\d+)",
        r"(\d+\.\d+\.\d+)",
        r"(\d+\.\d+)",
        r"v?(\d[\d.]+\d)",
    ]
    for pat in patterns:
        m = re.search(pat, filename)
        if m:
            return m.group(1)
    return None


# ============================================================
# Download Methods
# ============================================================

def download_direct(software: dict) -> Optional[Tuple[str, float, str]]:
    """Direct URL download."""
    url = software.get("download_source", "")
    name = software["id"]
    ext = ".exe"
    if url.lower().endswith(".zip"):
        ext = ".zip"
    elif url.lower().endswith(".msi"):
        ext = ".msi"

    dest = DOWNLOADS_DIR / f"{name}{ext}"
    if not download_file(url, dest):
        return None

    size_mb = os.path.getsize(dest) / (1024 * 1024)
    sha = sha256_file(dest)

    try:
        resp = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=30)
        final_url = resp.url
        version = extract_version_from_filename(final_url) or "latest"
    except Exception:
        version = "latest"

    return version, size_mb, sha


def download_github_release(software: dict) -> Optional[Tuple[str, float, str]]:
    """Download from GitHub Releases API."""
    repo = software.get("download_source", "")
    pattern = software.get("asset_pattern", ".*")
    name = software["id"]

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    gh_headers = {**HEADERS, "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    print(f"  🔍 查询 GitHub Releases: {repo}")
    try:
        resp = requests.get(api_url, headers=gh_headers, timeout=30)
        resp.raise_for_status()
        release = resp.json()
    except Exception as e:
        print(f"    ❌ API 请求失败: {e}")
        return None

    tag = release.get("tag_name", "")
    version = tag.lstrip("v")
    assets = release.get("assets", [])

    pat = re.compile(pattern, re.IGNORECASE)
    matched = None
    for asset in assets:
        if pat.search(asset.get("name", "")):
            matched = asset
            break

    if not matched:
        print(f"    ❌ 未找到匹配 asset (pattern: {pattern})")
        available = [a.get("name", "") for a in assets[:10]]
        print(f"    可用 assets: {available}")
        return None

    download_url = matched["browser_download_url"]
    asset_name = matched["name"]
    ext = Path(asset_name).suffix or ".zip"
    dest = DOWNLOADS_DIR / f"{name}{ext}"

    dl_headers = {**HEADERS, "Accept": "application/octet-stream"}
    if GITHUB_TOKEN:
        dl_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    print(f"  ⬇ 下载: {asset_name} ({matched.get('size', 0) / (1 << 20):.1f} MB)")
    try:
        resp = requests.get(download_url, headers=dl_headers, stream=True, timeout=600)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct % 25 == 0:
                        print(f"    {pct}%")
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"    ✅ 完成 ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        if dest.exists():
            dest.unlink()
        return None

    sha = sha256_file(dest)
    return version, size_mb, sha


def download_scrape(software: dict) -> Optional[Tuple[str, float, str]]:
    """Scrape download URL from a web page."""
    name = software["id"]
    source_url = software.get("download_source", "")

    # Try direct scrape_url first
    scrape_url = software.get("scrape_url", "")
    if scrape_url:
        ext = ".exe"
        if scrape_url.lower().endswith(".zip"):
            ext = ".zip"
        dest = DOWNLOADS_DIR / f"{name}{ext}"
        if download_file(scrape_url, dest):
            version = extract_version_from_filename(scrape_url) or "latest"
            size_mb = os.path.getsize(dest) / (1024 * 1024)
            sha = sha256_file(dest)
            return version, size_mb, sha

    # Fallback: scrape the page for download links
    print(f"  🔍 抓取页面: {source_url}")
    try:
        resp = requests.get(source_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ❌ 抓取失败: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    candidate_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(k in href.lower() for k in [".exe", "download", "setup"]):
            from urllib.parse import urljoin
            candidate_urls.append(urljoin(source_url, href))

    for url in candidate_urls:
        if not url.lower().endswith((".exe", ".msi", ".zip")):
            continue
        ext = ".exe"
        if url.lower().endswith(".zip"):
            ext = ".zip"
        elif url.lower().endswith(".msi"):
            ext = ".msi"

        dest = DOWNLOADS_DIR / f"{name}{ext}"
        if download_file(url, dest):
            version = extract_version_from_filename(url) or "latest"
            size_mb = os.path.getsize(dest) / (1024 * 1024)
            sha = sha256_file(dest)
            return version, size_mb, sha

    print(f"    ❌ 未找到可下载链接")
    return None


# ============================================================
# Main update logic
# ============================================================

DOWNLOAD_METHODS = {
    "direct": download_direct,
    "github_release": download_github_release,
    "scrape": download_scrape,
}


def update_software(software: dict) -> bool:
    """Update a single software entry. Returns True if updated."""
    sid = software["id"]
    name = software["name"]
    method = software.get("download_method", "direct")

    print(f"\n{'='*60}")
    print(f"📦 {name} ({sid})")
    print(f"   方法: {method}")

    fn = DOWNLOAD_METHODS.get(method)
    if not fn:
        print(f"   ❌ 未知下载方法: {method}")
        return False

    try:
        result = fn(software)
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        return False

    if not result:
        print(f"   ❌ 更新失败")
        return False

    version, size_mb, sha = result

    # Check if version changed
    old_version = software.get("version", "")
    if old_version == version and software.get("sha256") == sha:
        print(f"   ✅ 已是最新版本 (v{version})，跳过")
        return False

    # Update manifest entry
    software["version"] = version
    software["size_mb"] = round(size_mb, 1)
    software["sha256"] = sha

    # Store local file info for GitHub Actions
    ext = ".exe"
    for f in DOWNLOADS_DIR.glob(f"{sid}.*"):
        ext = f.suffix
        break
    software["_local_file"] = str(DOWNLOADS_DIR / f"{sid}{ext}")
    software["_asset_name"] = f"{sid}-{version}{ext}"

    print(f"   ✅ 更新完成: v{version} ({size_mb:.1f} MB)")
    return True


def main():
    print("=" * 60)
    print("🔄 公司软件下载站 - 自动更新脚本")
    print(f"   时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    if not MANIFEST_PATH.exists():
        print(f"❌ 未找到 {MANIFEST_PATH}")
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    DOWNLOADS_DIR.mkdir(exist_ok=True)

    updated = False
    updated_list = []

    for sw in manifest["software"]:
        try:
            if update_software(sw):
                updated = True
                updated_list.append(sw["id"])
        except Exception as e:
            print(f"   ❌ 异常: {e}")
            continue

    manifest["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    if updated:
        print(f"✅ 更新了 {len(updated_list)} 个软件: {', '.join(updated_list)}")
    else:
        print(f"✅ 所有软件均为最新版本，无需更新")

    download_files = list(DOWNLOADS_DIR.glob("*"))
    print(f"\n📁 下载文件列表 ({len(download_files)} 个):")
    for fp in sorted(download_files):
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        print(f"   {fp.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
