import os
import time
from datetime import datetime
from dotenv import load_dotenv
from notion_client import Client
from notion2md.exporter.block import StringExporter

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
    page = notion.pages.retrieve(PAGE_ID)
    last_edited_time = page["last_edited_time"]
    last_sync_time = get_last_sync()

    if last_edited_time > last_sync_time:
        print(f"[*] Update detected: {last_edited_time}")
      
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        os.system(f"rm -rf {OUTPUT_DIR}/*")
        
        print(f"[*] Exporting page {PAGE_ID}...")
        StringExporter(block_id=PAGE_ID, output_path=OUTPUT_DIR).export()
        
        files = os.listdir(OUTPUT_DIR)
        print(f"[i] Files generated: {files}")

        if not files:
            print("[!] No files generated. Check Notion connection.")
            return

        os.chdir(REPO_PATH)
        
        os.system('git config user.email "giabachand@gmail.com"')
        os.system('git config user.name "giabach1106"')

        target_ssh = os.getenv("TARGET_REPO_SSH")
        os.system(f'git remote add notes-repo {target_ssh} || git remote set-url notes-repo {target_ssh}')

        os.system("git add notes/")
        
        commit_msg = f"Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        if os.system(f'git commit -m "{commit_msg}"') == 0:
            os.system("git push notes-repo main --force")
            print("Pushed to your Repo.")
        else:
            print("[i] Nothing new to commit in notes folder.")

        save_sync_time(last_edited_time)
        print("Sync completed.")
    else:
        print("[i] No changes.")

if __name__ == "__main__":
    print("Started...")
    while True:
        try:
            run_sync()
        except Exception as e:
            print(f"Error: {e}")
        
        print("Sleeping for 1 minute...")
        time.sleep(60)