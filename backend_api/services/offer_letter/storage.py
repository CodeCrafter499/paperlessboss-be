import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE_PATH = PROJECT_ROOT / "generated_letters"


def letter_paths(company_id: uuid.UUID, employee_id: int) -> tuple[Path, Path]:
    folder = BASE_PATH / str(company_id) / str(employee_id)
    pdf_path = folder / "appointment_letter.pdf"
    docx_path = folder / "appointment_letter.docx"
    return pdf_path, docx_path


def paths_exist(pdf_path: Path | str | None, docx_path: Path | str | None) -> bool:
    if not pdf_path or not docx_path:
        return False
    return Path(pdf_path).is_file() and Path(docx_path).is_file()
