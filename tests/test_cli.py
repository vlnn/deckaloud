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
    assert not (project / "deckaloud.apkg").exists(), "a failed build should not write a package"


def test_build_with_stamp_writes_ids_then_builds(project):
    source = write(project, "geo.txt", UNSTAMPED)

    code = main(["build", "--stamp", source])

    assert code == 0, "build --stamp should succeed on unstamped cards"
    assert "\nid: " in (project / "geo.txt").read_text(encoding="utf-8"), "ids should be written to the source"
    assert (project / "deckaloud.apkg").exists(), "the default output name should be deckaloud.apkg"


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


def test_build_without_cards_fails_and_writes_nothing(project, capsys):
    code = main(["build", write(project, "empty.txt", "deck: Empty\n")])

    assert code == 1, "building nothing should fail"
    assert "no cards" in capsys.readouterr().err, "the failure should say there were no cards"
    assert not Path("deckaloud.apkg").exists(), "no package should be written"
