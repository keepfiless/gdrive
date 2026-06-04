#!/usr/bin/env python3
"""
Google Drive Folder Lister
Lists all files in a Google Drive folder and creates list.txt
For single files, use the Download workflow directly.
"""

import re
import os
import sys
import subprocess
from typing import Optional, Tuple, List


def extract_folder_id(url: str) -> Optional[str]:
    """Extract folder ID from Google Drive folder URL."""
    url = url.strip()

    patterns = [
        r'drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)',
        r'drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9_-]+)',
        r'folders/([a-zA-Z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def is_single_file_url(url: str) -> bool:
    """Check if URL is a single file URL."""
    file_patterns = [
        r'drive\.google\.com/file/d/',
        r'drive\.google\.com/uc\?id=',
        r'drive\.google\.com/open\?id=',
    ]

    for pattern in file_patterns:
        if re.search(pattern, url):
            return True

    return False


def list_folder(folder_id: str, output_log: str = "gdown_output.log") -> bool:
    """
    Run gdown to list folder contents, killing before actual download.
    """
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

    print(f"📂 Listing folder: {folder_id}")
    print(f"   URL: {folder_url}")

    with open(output_log, 'w') as log_file:
        pass  # Create empty log

    try:
        process = subprocess.Popen(
            ['gdown', '--folder', folder_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        with open(output_log, 'a') as log_file:
            for line in iter(process.stdout.readline, ''):
                log_file.write(line)
                log_file.flush()
                print(f"   {line.rstrip()}")

                # Kill when actual download starts (progress bar appears)
                if re.match(r'^[\s]*[0-9]+%\|', line):
                    print("\n[WATCHER] Transfer started — killing gdown")
                    process.kill()
                    break

        process.wait()
        return True

    except Exception as e:
        print(f"❌ Error running gdown: {e}")
        return False


def parse_gdown_log(log_file: str = "gdown_output.log") -> List[Tuple[str, str, str]]:
    """
    Parse gdown log to extract file information.

    Returns:
        List of (folder_name, file_id, filename) tuples
    """
    if not os.path.exists(log_file):
        print(f"❌ Log file not found: {log_file}")
        return []

    with open(log_file, 'r') as f:
        lines = f.readlines()

    # Pass 1: Extract file_id -> filename from "Processing file" lines
    id_to_name = {}
    for line in lines:
        match = re.match(r'^Processing file ([a-zA-Z0-9_-]{10,})\s+(.+)$', line.strip())
        if match:
            id_to_name[match.group(1)] = match.group(2).strip()

    print(f"Pass 1: Found {len(id_to_name)} file IDs from Processing lines")

    # Pass 2: Extract folder info from "To:" lines
    id_to_folder = {}
    for line in lines:
        line = line.strip()
        match = re.match(r'^To:\s+(.+)$', line)
        if match:
            path = match.group(1).strip()
            parts = path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                folder_name = parts[-2]
                filename = parts[-1]
                for fid, fname in id_to_name.items():
                    if fname == filename:
                        id_to_folder[fid] = folder_name
                        break

    print(f"Pass 2: Resolved folder for {len(id_to_folder)} files from To: lines")

    # Build results in original order
    results = []
    ordered_ids = []
    last_known_folder = "downloads"

    for line in lines:
        match = re.match(r'^Processing file ([a-zA-Z0-9_-]{10,})\s+', line.strip())
        if match and match.group(1) in id_to_name:
            fid = match.group(1)
            if fid not in [x[0] for x in ordered_ids]:
                ordered_ids.append((fid, id_to_name[fid]))

    for fid, fname in ordered_ids:
        folder = id_to_folder.get(fid)
        if folder:
            last_known_folder = folder
        else:
            folder = last_known_folder
        results.append((folder, fid, fname))

    return results


def write_list_file(entries: List[Tuple[str, str, str]], output_file: str = "list.txt") -> int:
    """Write entries to list.txt file."""
    with open(output_file, 'w') as f:
        for folder, file_id, filename in entries:
            link = f"https://drive.google.com/uc?id={file_id}&export=download"
            f.write(f"{folder} = {link}\n")
            print(f"  [{folder}] {filename}")

    return len(entries)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python list_drive.py <google_drive_folder_url>")
        sys.exit(1)

    url = sys.argv[1]

    # Check if it's a single file URL
    if is_single_file_url(url):
        print("=" * 60)
        print("📄 This is a SINGLE FILE URL!")
        print("")
        print("For single files, use the Download workflow directly:")
        print("   1. Go to Actions → '01 __ DOWNLOAD FROM LIST'")
        print("   2. Enter the file URL in the 'drive_url' input")
        print("   3. Run the workflow - no list.txt needed!")
        print("=" * 60)
        sys.exit(1)

    # Extract folder ID
    folder_id = extract_folder_id(url)

    if not folder_id:
        print(f"❌ Could not extract folder ID from URL: {url}")
        print("")
        print("Expected format:")
        print("  https://drive.google.com/drive/folders/FOLDER_ID")
        sys.exit(1)

    print(f"🔍 Folder ID: {folder_id}")
    print("=" * 50)

    # List folder contents
    if not list_folder(folder_id):
        print("❌ Failed to list folder")
        sys.exit(1)

    # Parse and write results
    entries = parse_gdown_log()

    if entries:
        count = write_list_file(entries)
        print("=" * 50)
        print(f"✅ Written {count} entries to list.txt")
    else:
        print("❌ No files found in folder")
        sys.exit(1)

    # Cleanup
    if os.path.exists("gdown_output.log"):
        os.remove("gdown_output.log")


if __name__ == "__main__":
    main()
