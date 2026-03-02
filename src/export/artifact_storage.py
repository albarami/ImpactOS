"""Export artifact storage — persists generated export bytes to filesystem.

Stores artifacts under OBJECT_STORAGE_PATH/exports/{export_id}/{format}.ext.
Retrieval returns raw bytes by storage key.
"""

from pathlib import Path

_FORMAT_EXTENSIONS: dict[str, str] = {
    "excel": "xlsx",
    "pptx": "pptx",
}


class ExportArtifactStorage:
    """Filesystem-backed export artifact storage."""

    def __init__(self, storage_root: str) -> None:
        self._root = Path(storage_root)

    def store(self, key: str, data: bytes) -> None:
        """Write artifact bytes to the given storage key."""
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def retrieve(self, key: str) -> bytes:
        """Read artifact bytes by storage key.

        Raises:
            FileNotFoundError: If the key does not exist.
        """
        path = self._root / key
        if not path.exists():
            msg = f"Export artifact not found: {key}"
            raise FileNotFoundError(msg)
        return path.read_bytes()

    @staticmethod
    def build_key(export_id: str, fmt: str) -> str:
        """Build a canonical storage key for an export artifact."""
        ext = _FORMAT_EXTENSIONS.get(fmt, fmt)
        return f"exports/{export_id}/{fmt}.{ext}"
