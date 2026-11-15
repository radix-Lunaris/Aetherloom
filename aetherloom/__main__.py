import argparse
from pathlib import Path
from .launcher import launch

def main():
    p = argparse.ArgumentParser(description="Launch an already-installed Minecraft instance")
    p.add_argument("root", type=Path)
    p.add_argument("version")
    p.add_argument("--java", type=Path, required=True)
    p.add_argument("--name", default="Player")
    p.add_argument("--run-dir", type=Path)
    a = p.parse_args()
    try:
        process = launch(a.root, a.version, a.java, a.name, a.run_dir)
        print("Game PID:", process.pid)
    except (OSError, ValueError) as exc:
        p.exit(1, str(exc) + "\n")

if __name__ == "__main__":
    main()

