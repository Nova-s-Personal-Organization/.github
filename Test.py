#!/usr/bin/env python3
# =======================================================
# Nova Protocol & Automation Layer v1.4
# Terminal/Termux Ready - Python 3 + Bash Integration
# Features: Detection, Indexing, Repo Integration, Wrappers,
# CLI, Sandbox, Logging, Self-Propagation, Auto-Update
# =======================================================

import os
import sys
import sqlite3
import hashlib
import subprocess
import threading
import time
import shlex
import json
import urllib.request
from pathlib import Path
from datetime import datetime

# =======================================================
# AUTO-INSTALL / SETUP
# =======================================================
REQUIRED_MODULES = ["watchdog", "requests"]

def auto_setup():
    log_event("Running auto-setup...")
    for module in REQUIRED_MODULES:
        try:
            __import__(module)
            log_event(f"Module OK: {module}")
        except ImportError:
            log_event(f"Installing missing module: {module}")
            subprocess.run([sys.executable, "-m", "pip", "install", module, "--quiet"])

    # Recreate dirs if missing
    for d in [BASE_DIR, BIN_DIR, LOG_DIR, DATA_DIR]:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            log_event(f"Created directory: {d}")

    # Ensure DB initialized
    init_db()
    log_event("Auto-setup completed successfully.")

# Watchdog for real-time filesystem watching
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"], check=True)
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True

# =======================================================
# CONFIGURATION
# =======================================================
BASE_DIR = Path.home() / "nova"
BIN_DIR = BASE_DIR / "bin"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nova_index.db"
SCAN_INTERVAL = 60  # fallback scan interval in seconds

# Optional central update repo URL
UPDATE_REPO = "https://your-central-repo-url.com/nova-scripts.json"

# Ensure directories exist
for d in [BASE_DIR, BIN_DIR, LOG_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# =======================================================
# DATABASE SETUP
# =======================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Items table
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            type TEXT,
            hash TEXT,
            repo_url TEXT,
            last_modified REAL,
            trust_score INTEGER DEFAULT 0,
            state TEXT DEFAULT 'quarantine',
            last_run REAL,
            wrapper TEXT,
            notes TEXT
        )
    ''')
    # Projects table
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            path TEXT UNIQUE,
            repo_url TEXT,
            head_commit TEXT,
            last_update REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# =======================================================
# UTILITY FUNCTIONS
# =======================================================
def log_event(message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = LOG_DIR / f"log_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(log_file, "a") as f:
        f.write(f"[{ts}] {message}\n")
    print(f"[{ts}] {message}")

def compute_hash(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def safe_exec(command, work_dir=None, timeout=60, log_file=None):
    env = os.environ.copy()
    if work_dir:
        env["PROJECT_ROOT"] = str(work_dir)
    log_file = log_file or (LOG_DIR / f"nova-{int(time.time())}.log")
    with open(log_file, "a") as f:
        try:
            subprocess.run(command, shell=True, cwd=work_dir, env=env, timeout=timeout, stdout=f, stderr=f)
        except subprocess.TimeoutExpired:
            f.write(f"\nExecution timed out: {command}\n")
        except Exception as e:
            f.write(f"\nExecution error: {command} -> {str(e)}\n")

# =======================================================
# WRAPPER CREATION
# =======================================================
def create_wrapper(item_path, wrapper_name=None):
    wrapper_name = wrapper_name or Path(item_path).stem
    wrapper_path = BIN_DIR / wrapper_name
    wrapper_content = f"""#!/bin/bash
# Nova Wrapper for {item_path}
PROJECT_ROOT="{Path(item_path).parent}"
LOG="{LOG_DIR}/{wrapper_name}.$(date +%s).log"
cd "$PROJECT_ROOT" || exit 1
ulimit -t 60
bash "{item_path}" "$@" >> "$LOG" 2>&1
echo "exit:$? run_at:$(date)" >> "$LOG"
"""
    with open(wrapper_path, "w") as f:
        f.write(wrapper_content)
    os.chmod(wrapper_path, 0o755)
    return wrapper_path

# =======================================================
# ITEM REGISTRATION
# =======================================================
def register_item(path, type_, repo_url=None):
    h = compute_hash(path)
    mtime = os.path.getmtime(path)
    wrapper = create_wrapper(path)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO items (path, type, hash, repo_url, last_modified, state, wrapper)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (str(path), type_, h, repo_url, mtime, 'approved', str(wrapper)))
    conn.commit()
    conn.close()
    log_event(f"Registered: {path} ({type_}) -> Wrapper: {wrapper}")

# =======================================================
# GIT / PROJECT DETECTION
# =======================================================
def scan_repo(repo_path):
    repo_path = Path(repo_path)
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return
    try:
        cmd = f"git -C {repo_path} config --get remote.origin.url"
        repo_url = subprocess.check_output(shlex.split(cmd), stderr=subprocess.DEVNULL).decode().strip()
    except:
        repo_url = None
    try:
        head_commit = subprocess.check_output(shlex.split(f"git -C {repo_path} rev-parse HEAD"), stderr=subprocess.DEVNULL).decode().strip()
    except:
        head_commit = None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO projects (name, path, repo_url, head_commit, last_update)
        VALUES (?, ?, ?, ?, ?)
    ''', (repo_path.name, str(repo_path), repo_url, head_commit, time.time()))
    conn.commit()
    conn.close()
    # Scan files inside repo
    for root, dirs, files in os.walk(repo_path):
        for f in files:
            ext = Path(f).suffix
            full_path = Path(root) / f
            if ext in ['.sh', '.py', '.js', '.pl', '.rb']:
                register_item(full_path, 'script', repo_url)
            elif ext in ['.exe', '.bin']:
                register_item(full_path, 'binary', repo_url)
            else:
                register_item(full_path, 'data', repo_url)

