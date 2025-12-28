#!/usr/bin/env python3
"""
Notion to GitHub Automated Backup System
Uses Notion's internal API for recursive exports
"""

import os
import re
import json
import time
import shutil
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple

import requests
from tqdm import tqdm
from dotenv import load_dotenv


class NotionExporter:
    """Handles Notion export operations using internal API"""
    
    BASE_URL = "https://www.notion.so/api/v3"
    
    def __init__(self, token_v2: str, space_id: str):
        self.token_v2 = token_v2
        self.space_id = space_id
        self.session = requests.Session()
        self.session.headers.update({
            "Cookie": f"token_v2={token_v2}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
    
    def export_space(
        self,
        page_id: Optional[str] = None,
        export_type: str = "markdown",
        include_files: bool = True,
        recursive: bool = True,
        timezone: str = "America/New_York"
    ) -> Optional[str]:
        """
        Trigger Notion export and return download URL
        
        Args:
            page_id: Specific page to export (None = entire space)
            export_type: 'markdown' or 'html'
            include_files: Include images/attachments
            recursive: Export nested pages
            timezone: Timezone for export
        
        Returns:
            Download URL for the export zip file
        """
        # Determine export options
        export_options = {
            "exportType": export_type,
            "timeZone": timezone,
            "locale": "en"
        }
        
        # Build task payload
        task_payload = {
            "task": {
                "eventName": "exportSpace",
                "request": {
                    "spaceId": self.space_id,
                    "exportOptions": export_options,
                    "shouldExportComments": False,
                    "recursive": recursive,
                    "includeContents": "everything" if include_files else "no_files"
                }
            }
        }
        
        # If page_id specified, export only that page
        if page_id:
            task_payload["task"]["request"]["exportType"] = "currentView"
            task_payload["task"]["request"]["blockId"] = page_id
        
        print(f"[Notion] Triggering export...")
        print(f"  - Type: {export_type}")
        print(f"  - Recursive: {recursive}")
        print(f"  - Include files: {include_files}")
        print(f"  - Page ID: {page_id or 'Entire workspace'}")
        
        try:
            # Enqueue the export task
            response = self.session.post(
                f"{self.BASE_URL}/enqueueTask",
                json=task_payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            task_id = data.get("taskId")
            if not task_id:
                print(f"[Error] No taskId in response: {data}")
                return None
            
            print(f"[Notion] Export task created: {task_id}")
            
            # Poll for completion
            download_url = self._poll_export_status(task_id)
            return download_url
            
        except requests.exceptions.RequestException as e:
            print(f"[Error] Failed to trigger export: {e}")
            return None
    
    def _poll_export_status(self, task_id: str, max_attempts: int = 60) -> Optional[str]:
        """
        Poll task status until export is ready
        
        Args:
            task_id: The export task ID
            max_attempts: Maximum polling attempts (1 attempt = 10 seconds)
        
        Returns:
            Download URL when ready
        """
        print("[Notion] Waiting for export to complete...")
        
        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    f"{self.BASE_URL}/getTasks",
                    json={"taskIds": [task_id]},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                # Debug: Print raw response on first attempt
                if attempt == 0:
                    print(f"[Debug] Raw API response: {json.dumps(data, indent=2)[:500]}...")
                
                results = data.get("results", [])
                if not results:
                    print(f"[Warning] No results for task {task_id}")
                    time.sleep(10)
                    continue
                
                task = results[0]
                
                # Debug: Show task structure
                if attempt < 3:
                    print(f"[Debug] Task keys: {list(task.keys())}")
                
                status = task.get("status", {})
                state = status.get("type")
                
                # Try alternative keys for state
                if not state:
                    state = task.get("state") or status.get("state")
                
                # Debug: Show status structure
                if attempt < 3:
                    print(f"[Debug] Status: {json.dumps(status, indent=2)[:300]}")
                
                if state == "complete":
                    export_url = status.get("exportURL")
                    if export_url:
                        print(f"[Notion] Export ready! URL obtained.")
                        return export_url
                    else:
                        print("[Error] Export complete but no URL found")
                        print(f"[Debug] Full status: {json.dumps(status, indent=2)}")
                        return None
                
                elif state == "failure":
                    error = status.get("error", "Unknown error")
                    print(f"[Error] Export failed: {error}")
                    print(f"[Debug] Full response: {json.dumps(data, indent=2)}")
                    return None
                
                else:
                    # Still in progress
                    progress = status.get("pagesExported", 0)
                    print(f"  [{attempt+1}/{max_attempts}] Status: {state}, Pages: {progress}")
                    time.sleep(10)
            
            except requests.exceptions.RequestException as e:
                print(f"[Error] Polling failed: {e}")
                time.sleep(10)
        
        print("[Error] Export timeout - max attempts reached")
        return None
    
    def download_export(self, url: str, output_path: str) -> bool:
        """
        Download the export ZIP file
        
        Args:
            url: Download URL from Notion
            output_path: Local path to save ZIP
        
        Returns:
            True if successful
        """
        print(f"[Download] Fetching export file...")
        
        try:
            response = self.session.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(output_path, 'wb') as f:
                with tqdm(total=total_size, unit='iB', unit_scale=True) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        size = f.write(chunk)
                        pbar.update(size)
            
            print(f"[Download] Saved to {output_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"[Error] Download failed: {e}")
            return False


class FileProcessor:
    """Cleans up Notion export files"""
    
    UUID_PATTERN = re.compile(r'\s+[a-f0-9]{32}$|\s+[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    
    @staticmethod
    def unzip_export(zip_path: str, extract_to: str) -> Optional[str]:
        """
        Extract ZIP file and return the root export directory
        
        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract to
        
        Returns:
            Path to extracted root directory
        """
        print(f"[Extract] Unzipping export...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            # Find the root export directory (usually named "Export-...")
            extracted_items = list(Path(extract_to).iterdir())
            if extracted_items:
                root_dir = extracted_items[0]
                print(f"[Extract] Root directory: {root_dir}")
                return str(root_dir)
            
            return extract_to
            
        except zipfile.BadZipFile as e:
            print(f"[Error] Invalid ZIP file: {e}")
            return None
    
    @staticmethod
    def clean_filename(filename: str) -> str:
        """Remove Notion UUID from filename"""
        name, ext = os.path.splitext(filename)
        cleaned = FileProcessor.UUID_PATTERN.sub('', name)
        return f"{cleaned}{ext}"
    
    def rename_files_and_folders(self, root_path: str) -> Dict[str, str]:
        """
        Recursively rename all files and folders to remove UUIDs
        
        Args:
            root_path: Root directory to process
        
        Returns:
            Mapping of old paths to new paths
        """
        print("[Cleanup] Removing UUIDs from filenames...")
        
        rename_map = {}
        root = Path(root_path)
        
        # Process in reverse depth order (deepest first)
        all_paths = sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True)
        
        for old_path in all_paths:
            if not old_path.exists():
                continue
            
            old_name = old_path.name
            new_name = self.clean_filename(old_name)
            
            if old_name != new_name:
                new_path = old_path.parent / new_name
                
                # Handle naming conflicts
                counter = 1
                while new_path.exists():
                    name, ext = os.path.splitext(new_name)
                    new_path = old_path.parent / f"{name}_{counter}{ext}"
                    counter += 1
                
                try:
                    old_path.rename(new_path)
                    rename_map[str(old_path)] = str(new_path)
                    print(f"  Renamed: {old_name} → {new_name}")
                except Exception as e:
                    print(f"  [Warning] Could not rename {old_name}: {e}")
        
        return rename_map
    
    def fix_markdown_links(self, root_path: str, rename_map: Dict[str, str]):
        """
        Fix internal links in Markdown files to match new filenames
        
        Args:
            root_path: Root directory to process
            rename_map: Mapping of old to new paths
        """
        print("[Cleanup] Fixing Markdown links...")
        
        root = Path(root_path)
        markdown_files = list(root.rglob("*.md"))
        
        for md_file in markdown_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                original_content = content
                
                # Fix relative links
                for old_path, new_path in rename_map.items():
                    old_name = Path(old_path).name
                    new_name = Path(new_path).name
                    
                    # Replace URL-encoded and regular links
                    content = content.replace(
                        old_name.replace(' ', '%20'),
                        new_name.replace(' ', '%20')
                    )
                    content = content.replace(old_name, new_name)
                
                if content != original_content:
                    md_file.write_text(content, encoding='utf-8')
                    print(f"  Fixed links in: {md_file.name}")
            
            except Exception as e:
                print(f"  [Warning] Could not process {md_file.name}: {e}")


class GitManager:
    """Handles Git operations"""
    
    def __init__(self, repo_path: str, remote_url: str, user_name: str, user_email: str):
        self.repo_path = Path(repo_path)
        self.remote_url = remote_url
        self.user_name = user_name
        self.user_email = user_email
    
    def _run_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Execute git command and return success status"""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timeout"
        except Exception as e:
            return False, str(e)
    
    def initialize_repo(self) -> bool:
        """Initialize or clone the repository"""
        print(f"[Git] Initializing repository at {self.repo_path}...")
        
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        # Check if already a git repo
        if (self.repo_path / ".git").exists():
            print("[Git] Repository already initialized")
            return True
        
        # Initialize new repo
        success, output = self._run_command(["git", "init"])
        if not success:
            print(f"[Error] Git init failed: {output}")
            return False
        
        # Configure user
        self._run_command(["git", "config", "user.name", self.user_name])
        self._run_command(["git", "config", "user.email", self.user_email])
        
        # Add remote
        self._run_command(["git", "remote", "add", "origin", self.remote_url])
        
        # Try to pull existing content
        print("[Git] Attempting to pull existing content...")
        self._run_command(["git", "pull", "origin", "main", "--allow-unrelated-histories"])
        
        return True
    
    def commit_and_push(self, message: Optional[str] = None) -> bool:
        """
        Add, commit, and push changes
        
        Args:
            message: Commit message (auto-generated if None)
        
        Returns:
            True if successful
        """
        if message is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Automated backup: {timestamp}"
        
        print(f"[Git] Checking for changes...")
        
        # Check if there are changes
        success, output = self._run_command(["git", "status", "--porcelain"])
        if not output.strip():
            print("[Git] No changes to commit")
            return True
        
        print(f"[Git] Changes detected:\n{output[:500]}")
        
        # Add all changes
        print("[Git] Staging changes...")
        success, output = self._run_command(["git", "add", "."])
        if not success:
            print(f"[Error] Git add failed: {output}")
            return False
        
        # Commit
        print("[Git] Committing...")
        success, output = self._run_command(["git", "commit", "-m", message])
        if not success and "nothing to commit" not in output.lower():
            print(f"[Error] Git commit failed: {output}")
            return False
        
        # Push
        print("[Git] Pushing to remote...")
        success, output = self._run_command(["git", "push", "origin", "main"])
        if not success:
            # Try creating main branch if it doesn't exist
            self._run_command(["git", "branch", "-M", "main"])
            success, output = self._run_command(["git", "push", "-u", "origin", "main"])
            
            if not success:
                print(f"[Error] Git push failed: {output}")
                return False
        
        print("[Git] Successfully pushed changes!")
        return True


class BackupOrchestrator:
    """Main orchestrator for the backup process"""
    
    def __init__(self):
        load_dotenv()
        
        # Load configuration
        self.notion_token = os.getenv("NOTION_TOKEN_V2")
        self.space_id = os.getenv("NOTION_SPACE_ID")
        self.page_id = os.getenv("NOTION_PAGE_ID")
        self.repo_url = os.getenv("GITHUB_REPO_URL")
        self.repo_path = os.getenv("REPO_PATH", "/repo")
        self.git_user = os.getenv("GIT_USER_NAME", "Notion Backup Bot")
        self.git_email = os.getenv("GIT_USER_EMAIL", "backup@example.com")
        self.interval_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
        
        # Export options
        self.export_type = os.getenv("EXPORT_TYPE", "markdown")
        self.include_files = os.getenv("INCLUDE_FILES", "true").lower() == "true"
        self.recursive = os.getenv("RECURSIVE", "true").lower() == "true"
        self.timezone = os.getenv("TIMEZONE", "America/New_York")
        
        self.validate_config()
        
        # Initialize components
        self.exporter = NotionExporter(self.notion_token, self.space_id)
        self.processor = FileProcessor()
        self.git_manager = GitManager(
            self.repo_path,
            self.repo_url,
            self.git_user,
            self.git_email
        )
    
    def validate_config(self):
        """Validate required configuration"""
        required = {
            "NOTION_TOKEN_V2": self.notion_token,
            "NOTION_SPACE_ID": self.space_id,
            "GITHUB_REPO_URL": self.repo_url
        }
        
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    def run_backup(self) -> bool:
        """Execute a single backup cycle"""
        print("\n" + "="*60)
        print(f"BACKUP STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")
        
        temp_dir = Path("/tmp/notion_export")
        zip_path = temp_dir / "export.zip"
        
        try:
            # Ensure temp directory exists
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Step 1: Export from Notion
            download_url = self.exporter.export_space(
                page_id=self.page_id,
                export_type=self.export_type,
                include_files=self.include_files,
                recursive=self.recursive,
                timezone=self.timezone
            )
            
            if not download_url:
                print("[Error] Failed to get export URL")
                return False
            
            # Step 2: Download export
            if not self.exporter.download_export(download_url, str(zip_path)):
                print("[Error] Failed to download export")
                return False
            
            # Step 3: Extract
            extracted_path = self.processor.unzip_export(str(zip_path), str(temp_dir))
            if not extracted_path:
                print("[Error] Failed to extract export")
                return False
            
            # Step 4: Clean up files
            rename_map = self.processor.rename_files_and_folders(extracted_path)
            self.processor.fix_markdown_links(extracted_path, rename_map)
            
            # Step 5: Initialize Git repo
            if not self.git_manager.initialize_repo():
                print("[Error] Failed to initialize Git repository")
                return False
            
            # Step 6: Clear old content and copy new
            print("[Sync] Replacing repository content...")
            repo_path = Path(self.repo_path)
            
            # Remove old content (except .git)
            for item in repo_path.iterdir():
                if item.name != ".git":
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            
            # Copy new content
            for item in Path(extracted_path).iterdir():
                dest = repo_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            
            # Step 7: Commit and push
            if not self.git_manager.commit_and_push():
                print("[Error] Failed to commit and push changes")
                return False
            
            print("\n" + "="*60)
            print("BACKUP COMPLETED SUCCESSFULLY")
            print("="*60 + "\n")
            return True
            
        except Exception as e:
            print(f"\n[Error] Backup failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Cleanup
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def run_forever(self):
        """Run backup loop indefinitely"""
        print("="*60)
        print("NOTION BACKUP SERVICE STARTED")
        print(f"Backup interval: {self.interval_hours} hours")
        print("="*60)
        
        while True:
            try:
                success = self.run_backup()
                
                if success:
                    print(f"\n[Scheduler] Next backup in {self.interval_hours} hours...")
                else:
                    print(f"\n[Scheduler] Backup failed. Retrying in {self.interval_hours} hours...")
                
                time.sleep(self.interval_hours * 3600)
                
            except KeyboardInterrupt:
                print("\n\n[Shutdown] Received interrupt signal. Exiting gracefully...")
                break
            except Exception as e:
                print(f"\n[Error] Unexpected error in main loop: {e}")
                print(f"[Scheduler] Retrying in 1 hour...")
                time.sleep(3600)


def main():
    """Entry point"""
    try:
        orchestrator = BackupOrchestrator()
        orchestrator.run_forever()
    except ValueError as e:
        print(f"\n[Configuration Error] {e}")
        print("Please check your .env file and ensure all required variables are set.")
        exit(1)
    except Exception as e:
        print(f"\n[Fatal Error] {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()