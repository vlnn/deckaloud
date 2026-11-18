import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from deckaloud.errors import PackageError

NEWER_FORMAT = "collection.anki21b"
COLLECTIONS = ("collection.anki21", "collection.anki2")
MEDIA_MAP = "media"
EXPORT_HINT = "export it again from Anki with 'Support older Anki versions' ticked"


@dataclass(frozen=True)
class OpenedPackage:
    source: Path
    collection_name: str
    database: Path
    media: dict[str, str]


def open_package(source: Path, workdir: Path) -> OpenedPackage:
    try:
        with zipfile.ZipFile(source) as archive:
            name = collection_name(set(archive.namelist()), source)
            archive.extract(name, workdir)
            return OpenedPackage(source, name, workdir / name, media_map(archive))
    except zipfile.BadZipFile:
        raise PackageError(f"{source} is not an Anki package") from None


def collection_name(names: set[str], source: Path) -> str:
    if NEWER_FORMAT in names:
        raise PackageError(f"{source} uses Anki's newer package format; {EXPORT_HINT}")
    found = [name for name in COLLECTIONS if name in names]
    if not found:
        raise PackageError(f"{source} is not an Anki package")
    return found[0]


def media_map(archive: zipfile.ZipFile) -> dict[str, str]:
    return json.loads(archive.read(MEDIA_MAP)) if MEDIA_MAP in archive.namelist() else {}


def save_package(package: OpenedPackage, clips: tuple[Path, ...], output: Path) -> None:
    added = numbered(new_clips(package.media, clips), first=next_index(package.media))
    replaced = {package.collection_name, MEDIA_MAP}
    with zipfile.ZipFile(package.source) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as result:
        for item in original.infolist():
            if item.filename not in replaced:
                result.writestr(item, original.read(item.filename))
        result.write(package.database, package.collection_name)
        for index, clip in added.items():
            result.write(clip, index)
        names = {index: clip.name for index, clip in added.items()}
        result.writestr(MEDIA_MAP, json.dumps({**package.media, **names}))


def new_clips(media: dict[str, str], clips: tuple[Path, ...]) -> list[Path]:
    known = set(media.values())
    return [clip for clip in dict.fromkeys(clips) if clip.name not in known]


def next_index(media: dict[str, str]) -> int:
    return max((int(index) for index in media), default=-1) + 1


def numbered(clips: list[Path], first: int) -> dict[str, Path]:
    return {str(index): clip for index, clip in enumerate(clips, start=first)}
