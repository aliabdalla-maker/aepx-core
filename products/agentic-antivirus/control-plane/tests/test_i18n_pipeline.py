"""Catalogue machine-translation pipeline (tools/i18n_translate.py) with a fake engine: ICU plurals and
{placeholders} survive, broken output is dropped (English fallback), files are labelled machine
translated, reviewed keys are kept, and the console serves the label with the messages."""
import json
import shutil
import sys

import pytest

from conftest import PRODUCT

sys.path.insert(0, str(PRODUCT / "tools"))
import i18n_translate as tr  # noqa: E402


class Fake:
    name = "fake-engine"

    def __init__(self, break_marker=False):
        self.break_marker = break_marker

    def translate(self, texts, locale):
        return [("~" + t.replace("[0]", "") if self.break_marker and "[0]" in t else f"<{locale}>{t}") for t in texts]


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    d = tmp_path / "i18n"
    d.mkdir()
    shutil.copy(PRODUCT / "shared" / "i18n" / "en.json", d / "en.json")
    monkeypatch.setattr(tr, "I18N", d)
    return d


def test_units_and_masks_round_trip():
    parts, build = tr.split_units("{n, plural, one {# threat in {files}} other {# threats in {files}}}")
    assert parts == ["# threat in {files}", "# threats in {files}"]
    masked, found = tr.mask(parts[0])
    assert masked == "[1] threat in [0]" or "[0]" in masked
    assert tr.unmask(masked, found) == parts[0]
    assert build(parts) == "{n, plural, one {# threat in {files}} other {# threats in {files}}}"


def test_locale_file_labelled_and_placeholders_validated(scratch, monkeypatch):
    monkeypatch.setattr(tr, "engine_for", lambda loc, choice, cache: Fake())
    r = tr.translate_locale("sw", "auto", {}, None)
    assert r["translated"] == r["keys_total"] and r["dropped_placeholder_mismatch"] == 0
    data = json.loads((scratch / "sw.json").read_text())
    assert data["_meta"]["origin"] == "machine:catalogue" and data["_meta"]["engine"] == "fake-engine"
    assert data["thisComputer.found"].startswith("{n, plural, one {<sw>") and "{files}" in data["thisComputer.found"]
    monkeypatch.setattr(tr, "engine_for", lambda loc, choice, cache: Fake(break_marker=True))
    r = tr.translate_locale("yo", "auto", {}, None)
    data = json.loads((scratch / "yo.json").read_text())
    assert r["dropped_placeholder_mismatch"] > 0 and "thisComputer.clean" not in data   # English fallback


def test_reviewed_keys_are_not_overwritten(scratch, monkeypatch):
    monkeypatch.setattr(tr, "engine_for", lambda loc, choice, cache: Fake())
    tr.translate_locale("de", "auto", {}, None)
    data = json.loads((scratch / "de.json").read_text())
    data["nav.security"] = "Sicherheit"
    data["_meta"]["reviewed_keys"] = ["nav.security"]
    (scratch / "de.json").write_text(json.dumps(data))
    en = json.loads((scratch / "en.json").read_text())
    en["nav.security"] = "Security centre"          # source changed after review
    (scratch / "en.json").write_text(json.dumps(en))
    tr.translate_locale("de", "auto", {}, None)
    assert json.loads((scratch / "de.json").read_text())["nav.security"] == "Sicherheit"


def test_console_serves_machine_label_for_catalogue_files(client, monkeypatch, scratch):
    from app import i18n
    monkeypatch.setattr(tr, "engine_for", lambda loc, choice, cache: Fake())
    tr.translate_locale("fr", "auto", {}, 5)
    monkeypatch.setattr(i18n, "MESSAGES_DIR", scratch)
    m = client.get("/v1/i18n/messages/fr").json()
    assert m["label"] == "machine translated, not yet reviewed" and len(m["machine_translated"]) == 5
    loc = [x for x in client.get("/v1/i18n/locales").json() if x["locale"] == "fr"][0]
    assert loc["keys_machine"] == 5 and loc["keys_reviewed"] == 0
