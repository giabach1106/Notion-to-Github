import os
import time
import zipfile
import re
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from notion_client import Client
from notion2md.exporter.block import MarkdownExporter

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
REPO_PATH = os.getenv("REPO_PATH") or "/app"
SYNC_FILE = os.path.join(REPO_PATH, "last_sync_timestamp.txt")
OUTPUT_DIR = os.path.join(REPO_PATH, "notes")

notion = Client(auth=NOTION_TOKEN)

def get_last_sync():
    if os.path.exists(SYNC_FILE):
        with open(SYNC_FILE, "r") as f:
            content = f.read().strip()
            return content if content else "2000-01-01T00:00:00.000Z"
    return "2000-01-01T00:00:00.000Z"

def save_sync_time(timestamp):
    with open(SYNC_FILE, "w") as f:
        f.write(timestamp)

def post_process_files(directory):
    print(f"[*] Starting post-processing in {directory}...")
    
    rename_map = {} 
    
    uuid_pattern = re.compile(r'( ?[a-f0-9]{32})(\.[a-zA-Z0-9]+)$')

    for root, dirs, files in os.walk(directory, topdown=False):
        for filename in files:
            match = uuid_pattern.search(filename)
            if match:
                clean_name = filename.replace(match.group(1), "")
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, clean_name)
                
                if old_path != new_path:
                    os.rename(old_path, new_path)
                    rename_map[urllib.parse.quote(filename)] = urllib.parse.quote(clean_name)
                    print(f"    [Renamed] {filename} -> {clean_name}")

    garbage_pattern = re.compile(r"^\[//\]: # \(.*is not supported\)")

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                for old_link, new_link in rename_map.items():
                    if old_link in content:
                        content = content.replace(old_link, new_link)
                
                lines = content.splitlines()
                cleaned_lines = []
                for line in lines:
                    if garbage_pattern.match(line.strip()):
                        continue
                    cleaned_lines.append(line)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("\n".join(cleaned_lines))
                    
    print("[*] Post-processing completed.")

def run_sync():
    print(f"[*] Checking page {PAGE_ID}...")
    try:
        page = notion.pages.retrieve(PAGE_ID)
        last_edited_time = page["last_edited_time"]
    except Exception as e:
        print(f"[!] Notion API Error: {e}")
        return

    last_sync_time = get_last_sync()
    
    if last_edited_time > last_sync_time:
        print(f"[*] Update detected! ({last_edited_time})")

        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        os.system(f"rm -rf {OUTPUT_DIR}/*")

        print(f"[*] Exporting to {OUTPUT_DIR}...")
        exported_path = MarkdownExporter(block_id=PAGE_ID, output_path=OUTPUT_DIR, download=True).export()
        
        exported_str = str(exported_path)
        if exported_str.endswith(".zip"):
            print(f"[*] Unzipping {exported_str}...")
            try:
                with zipfile.ZipFile(exported_str, 'r') as zip_ref:
                    zip_ref.extractall(OUTPUT_DIR)
                os.remove(exported_str)
            except Exception as e:
                print(f"[!] Error unzipping: {e}")

        post_process_files(OUTPUT_DIR)

        os.chdir(REPO_PATH)
        os.system('git config user.email "giabachand@gmail.com"')
        os.system('git config user.name "giabach1106"')

        target_ssh = os.getenv("TARGET_REPO_SSH")
        os.system(f'git remote add notes-repo {target_ssh} 2>/dev/null || git remote set-url notes-repo {target_ssh}')

        os.system("git add notes/")
        
        status = os.popen("git status --porcelain").read()
        if not status:
             print("[i] No content changes detected.")
             save_sync_time(last_edited_time)
             return

        commit_msg = f"Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if os.system(f'git commit -m "{commit_msg}"') == 0:
            print("Pushing to remote...")
            if os.system("git push notes-repo main --force") == 0:
                print("[+] Pushed successfully.")
                save_sync_time(last_edited_time)
            else:
                print("[!] Push failed.")
        else:
            print("[i] Commit failed.")
    else:
        print("[i] No changes.")

if __name__ == "__main__":
    print("Started Notion-to-GitHub Sync Bot (V4: Clean Names & Links)...")
    while True:
        try:
            run_sync()
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
        
        print("Sleeping for 1 minute...")
        time.sleep(60)