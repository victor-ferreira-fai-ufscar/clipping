from pathlib import Path


def load_names(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de nomes nao encontrado: {file_path}")

    with file_path.open("r", encoding="utf-8") as file_handle:
        return [line.strip() for line in file_handle if line.strip()]
