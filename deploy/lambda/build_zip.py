"""Monta dist/archiq-lambda.zip para o runtime python3.11 (x86_64) do AWS Lambda, sem Docker.

As dependencias vem como wheels Linux (manylinux), baixadas mesmo rodando no Windows.
O run.sh entra com fim de linha LF e permissao 755: sem isso o Lambda nao consegue executa-lo.
Nunca entram no pacote: .env (as chaves ficam fora; o Lambda usa a role), testes e caches.

    python deploy/lambda/build_zip.py
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "dist" / "lambda-build"
OUT = ROOT / "dist" / "archiq-lambda.zip"
SKIP_DIRS = {"__pycache__", ".taste-skill", ".pytest_cache"}
MAX_DIRECT_UPLOAD = 50 * 1024 * 1024  # acima disso o upload precisa passar por um bucket S3


def add_tree(zf: zipfile.ZipFile, folder: str) -> None:
    for path in sorted((ROOT / folder).rglob("*")):
        if path.is_dir() or SKIP_DIRS & set(path.parts) or path.name == ".env":
            continue
        zf.write(path, path.relative_to(ROOT).as_posix())


def main() -> int:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--quiet",
        "--platform", "manylinux2014_x86_64", "--implementation", "cp", "--python-version", "3.11",
        "--only-binary=:all:", "--target", str(BUILD), "-r", str(ROOT / "requirements_minimal.txt"),
    ], check=True)

    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file() and not SKIP_DIRS & set(path.parts):
                zf.write(path, path.relative_to(BUILD).as_posix())
        for folder in ("src", "data", "web"):
            add_tree(zf, folder)
        script = (Path(__file__).parent / "run.sh").read_bytes().replace(b"\r\n", b"\n")
        info = zipfile.ZipInfo("run.sh")
        info.external_attr = (0o100755 << 16)  # arquivo comum, rwxr-xr-x
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, script)

    size = OUT.stat().st_size
    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        assert "run.sh" in names and "src/api/app.py" in names, "pacote incompleto"
        assert not any(n.endswith(".env") for n in names), ".env nao pode ir no pacote"
        assert b"\r" not in zf.read("run.sh"), "run.sh precisa de fim de linha LF"
    print(f"{OUT} ({size / 1024 / 1024:.1f} MB, {len(names)} arquivos)")
    if size > MAX_DIRECT_UPLOAD:
        print("Acima de 50 MB: o deploy.sh envia pelo bucket S3 de relatorios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
