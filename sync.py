import os
import time
import zipfile 
from datetime import datetime
from dotenv import load_dotenv
from notion_client import Client
from notion2md.exporter.block import MarkdownExporter

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
REPO_PATH = os.getenv("REPO_PATH")
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
        MarkdownExporter(block_id=PAGE_ID, output_path=OUTPUT_DIR, download=True).export()

        files_in_dir = os.listdir(OUTPUT_DIR)
        for file in files_in_dir:
            if file.endswith(".zip"):
                zip_path = os.path.join(OUTPUT_DIR, file)
                print(f"[*] Unzipping {file}...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(OUTPUT_DIR)
                os.remove(zip_path)
        final_files = os.listdir(OUTPUT_DIR)
        print(f"[i] Files ready to push: {final_files}")

        if not final_files:
            print("[!] No files generated.")
            return

        os.chdir(REPO_PATH)
        os.system('git config user.email "giabachand@gmail.com"')
        os.system('git config user.name "giabach1106"')

        target_ssh = os.getenv("TARGET_REPO_SSH")
        os.system(f'git remote add notes-repo {target_ssh} 2>/dev/null || git remote set-url notes-repo {target_ssh}')

        os.system("git add notes/")
        
        status = os.popen("git status --porcelain").read()
        if not status:
             print("[i] No content changes detected by Git.")
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
    print("Started Notion-to-GitHub Sync Bot (Unzip logic added)...")
    while True:
        try:
            run_sync()
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
        
        print("Sleeping for 1 minute...")
        time.sleep(60)