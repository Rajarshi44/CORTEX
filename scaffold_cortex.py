import os
import shutil
import sys
from pathlib import Path
import subprocess

BATCAVE = Path(r"c:\Users\NIRJHAR BARMA\Desktop\batcave").resolve()
CORTEX = BATCAVE / "cortex-enterprise"

def copy_tree_filtered(src: Path, dst: Path, ignore_dirs=None, ignore_exts=None):
    if ignore_dirs is None:
        ignore_dirs = {".next", ".next-demo", "node_modules", "__pycache__", "venv", ".git", ".pytest_cache"}
    if ignore_exts is None:
        ignore_exts = {".pyc", ".pyo"}

    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        rel_root = Path(root).relative_to(src)
        target_dir = dst / rel_root
        target_dir.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            if any(file.endswith(ext) for ext in ignore_exts):
                continue
            src_file = Path(root) / file
            dst_file = target_dir / file
            shutil.copy2(src_file, dst_file)
            print(f"Copied: {src_file.relative_to(BATCAVE)} -> {dst_file.relative_to(BATCAVE)}")

def main():
    print(f"Starting cortex-enterprise scaffolding from {BATCAVE} to {CORTEX}")
    CORTEX.mkdir(parents=True, exist_ok=True)

    # 1. Demo case data
    demo_src = BATCAVE / "demo-case-data"
    demo_dst = CORTEX / "demo-case-data"
    print(f"\n--- 1. Migrating demo-case-data ---")
    copy_tree_filtered(demo_src, demo_dst)

    # 2. Backend migration
    backend_src = BATCAVE / "backend"
    backend_dst = CORTEX / "backend"
    backend_dst.mkdir(parents=True, exist_ok=True)
    print(f"\n--- 2. Migrating backend ---")
    
    # 2a. app directory
    print("Migrating backend/app...")
    copy_tree_filtered(backend_src / "app", backend_dst / "app")
    
    # 2b. tests directory
    print("Migrating backend/tests...")
    copy_tree_filtered(backend_src / "tests", backend_dst / "tests")
    
    # 2c. data directory
    data_dst = backend_dst / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    # Copy generate_dataset.py
    for f in ["generate_dataset.py", "cna.db", "__init__.py"]:
        src_f = backend_src / "data" / f
        if src_f.exists():
            shutil.copy2(src_f, data_dst / f)
            print(f"Copied backend/data/{f}")
            
    # Copy samples / models if they exist
    for sub in ["models", "samples"]:
        src_sub = backend_src / "data" / sub
        if src_sub.exists():
            copy_tree_filtered(src_sub, data_dst / sub)
            
    # Copy demo-case-data into backend/data/ and backend/data/demo-case-data/
    demo_data_sub = data_dst / "demo-case-data"
    demo_data_sub.mkdir(parents=True, exist_ok=True)
    for f in demo_src.glob("*.csv"):
        shutil.copy2(f, demo_data_sub / f.name)
        shutil.copy2(f, data_dst / f.name)
        print(f"Copied {f.name} into backend/data/")
    for f in demo_src.glob("*.md"):
        shutil.copy2(f, demo_data_sub / f.name)

    # 2d. Configuration files
    for config_file in ["pyproject.toml", ".env", ".env.demo", ".env.example", ".gitignore"]:
        src_conf = backend_src / config_file
        if src_conf.exists():
            shutil.copy2(src_conf, backend_dst / config_file)
            print(f"Copied config: {config_file}")

    # 2e. Ensure init files in existing anomalies and graph modules
    for mod in ["anomalies", "graph", "api"]:
        mod_dir = backend_dst / mod
        if mod_dir.exists():
            init_f = mod_dir / "__init__.py"
            if not init_f.exists():
                init_f.write_text("# Module init\n", encoding="utf-8")
                print(f"Created __init__.py in {mod}")

    # 2f. Virtual environment junction/symlink
    venv_src = backend_src / "venv"
    venv_dst = backend_dst / "venv"
    if not venv_dst.exists():
        print(f"Creating directory junction for venv: {venv_dst} -> {venv_src}")
        res = subprocess.run(["cmd", "/c", f'mklink /J "{venv_dst}" "{venv_src}"'], capture_output=True, text=True)
        print("mklink output:", res.stdout, res.stderr)

    # 3. Frontend migration
    frontend_src = BATCAVE / "frontend-next"
    frontend_dst = CORTEX / "frontend"
    print(f"\n--- 3. Migrating frontend ---")
    frontend_dst.mkdir(parents=True, exist_ok=True)
    
    # 3a. src & public
    print("Migrating frontend/src...")
    copy_tree_filtered(frontend_src / "src", frontend_dst / "src")
    print("Migrating frontend/public...")
    copy_tree_filtered(frontend_src / "public", frontend_dst / "public")
    
    # 3b. Frontend configs & files
    for f in [
        "package.json", "package-lock.json", "tsconfig.json", "next.config.ts",
        "next-env.d.ts", "postcss.config.mjs", "eslint.config.mjs", "components.json",
        "DESIGN.md", "README.md", "AGENTS.md", "CLAUDE.md", ".gitignore"
    ]:
        src_f = frontend_src / f
        if src_f.exists():
            shutil.copy2(src_f, frontend_dst / f)
            print(f"Copied frontend config: {f}")

    # 3c. node_modules junction
    nm_src = frontend_src / "node_modules"
    nm_dst = frontend_dst / "node_modules"
    if nm_src.exists() and not nm_dst.exists():
        print(f"Creating directory junction for node_modules: {nm_dst} -> {nm_src}")
        res = subprocess.run(["cmd", "/c", f'mklink /J "{nm_dst}" "{nm_src}"'], capture_output=True, text=True)
        print("mklink output:", res.stdout, res.stderr)

    print("\nScaffolding migration complete!")

if __name__ == "__main__":
    main()
