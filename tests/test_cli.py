import zipfile
from pathlib import Path

import pytest
from conftest import copy_as_encoding

from deckaloud.cli import main

STAMPED = "deck: Geo\n\nid: a1\nQ: Capital of Ukraine?\nA: Kyiv.\n\nid: p7\nC: Kyiv lies on the {{c1::Dnipro}}.\n"
UNSTAMPED = "deck: Geo\n\nQ: Capital of Ukraine?\nA: Kyiv.\n"


@pytest.fixture
def project(tmp_path, monkeypatch, mocker, engine):
    monkeypatch.chdir(tmp_path)
    mocker.patch("deckaloud.cli.engine_named", return_value=engine)
    mocker.patch("deckaloud.cli.encode_m4a", side_effect=copy_as_encoding)
    return tmp_path


def write(project, name, text):
    path = project / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_build_writes_an_apkg_and_reports(project, capsys):
    source = write(project, "geo.txt", STAMPED)

    code = main(["build", source, "-o", "geo.apkg"])

    assert code == 0, "a clean build should exit with 0"
    assert zipfile.is_zipfile(project / "geo.apkg"), "build should write the .apkg archive"
    assert "Built 2 cards into geo.apkg, all sides baked." in capsys.readouterr().out, "build should print its report"


def test_build_refuses_unstamped_cards_and_leaves_the_source_alone(project, capsys):
    source = write(project, "geo.txt", UNSTAMPED)

    code = main(["build", source])

    assert code == 1, "unstamped cards should fail the build"
    assert "no id" in capsys.readouterr().err, "the failure should explain that ids are missing"
    assert (project / "geo.txt").read_text(encoding="utf-8") == UNSTAMPED, "build should not rewrite sources unasked"
    assert not list(project.rglob("*.apkg")), "a failed build should not write a package"


def test_build_with_stamp_writes_ids_then_builds(project):
    source = write(project, "geo.txt", UNSTAMPED)

    code = main(["build", "--stamp", source])

    assert code == 0, "build --stamp should succeed on unstamped cards"
    assert "\nid: " in (project / "geo.txt").read_text(encoding="utf-8"), "ids should be written to the source"
    assert (project / "geo.apkg").exists(), "the stamped source should be built into its package"


def numbered_source(number):
    return f"deck: Deck {number}\n\nid: card{number}\nQ: Question {number}?\nA: Answer {number}.\n"


def write_sources(project, names):
    for number, name in enumerate(names):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        write(project, name, numbered_source(number))


@pytest.mark.parametrize(
    "sources, options, expected",
    [
        (["geo.txt"], [], "geo.apkg"),
        (["notes/geo.txt"], [], "notes/geo.apkg"),
        (["geo.notes.txt"], [], "geo.notes.apkg"),
        (["geo"], [], "geo.apkg"),
        (["geo.txt", "bio.txt"], [], "deckaloud.apkg"),
        (["geo.txt"], ["-o", "named.apkg"], "named.apkg"),
        (["geo.txt", "bio.txt"], ["-o", "named.apkg"], "named.apkg"),
    ],
)
def test_build_names_the_package_after_its_only_source_unless_told_otherwise(
    project, capsys, sources, options, expected
):
    write_sources(project, sources)

    code = main(["build", *sources, *options])

    written = sorted(str(package.relative_to(project)) for package in project.rglob("*.apkg"))
    assert code == 0, f"building {sources} should succeed"
    assert written == [expected], f"building {sources} with {options} should write {expected} and nothing else"
    assert f"into {expected}" in capsys.readouterr().out, f"the report should name {expected}"


def test_rebuild_reports_cards_that_left_the_sources(project, capsys):
    source = write(project, "geo.txt", STAMPED)
    main(["build", source])
    write(project, "geo.txt", STAMPED.split("\n\nid: p7")[0] + "\n")
    capsys.readouterr()

    main(["build", source])

    assert "tag:deckaloud-p7-c1" in capsys.readouterr().out, "a card removed from the source should be reported"


def test_rebuild_reuses_cached_audio(project, engine):
    source = write(project, "geo.txt", STAMPED)
    main(["build", source])
    spoken_once = len(engine.spoken)

    main(["build", source])

    assert len(engine.spoken) == spoken_once, "an unchanged rebuild should not synthesize anything"


def test_build_honours_the_config_file(project, engine):
    write(project, "deckaloud.toml", '[languages.en]\nvoice = "Daniel"\n')

    main(["build", write(project, "geo.txt", STAMPED)])

    assert {voice for _, voice, _ in engine.spoken} == {"Daniel"}, "the configured voice should speak the cards"


def test_stamp_reports_how_many_ids_it_added(project, capsys):
    source = write(project, "geo.txt", UNSTAMPED)

    code = main(["stamp", source])

    assert code == 0, "stamp should exit with 0"
    assert "1 id added" in capsys.readouterr().out, "stamp should say how many ids it wrote"


@pytest.mark.parametrize(
    "text, code, stream, fragment",
    [
        (STAMPED, 0, "out", "2 cards"),
        (UNSTAMPED, 1, "err", "no id"),
        ("deck: Geo\n\nQ: lonely question\n", 1, "err", "geo.txt:3"),
    ],
)
def test_check_validates_without_rendering(project, capsys, engine, text, code, stream, fragment):
    result = main(["check", write(project, "geo.txt", text)])

    assert result == code, f"check should exit with {code}"
    assert fragment in getattr(capsys.readouterr(), stream), f"check should print '{fragment}' on std{stream}"
    assert engine.spoken == [], "check should never synthesize speech"