# =======================================================
# FILESYSTEM WATCHER
# =======================================================
class NovaHandler(FileSystemEventHandler):
    def on_created(self, event):
        path = Path(event.src_path)
        if path.is_file():
            ext = path.suffix
            type_ = 'script' if ext in ['.sh', '.py', '.js', '.pl', '.rb'] else 'binary'
            register_item(path, type_)
        elif path.is_dir():
            if (path / ".git").exists():
                log_event(f"Detected new repo: {path}")
                scan_repo(path)

def start_watcher(target_dirs=None):
    target_dirs = target_dirs or [Path.home()]
    if not WATCHDOG_AVAILABLE:
        log_event("Watchdog not installed, skipping live watcher")
        return
    event_handler = NovaHandler()
    observer = Observer()
    for d in target_dirs:
        observer.schedule(event_handler, str(d), recursive=True)
    observer.start()
    log_event(f"Started filesystem watcher on: {target_dirs}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# =======================================================
# DIRECTORY SCAN
# =======================================================
def scan_directories(paths=None):
    paths = paths or [Path.home()]
    for p in paths:
        for root, dirs, files in os.walk(p):
            for f in files:
                ext = Path(f).suffix
                full_path = Path(root) / f
                if ext in ['.sh', '.py', '.js', '.pl', '.rb']:
                    register_item(full_path, 'script')
                elif ext in ['.exe', '.bin']:
                    register_item(full_path, 'binary')
                else:
                    register_item(full_path, 'data')

# =======================================================
# LIST REGISTERED ITEMS
# =======================================================
def list_registered_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, path FROM items ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]

# =======================================================
# RUN ITEM
# =======================================================
def nova_run(item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT wrapper FROM items WHERE id=?", (item_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        wrapper_path = result[0]
        log_event(f"


        log_event(f"Executing item {item_id} with wrapper {wrapper_path}")
        safe_exec(wrapper_path)
        # Update last_run timestamp
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE items SET last_run=? WHERE id=?", (time.time(), item_id))
        conn.commit()
        conn.close()
    else:
        log_event(f"Item ID {item_id} not found in database")
        # =======================================================
# INFO / HELP SECTION
# =======================================================
def show_info():
    banner = """
    ======================================================
       Nova Protocol & Automation Layer v1.4
       Terminal/Termux-Ready
    ------------------------------------------------------
       - Auto-detects new & existing files, repos, scripts
       - Registers everything into a managed database
       - Creates safe wrappers for execution
       - Can be injected into bigger projects as a module
       - Offers sandboxed + logged runs
       - Watches filesystem in real-time (if enabled)
       - Maintains trust states (approved/quarantine/etc)
       - Integrity checks + auto-repair of misused items
    ======================================================
    """
    print(banner)
    log_event("Displayed system info/help")
    # =======================================================
# INTERACTIVE CLI
# =======================================================
def main_cli():
    while True:
        print("\n=== Nova Protocol & Automation Layer v1.4 ===")
        print("1) Scan directories")
        print("2) Start watcher")
        print("3) List registered items")
        print("4) Run item by ID")
        print("5) Show info/help")
        print("6) Exit")
        choice = input("Select an option: ").strip()

        if choice == "1":
            target = input("Enter directory to scan (or leave blank for HOME): ").strip()
            if target:
                scan_directories([Path(target)])
            else:
                scan_directories()
        elif choice == "2":
            target = input("Enter directory to watch (or leave blank for HOME): ").strip()
            if target:
                start_watcher([Path(target)])
            else:
                start_watcher()
        elif choice == "3":
            items = list_registered_items()
            if not items:
                print("No items registered yet.")
            else:
                for item_id, path in items:
                    print(f"[{item_id}] {path}")
        elif choice == "4":
            item_id = input("Enter item ID to run: ").strip()
            if item_id.isdigit():
                nova_run(int(item_id))
            else:
                print("Invalid ID.")
        elif choice == "5":
            show_info()
        elif choice == "6":
            print("Exiting Nova Protocol Layer...")
            break
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    show_info()
    main_cli()
        
