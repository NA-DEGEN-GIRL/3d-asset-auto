"""No network, editor, graphics context or paid calls in routine helper tests."""

import importlib.util
import io
import json
import stat
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/effekseer.py"
SPEC = importlib.util.spec_from_file_location("effekseer_helper", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def archive_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in entries:
            archive.writestr(name, value)
    stream.seek(0)
    return stream


@pytest.mark.parametrize("name", ["../bad", "/absolute", "C:/escape", "dir\\..\\bad", "dir./bad"])
def test_archive_rejects_paths_before_any_extraction(tmp_path, name):
    archive = tmp_path / "input.zip"
    archive.write_bytes(archive_bytes([("ok.txt", b"ok"), (name, b"bad")]).read())
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Unsafe archive"):
        helper.extract_verified(archive, output)
    assert not output.exists()


def test_archive_rejects_symlink_and_case_alias(tmp_path):
    link = zipfile.ZipInfo("link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for entries in [[(link, b"../other")], [("FILE", b"1"), ("file", b"2")]]:
        with zipfile.ZipFile(archive_bytes(entries)) as archive, pytest.raises(ValueError):
            list(helper.safe_members(archive, tmp_path))


def test_extract_reuses_identical_and_preserves_modified_files(tmp_path):
    archive = tmp_path / "input.zip"
    archive.write_bytes(archive_bytes([("dir/asset", b"pinned")]).read())
    output = tmp_path / "out"
    helper.extract_verified(archive, output)
    helper.extract_verified(archive, output)
    (output / "dir/asset").write_bytes(b"local modification")
    with pytest.raises(ValueError, match="differs"):
        helper.extract_verified(archive, output)
    assert (output / "dir/asset").read_bytes() == b"local modification"


def test_download_rejects_corrupt_cache_without_network(tmp_path, monkeypatch):
    cached = tmp_path / "archive.zip"
    cached.write_bytes(b"wrong")
    monkeypatch.setattr(helper.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network requested"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        helper.download("https://example.invalid/file", cached, "0" * 64)
    assert cached.read_bytes() == b"wrong"


def effect_container(paths=()):
    data = b"EFKE" + struct.pack("<I", 0)
    info = struct.pack("<ii", 1810, len(paths))
    for path in paths:
        encoded = (path + "\0").encode("utf-16le")
        info += struct.pack("<iii", 1, 1, len(encoded) // 2) + encoded
    for name, value in [(b"INFO", info), (b"EDIT", b"fixture"), (b"BIN_", b"SKFE12345678")]:
        data += name + struct.pack("<I", len(value)) + value
    return data


def test_output_validation_requires_complete_source_and_runtime(tmp_path):
    path = tmp_path / "effect.efkefc"
    for data in [b"not an effect", effect_container()[:-1], effect_container()[:23]]:
        path.write_bytes(data)
        with pytest.raises(ValueError):
            helper.validate_output(path)
    path.write_bytes(effect_container())
    helper.validate_output(path)


@pytest.fixture
def mock_export(tmp_path, monkeypatch):
    from asset_auto import resources

    monkeypatch.setattr(helper.sys, "platform", "win32")
    monkeypatch.setattr(helper, "doctor", lambda root: {
        "components": {"editor": {"ready": True}}, "editor_cli": "Effekseer.exe",
        "model_converter": "EffekseerResourceConverter.exe"})
    monkeypatch.setattr(resources, "resolve", lambda root: {"effective": {"gpu": "cpu", "threads": 3}})
    monkeypatch.setattr(resources, "apply_process_resources", lambda root, **kwargs: {"enforcement": {}})
    source = tmp_path / "input.efkproj"
    source.write_text("<EffekseerProject><Root /></EffekseerProject>")
    return source, tmp_path / "out.efkefc"


def test_export_validates_output_despite_success_exit(mock_export, monkeypatch):
    source, output = mock_export
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b"", stderr=b"load failed"))
    with pytest.raises(ValueError, match="without creating output"):
        helper.export(source.parent, source, output)
    report = json.loads(output.with_suffix(".efkefc.provenance.json").read_text())
    assert report["state"] == "failed"
    assert not report["rendered"]


def test_export_applies_threads_and_never_gui_or_material_cache(mock_export, monkeypatch):
    source, output = mock_export

    def run(command, **kwargs):
        assert "-cui" in command and "-o" in command
        assert "--materialcache" not in command
        assert kwargs["env"]["OMP_NUM_THREADS"] == "3"
        output.write_bytes(effect_container())
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(helper.subprocess, "run", run)
    result = helper.export(source.parent, source, output)
    assert result["state"] == "completed"
    assert not result["rendered"]
    with pytest.raises(ValueError, match="already exists"):
        helper.export(source.parent, source, output)


def test_model_conversion_checks_header_and_preserves_cpu_contract(mock_export, monkeypatch):
    source, _ = mock_export
    source = source.with_suffix(".obj")
    source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    output = source.with_suffix(".efkmodel")

    def run(command, **kwargs):
        assert command[0] == "EffekseerResourceConverter.exe"
        assert command[-2:] == ["-s", "2.0"]
        assert kwargs["env"]["OMP_NUM_THREADS"] == "3"
        output.write_bytes(struct.pack("<ifiiii", 6, 1.0, 1, 1, 3, 0))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(helper.subprocess, "run", run)
    result = helper.export(source.parent, source, output, model_scale=2.0)
    assert result["state"] == "completed"
    report = json.loads(output.with_suffix(".efkmodel.provenance.json").read_text())
    assert report["operation"] == "model_conversion"
    assert not report["rendered"]


def test_model_header_does_not_accept_empty_or_wrong_version(tmp_path):
    output = tmp_path / "model.efkmodel"
    for data in (b"", struct.pack("<ifiiii", 999, 1.0, 1, 1, 3, 0)):
        output.write_bytes(data)
        with pytest.raises(ValueError):
            helper.validate_output(output)


def test_export_detects_missing_dependencies_despite_valid_effect(mock_export, monkeypatch):
    source, output = mock_export

    def run(command, **kwargs):
        output.write_bytes(effect_container(["Texture/missing.png"]))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(helper.subprocess, "run", run)
    with pytest.raises(ValueError, match="missing dependencies"):
        helper.export(source.parent, source, output)
    report = json.loads(output.with_suffix(".efkefc.provenance.json").read_text())
    assert report["state"] == "failed"
    assert report["dependencies"][0]["path"] == "Texture/missing.png"


def test_dependency_inventory_hashes_existing_resources(tmp_path):
    texture = tmp_path / "Texture/texture.png"
    texture.parent.mkdir()
    texture.write_bytes(b"fixture")
    effect = tmp_path / "effect.efkefc"
    effect.write_bytes(effect_container(["Texture/texture.png"]))
    inventory = helper.dependencies(effect)
    assert inventory[0]["exists"]
    assert inventory[0]["sha256"] == helper.sha256(texture)
