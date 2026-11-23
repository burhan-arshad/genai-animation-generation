import os

IGNORE_DIRS = {
    '.git', 'venv', '.venv', 'env', '__pycache__',
    '.pytest_cache', '.mypy_cache', 'node_modules', 'dist', 'build', 'logs'
}

ALLOWED_EXTS = {'.py', '.txt', '.toml', '.yaml', '.yml', '.md', '.env.example'}
output_file = 'project_context.txt'

def build_tree(start_path='.'):
    lines = ["PROJECT FOLDER TREE:", "."]
    for root, dirs, files in os.walk(start_path):
        dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
        level = root.replace(start_path, '').count(os.sep)
        indent = '│   ' * level
        if root != start_path:
            lines.append(f"{'│   ' * (level - 1)}├── {os.path.basename(root)}/")
        for f in sorted(files):
            if f in {'pack.py', output_file}:
                continue
            lines.append(f"{indent}├── {f}")
    return "\n".join(lines)

file_count = 0
with open(output_file, 'w', encoding='utf-8') as out:
    # 1. Write the full folder tree at the top
    out.write(build_tree() + "\n\n")

    # 2. Write the contents of every allowed file
    for root, dirs, files in os.walk('.'):
        dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
        for file in sorted(files):
            if file in {'pack.py', output_file}:
                continue
            if os.path.splitext(file)[1] in ALLOWED_EXTS:
                path = os.path.join(root, file)
                out.write(f"\n{'='*60}\nFILE: {path}\n{'='*60}\n")
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        out.write(f.read() + "\n")
                    file_count += 1
                except Exception as e:
                    out.write(f"[Skipped: {e}]\n")

size_kb = os.path.getsize(output_file) / 1024
print(f"Success! Saved folder tree + {file_count} files into '{output_file}' ({size_kb:.1f} KB).")
