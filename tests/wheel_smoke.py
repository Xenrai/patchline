"""Verify the distributed wheel in an empty directory, outside the checkout."""
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    wheels = sorted(Path(sys.argv[1]).glob("patchline-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("provide a directory containing exactly one Patchline wheel")
    wheel = wheels[0].resolve()
    with tempfile.TemporaryDirectory(prefix="patchline-install-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "env")
        python = root / "env" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                       cwd=root, check=True)
        result = subprocess.run([str(python), "-m", "patchline", "demo"],
                                cwd=root, text=True, capture_output=True, check=True)
        if "4 breaking changes -> 4 potential call sites" not in result.stdout:
            raise SystemExit("installed demo did not produce the expected findings")
        subprocess.run([str(python), "-m", "patchline", "--version"], cwd=root, check=True)
    print("Wheel installation and offline demo passed outside the source checkout.")


if __name__ == "__main__":
    main()
