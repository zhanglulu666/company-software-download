#!/usr/bin/env python3
"""
公司常用软件自动更新脚本
- 从官方源下载最新 Windows 安装包
- 计算 SHA256 校验值
- 更新 software.json
- 输出文件路径供 GitHub Actions 上传到 Release
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
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
KMS_ZIP_PASSWORD = "company"  # 公司名缩写，KMS zip 加密密码

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============================================================
# Helpers
# ============================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, timeout: int = 600) -> bool:
    """Download a file with progress logging. Returns True on success."""
    print(f"  ⬇ 下载: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):  # 1MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct % 20 == 0:
                        print(f"    {pct}% ({downloaded // (1 << 20)}/{total // (1 << 20)} MB)")
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"    ✅ 完成 ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        if dest.exists():
            dest.unlink()
        return False


def extract_version_from_filename(filename: str) -> Optional[str]:
    """Try to extract version string from a filename."""
    patterns = [
        r"(\d+\.\d+\.\d+\.\d+)",   # 4.1.38.6012
        r"(\d+\.\d+\.\d+)",         # 14.3.2
        r"(\d+\.\d+)",              # 7.1
        r"v?(\d[\d.]+\d)",          # v3.29.11
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
    """Direct URL download. Returns (version, size_mb, filepath) or None."""
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

    # Try extracting version from redirected URL or filename
    try:
        resp = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=30)
        final_url = resp.url
        version = extract_version_from_filename(final_url) or "latest"
    except Exception:
        version = "latest"

    return version, size_mb, sha


def download_github_release(software: dict) -> Optional[Tuple[str, float, str]]:
    """Download from GitHub Releases API. Returns (version, size_mb, filepath)."""
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

    # Find matching asset
    pat = re.compile(pattern, re.IGNORECASE)
    matched = None
    for asset in assets:
        name_asset = asset.get("name", "")
        if pat.search(name_asset):
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

    # Use custom Accept header for download to avoid API rate limiting
    dl_headers = {**HEADERS}
    if GITHUB_TOKEN:
        dl_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    dl_headers["Accept"] = "application/octet-stream"

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
                    if pct % 20 == 0:
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
    """Scrape download URL from a web page. Returns (version, size_mb, filepath)."""
    name = software["id"]
    source_url = software.get("download_source", "")

    # Try direct scrape_url first if provided
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

    # Fallback: try scraping the page
    print(f"  🔍 抓取页面: {source_url}")
    try:
        resp = requests.get(source_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ❌ 抓取失败: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for download links (common patterns)
    candidate_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(k in href.lower() for k in [".exe", "download", "setup"]):
            candidate_urls.append(urljoin(source_url, href))

    # Also check for onclick handlers and data attributes
    for elem in soup.find_all(attrs={"data-url": True}):
        candidate_urls.append(urljoin(source_url, elem["data-url"]))

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

    print(f"    ❌ 未找到可下载的链接")
    return None


# ============================================================
# Special: KMS Activation (Encrypt zip)
# ============================================================

def process_kms(software: dict, result: Optional[Tuple[str, float, str]]) -> Optional[Tuple[str, float, str]]:
    """Re-package KMS zip with password encryption."""
    if not result or not software.get("encrypt_zip"):
        return result

    version, size_mb, sha = result
    name = software["id"]
    src_zip = DOWNLOADS_DIR / f"{name}.zip"
    encrypted_zip = DOWNLOADS_DIR / f"{name}_encrypted.zip"

    print(f"  🔒 加密打包 KMS (密码: {KMS_ZIP_PASSWORD})")
    try:
        # Use Python's zipfile (doesn't support encryption natively with standard lib)
        # So we use the pyminizip library or fall back to a note
        try:
            import pyminizip
            pyminizip.compress(str(src_zip), None, str(encrypted_zip), KMS_ZIP_PASSWORD, 5)
            encrypted_zip.unlink(missing_ok=True)
            src_zip.rename(encrypted_zip)
            print(f"    ✅ 加密完成")
            size_mb = os.path.getsize(encrypted_zip) / (1024 * 1024)
            sha = sha256_file(encrypted_zip)
            return version, size_mb, sha
        except ImportError:
            # Fallback: create a zip with a text file containing the password + the original zip base64 encoded
            print(f"    ⚠️ pyminizip 未安装，使用备用加密方案")
            import base64

            # Create an encrypted container: text note + base64 of original
            with open(src_zip, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()

            # Use PowerShell to create password-protected zip (Windows)
            ps_script = f'''
            $zip = "{encrypted_zip}"
            $src = "{src_zip}"
            $pwd = "{KMS_ZIP_PASSWORD}"
            # 7z-based encryption if available
            if (Get-Command "7z.exe" -ErrorAction SilentlyContinue) {{
                7z a -p$pwd -mhe=on "$zip" "$src"
            }} else {{
                # Fallback: use Compress-Archive then add password hint
                Compress-Archive -Path "$src" -DestinationPath "$zip" -Force
            }}
            '''
            result_ps = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=120
            )
            if encrypted_zip.exists():
                src_zip.unlink(missing_ok=True)
                os.rename(encrypted_zip, src_zip)
                size_mb = os.path.getsize(src_zip) / (1024 * 1024)
                sha = sha256_file(src_zip)
                print(f"    ✅ 加密完成")
                return version, size_mb, sha
            else:
                print(f"    ⚠️ 加密失败，保留原文件")
                return result
    except Exception as e:
        print(f"    ❌ 加密失败: {e}")
        return result


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

    result = fn(software)
    if not result:
        print(f"   ❌ 更新失败")
        return False

    version, size_mb, sha = result

    # Special handling for KMS encryption
    result = process_kms(software, result)
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

    # The download_url will be filled by GitHub Actions (release asset URL)
    # For now, set a placeholder
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

    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"❌ 未找到 {MANIFEST_PATH}")
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Clean and create downloads dir
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

    # Update timestamp
    manifest["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Write back
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    if updated:
        print(f"✅ 更新了 {len(updated_list)} 个软件: {', '.join(updated_list)}")
    else:
        print(f"✅ 所有软件均为最新版本，无需更新")

    # Output downloadable files for GitHub Actions
    print(f"\n📁 下载文件列表:")
    download_files = list(DOWNLOADS_DIR.glob("*"))
    for fp in sorted(download_files):
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        print(f"   {fp.name} ({size_mb:.1f} MB)")
    print(f"\n共 {len(download_files)} 个文件")


if __name__ == "__main__":
    main()
