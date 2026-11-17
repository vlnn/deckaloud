from pathlib import Path


class DeckaloudError(Exception):
    pass


class ParseError(DeckaloudError):
    def __init__(self, path: Path, line: int, message: str):
        super().__init__(f"{path}:{line}: {message}")


class ConfigError(DeckaloudError):
    pass


class SpeechError(DeckaloudError):
    pass


class PackageError(DeckaloudError):
    pass
