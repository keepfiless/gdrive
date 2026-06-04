#!/usr/bin/env python3
"""
Google Drive Batch Downloader
Downloads files from list.txt in batches, tracking progress in done.txt
"""

import os
import re
import sys
import subprocess
from typing import List, Tuple, Set, Optional


# Configuration
DEFAULT_BATCH_SIZE = 60
MAX_FILE_SIZE_MB = 99  # Files larger than this will be split into RAR parts
DOWNLOAD_TIMEOUT = 600  # seconds


def check_list_exists() -> Tuple[bool, int]:
    """
    Check if list.txt exists and has content.

    Returns:
        (has_content, total_entries)
    """
    if not os.path.exists("list.txt"):
        return False, 0

    with open("list.txt", 'r') as f:
        lines = [l.strip() for l in f if l.strip() and "=" in l]

    return len(lines) > 0, len(lines)


def load_done_urls() -> Set[str]:
    """Load already-downloaded URLs from done.txt."""
    done_urls = set()

    if os.path.exists("done.txt"):
        with open("done.txt", 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("https://"):
                    done_urls.add(line)

    return done_urls


def load_list() -> List[Tuple[str, str]]:
    """
    Load all entries from list.txt.

    Returns:
        List of (folder, url) tuples
    """
    entries = []

    with open("list.txt", 'r') as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            parts = line.split("=", 1)
            folder = parts[0].strip()
            url = parts[1].strip()
            entries.append((folder, url))

    return entries


def pick_batch(batch_size: int = DEFAULT_BATCH_SIZE) -> Tuple[List[Tuple[str, str]], int, int]:
    """
    Pick next batch of files to download.

    Returns:
        (batch, total, done_count)
    """
    all_entries = load_list()
    done_urls = load_done_urls()

    total = len(all_entries)
    done_count = len(done_urls)

    pending = [(folder, url) for folder, url in all_entries if url not in done_urls]
    batch = pending[:batch_size]

    return batch, total, done_count


def extract_file_id(url: str) -> Optional[str]:
    """Extract file ID from Google Drive URL."""
    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else None


def split_large_file(filepath: str) -> bool:
    """
    Split file into RAR parts if larger than MAX_FILE_SIZE_MB.

    Returns:
        True if split was performed, False otherwise
    """
    if not os.path.isfile(filepath):
        return False

    size_mb = os.path.getsize(filepath) / (1024 * 1024)

    if size_mb <= MAX_FILE_SIZE_MB:
        return False

    folder = os.path.dirname(filepath)
    base = os.path.splitext(os.path.basename(filepath))[0]
    rar_prefix = os.path.join(folder, base)

    print(f"  📦 File >{MAX_FILE_SIZE_MB}MB ({size_mb:.1f}MB), splitting: {filepath}")

    try:
        result = subprocess.run(
            ["rar", "a", f"-v{MAX_FILE_SIZE_MB}m", f"{rar_prefix}.rar", filepath],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            os.remove(filepath)
            print(f"  ✅ Split into RAR parts and original removed")
            return True
        else:
            print(f"  ⚠️ RAR split failed: {result.stderr}")
            return False

    except FileNotFoundError:
        print(f"  ⚠️ RAR not installed, keeping original file")
        return False
    except Exception as e:
        print(f"  ⚠️ RAR split error: {e}")
        return False


def download_file(folder: str, url: str) -> bool:
    """
    Download a single file from Google Drive.

    Returns:
        True if successful, False otherwise
    """
    file_id = extract_file_id(url)

    if not file_id:
        print(f"  ❌ Could not extract file ID from: {url}")
        return False

    os.makedirs(folder, exist_ok=True)

    clean_url = f"https://drive.google.com/uc?id={file_id}&confirm=t&export=download"

    try:
        result = subprocess.run(
            ["gdown", clean_url, "-O", f"{folder}/"],
            timeout=DOWNLOAD_TIMEOUT,
        )

        if result.returncode == 0:
            # Check for large files and split
            for filename in os.listdir(folder):
                filepath = os.path.join(folder, filename)
                split_large_file(filepath)
            return True
        else:
            print(f"  ❌ Failed (exit code {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout after {DOWNLOAD_TIMEOUT}s")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def update_done_file(done_urls: Set[str], total: int):
    """Write updated done.txt file."""
    done_count = len(done_urls)

    with open("done.txt", 'w') as f:
        f.write(f"all:{total}\n")
        f.write(f"done:{done_count}\n")

        if done_count >= total:
            f.write("status:COMPLETE ✅\n")
        else:
            f.write(f"remaining:{total - done_count}\n")

        f.write("─" * 40 + "\n")

        for url in sorted(done_urls):
            f.write(url + "\n")


def download_batch(batch_size: int = DEFAULT_BATCH_SIZE) -> Tuple[int, int, int]:
    """
    Download next batch of files.

    Returns:
        (succeeded, failed, remaining)
    """
    batch, total, done_count = pick_batch(batch_size)

    if not batch:
        if done_count >= total:
            print(f"✅ All {total} files have already been downloaded!")
        else:
            print(f"No files to download (total: {total}, done: {done_count})")
        return 0, 0, total - done_count

    print(f"📥 Downloading batch: {len(batch)} files")
    print(f"   Progress: {done_count}/{total} done, {total - done_count} remaining")
    print("=" * 50)

    done_urls = load_done_urls()
    newly_done = []
    failed = []

    for i, (folder, url) in enumerate(batch, 1):
        print(f"\n[{i}/{len(batch)}] Downloading to: {folder}/")
        print(f"  URL: {url}")

        if download_file(folder, url):
            newly_done.append(url)
            print(f"  ✅ Done")
        else:
            failed.append((folder, url))

    # Update done.txt
    all_done = done_urls | set(newly_done)
    update_done_file(all_done, total)

    # Print summary
    remaining = total - len(all_done)

    print(f"\n{'=' * 50}")
    print(f"Batch     : {len(batch)}")
    print(f"Succeeded : {len(newly_done)}")
    print(f"Failed    : {len(failed)}")
    print(f"Total done: {len(all_done)} / {total}")

    if remaining == 0:
        print("🎉 ALL FILES DOWNLOADED!")
    else:
        print(f"⏳ {remaining} files remaining")

    print(f"{'=' * 50}")

    if failed:
        print(f"\nFailed URLs ({len(failed)}):")
        for folder, url in failed:
            print(f"  [{folder}] {url}")

    return len(newly_done), len(failed), remaining


def print_status():
    """Print current download status."""
    has_content, total = check_list_exists()

    if not has_content:
        print("=" * 60)
        print("⚠️  list.txt is empty or missing!")
        print("")
        print("📋 Please run the LIST workflow first:")
        print("   1. Go to Actions → '00 __ LIST GOOGLE DRIVE LINKS'")
        print("   2. Enter your Google Drive folder/file URL")
        print("   3. Run the workflow to generate list.txt")
        print("   4. Then run this download workflow")
        print("=" * 60)
        return False

    done_urls = load_done_urls()
    done_count = len(done_urls)
    remaining = total - done_count

    print(f"📊 Status: {done_count}/{total} files done, {remaining} remaining")

    return True


def main():
    """Main entry point."""
    # Parse arguments
    batch_size = DEFAULT_BATCH_SIZE

    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            print_status()
            return
        elif sys.argv[1] == "--check":
            has_content, total = check_list_exists()
            if has_content:
                print(f"has_work=true")
                print(f"total={total}")
            else:
                print(f"has_work=false")
            return
        else:
            try:
                batch_size = int(sys.argv[1])
            except ValueError:
                print(f"Invalid batch size: {sys.argv[1]}")
                sys.exit(1)

    # Check list.txt
    if not print_status():
        sys.exit(1)

    # Download batch
    succeeded, failed, remaining = download_batch(batch_size)

    # Exit with error if all failed
    if succeeded == 0 and failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
