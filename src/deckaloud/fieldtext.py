import hashlib
import html
import re
from html.parser import HTMLParser

SOUND_TAG = re.compile(r"\[sound:[^\]]*\]")
FORMULA = re.compile(r"\[latex\]|\[\$\$?\]|\\\(|\\\[")
MEDIA_SOURCE = re.compile(r"""(?i)<(?:img|audio|object)\b[^>]*?\b(?:src|data)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))[^>]*>""")
MARKUP = re.compile(r"(?is)<!--.*?-->|<style.*?>.*?</style>|<script.*?>.*?</script>|<.*?>")
LINE_BREAKERS = frozenset({"br", "div", "p", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"})
UNSPOKEN = frozenset({"style", "script"})
SENTENCE_ENDINGS = ".!?:;,…"
LINE_BREAK = "\x00"


class SpokenParts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.unspoken_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.unspoken_depth += tag in UNSPOKEN
        self.break_line(tag)

    def handle_endtag(self, tag: str) -> None:
        self.unspoken_depth = max(0, self.unspoken_depth - (tag in UNSPOKEN))
        self.break_line(tag)

    def handle_data(self, data: str) -> None:
        if not self.unspoken_depth:
            self.parts.append(data)

    def break_line(self, tag: str) -> None:
        if tag in LINE_BREAKERS:
            self.parts.append(LINE_BREAK)


def spoken_text(field: str) -> str:
    parser = SpokenParts()
    parser.feed(SOUND_TAG.sub("", field))
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).split(LINE_BREAK)]
    return as_sentences([line for line in lines if line])


def as_sentences(lines: list[str]) -> str:
    return " ".join([*(closed(line) for line in lines[:-1]), *lines[-1:]])


def closed(line: str) -> str:
    return line if line[-1] in SENTENCE_ENDINGS else f"{line}."


def has_sound(field: str) -> bool:
    return bool(SOUND_TAG.search(field))


def has_formula(field: str) -> bool:
    return bool(FORMULA.search(field))


def sort_text(field: str) -> str:
    named = MEDIA_SOURCE.sub(lambda match: f" {next(filter(None, match.groups()), '')} ", field)
    return html.unescape(MARKUP.sub("", named))


def field_checksum(field: str) -> int:
    return int(hashlib.sha1(sort_text(field).encode("utf-8")).hexdigest()[:8], 16)