def test_sample_renders_every_voice_without_needing_ids(project, capsys):
    source = write(project, "geo.txt", UNSTAMPED)

    code = main(["sample", source, "-o", "heard"])

    assert code == 0, "sample should work on unstamped cards"
    assert (project / "heard/en/Daniel/line3-front.m4a").exists(), "samples should be written per voice"
    assert not (project / "heard/en/Bells").exists(), "effect voices should be left out by default"
    assert "4 samples" in capsys.readouterr().out, "sample should report how many files it wrote"


def test_sample_says_which_language_has_no_voice(project, capsys):
    source = write(project, "uk.txt", "lang: uk\n\nQ: Що таке TCP?\nA: Протокол.\n")
    write(project, "deckaloud.toml", '[languages.de]\nvoice = "Anna"\nlocale = "de_DE"\n')
    german = write(project, "de.txt", "Q: Was?\nA: Das.\nlang: de\n")

    main(["sample", source, german])

    output = capsys.readouterr().out
    assert "no installed voice speaks 'de'" in output, "a language without voices should be named"
    assert "Manage Voices" in output, "the message should say where voices are downloaded"
    assert "'uk'" not in output, "a language with a voice should not be reported"


def test_unsupported_engine_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "deckaloud.toml").write_text('engine = "piper"\n', encoding="utf-8")
    (tmp_path / "geo.txt").write_text(STAMPED, encoding="utf-8")

    code = main(["build", "geo.txt"])

    assert code == 1, "an unsupported engine should fail the build"
    assert "piper" in capsys.readouterr().err, "the error should name the unsupported engine"


@pytest.mark.parametrize(
    "arguments",
    [
        ["build", "absent.txt"],
        ["check", "absent.txt"],
        ["stamp", "absent.txt"],
        ["build", "geo.txt", "-o", "no/such/dir/out.apkg"],
    ],
)
def test_file_system_errors_are_reported_without_a_traceback(project, capsys, arguments):
    write(project, "geo.txt", STAMPED)

    code = main(arguments)

    assert code == 1, f"{arguments} should fail"
    assert capsys.readouterr().err.startswith("error: "), "the failure should be a one-line error"


def test_source_with_a_byte_order_mark_is_read(project):
    (project / "bom.txt").write_bytes(b"\xef\xbb\xbf" + STAMPED.encode("utf-8"))

    assert main(["check", "bom.txt"]) == 0, "a byte-order mark should not break parsing"


def write_package_bytes(project, name):
    path = project / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("collection.anki2"), b"\xff\xfe not text")
    return path


@pytest.mark.parametrize("command", ["build", "check", "sample", "stamp"])
def test_anki_package_given_as_a_source_points_to_the_voice_command(project, capsys, command):
    package = write_package_bytes(project, "deck.apkg")
    before = package.read_bytes()

    code = main([command, str(package)])

    error = capsys.readouterr().err
    assert code == 1, f"{command} should refuse an Anki package"
    assert error.startswith("error: ") and error.count("\n") == 1, "the refusal should be a one-line error"
    assert f"deckaloud voice {package}" in error, "the refusal should name the command that takes packages"
    assert package.read_bytes() == before, "the package should be left as it was"


@pytest.mark.parametrize("command", ["build", "check", "sample", "stamp"])
def test_source_that_is_not_utf8_text_is_reported_without_a_traceback(project, capsys, command):
    (project / "notes.txt").write_bytes("Q: Столиця?\nA: Київ.\n".encode("cp1251"))

    code = main([command, "notes.txt"])

    error = capsys.readouterr().err
    assert code == 1, f"{command} should refuse a file it cannot decode"
    assert error.startswith("error: notes.txt") and "UTF-8" in error, "the failure should name the file and the encoding it needs"


def test_build_without_cards_fails_and_writes_nothing(project, capsys):
    code = main(["build", write(project, "empty.txt", "deck: Empty\n")])

    assert code == 1, "building nothing should fail"
    assert "no cards" in capsys.readouterr().err, "the failure should say there were no cards"
    assert not list(project.rglob("*.apkg")), "no package should be written"


DATA = Path(__file__).parent / "data"


def test_voice_adds_sound_to_an_existing_package(project, capsys):
    code = main(["voice", str(DATA / "anki_legacy_export.apkg"), "-o", "spoken.apkg"])

    assert code == 0, "voicing a legacy export should succeed"
    assert zipfile.is_zipfile(project / "spoken.apkg"), "the voiced package should be written"
    assert "Voiced 8 fields in 5 of 6 notes into spoken.apkg." in capsys.readouterr().out, "the report should be printed"


def test_voice_names_its_output_after_the_input_by_default(project):
    source = project / "deck.apkg"
    source.write_bytes((DATA / "anki_legacy_export.apkg").read_bytes())

    main(["voice", str(source)])

    assert (project / "deck-voiced.apkg").exists(), "the default output should sit beside the input with a -voiced suffix"


@pytest.mark.parametrize(
    "arguments, fragment",
    [
        (["voice", str(DATA / "anki_modern_export.apkg")], "Support older Anki versions"),
        (["voice", "absent.apkg"], "absent.apkg"),
        (["voice", str(DATA / "anki_legacy_export.apkg"), "--lang", "de"], None),
    ],
)
def test_voice_reports_problems_plainly(project, capsys, arguments, fragment):
    code = main(arguments)

    captured = capsys.readouterr()
    if fragment is None:
        assert code == 0, "an unconfigured default language should not stop the run"
        assert "no voice configured for language 'de'" in captured.out, "the skipped fields should say why"
    else:
        assert code == 1, f"{arguments} should fail"
        assert fragment in captured.err, f"the error should mention {fragment}"
