from pathlib import Path
from uuid import UUID


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path(self, run_id: str, page_id: str) -> Path:
        # Canonical UUIDs only. No caller-controlled filenames or directory traversal.
        run = str(UUID(run_id))
        page = str(UUID(page_id))
        expected = self.root / run / f"{page}.png"
        target = expected.resolve()
        # Also reject links/junctions into another run inside the evidence root.
        if target != expected or not target.is_relative_to(self.root):
            raise ValueError("Evidencia no válida.")
        return target

    def save(self, run_id: str, page_id: str, image: bytes) -> str:
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 3_000_000:
            raise ValueError("La captura no es un PNG dentro del límite permitido.")
        target = self.path(run_id, page_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_bytes(image)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return f"{page_id}.png"

    def remove_page(self, run_id: str, page_id: str) -> None:
        self.path(run_id, page_id).unlink(missing_ok=True)

    def remove_run(self, run_id: str) -> None:
        directory = (self.root / str(UUID(run_id))).resolve()
        if not directory.is_relative_to(self.root) or directory == self.root:
            raise ValueError("Directorio de evidencia no válido.")
        if directory.is_dir():
            for path in directory.iterdir():
                # Only engine-created flat PNG/tmp files; never recurse through links.
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.suffix in {".png", ".tmp"}
                ):
                    path.unlink()
            if not any(directory.iterdir()):
                directory.rmdir()
