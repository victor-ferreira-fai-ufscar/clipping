import csv
from pathlib import Path


def load_names(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de nomes nao encontrado: {file_path}")

    with file_path.open("r", encoding="utf-8", newline="") as file_handle:
        try:
            reader = csv.DictReader(file_handle)

            if reader.fieldnames:
                lower_fieldnames = [
                    field.casefold().strip() for field in reader.fieldnames
                ]
                name_field = None
                for candidate in ("nome", "name"):
                    if candidate in lower_fieldnames:
                        name_field = reader.fieldnames[
                            lower_fieldnames.index(candidate)
                        ]
                        break

                if name_field:
                    names = [row.get(name_field, "").strip() for row in reader]
                    return [name for name in names if name]
        except (csv.Error, ValueError):
            file_handle.seek(0)

        lines = [line.strip().strip('"') for line in file_handle if line.strip()]

        if lines and lines[0].casefold().strip() in {"nome", "name"}:
            lines = lines[1:]

        return lines
