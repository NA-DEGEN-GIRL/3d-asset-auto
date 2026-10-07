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


@pytest.mark.parametrize("kind", [stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK])
def test_archive_rejects_special_unix_files(tmp_path, kind):
    special = zipfile.ZipInfo("special")
    special.create_system = 3
    special.external_attr = (kind | 0o777) << 16
    with zipfile.ZipFile(archive_bytes([(special, b"fixture")])) as archive, pytest.raises(ValueError):
        list(helper.safe_members(archive, tmp_path))


def test_extract_preserves_executable_bits_without_privileged_permissions(tmp_path, monkeypatch):
    executable = zipfile.ZipInfo("tool")
    executable.create_system = 3
    executable.external_attr = (stat.S_IFREG | 0o6755) << 16
    archive = tmp_path / "input.zip"
    archive.write_bytes(archive_bytes([(executable, b"pinned")]).read())
    output = tmp_path / "out"
    modes = []
    monkeypatch.setattr(helper, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(Path, "chmod", lambda path, mode: modes.append(mode))
    helper.extract_verified(archive, output)
    helper.extract_verified(archive, output)
    assert len(modes) == 2  # Repair a matching installation extracted without exec bits too.
    assert all(mode & 0o111 == 0o111 and not mode & 0o7000 for mode in modes)
    assert (output / "tool").read_bytes() == b"pinned"


def installed_editor(root, *, legacy=False):
    layout = helper.editor_layout()
    base = helper.runtime_dir(root)
    for relative in layout["required"]:
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pinned " + relative.encode())
    receipt = {"version": helper.VERSION, "source_commit": helper.COMMIT,
               "files": {relative: helper.sha256(base / relative) for relative in layout["required"]}}
    if not legacy:
        receipt["platform"] = layout["platform"]
    (base / layout["receipt"]).write_text(json.dumps(receipt), encoding="utf-8")
    return layout, base


def test_doctor_accepts_legacy_windows_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    layout, base = installed_editor(tmp_path, legacy=True)
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: pytest.fail("native probe on Windows"))
    status = helper.doctor(tmp_path)
    assert status["components"]["editor"]["ready"]
    assert Path(status["editor_cli"]) == base / helper.EDITOR_DIR / "Tool/bin/Effekseer.exe"
    assert layout["receipt"] == "editor.install.json"


def test_linux_doctor_requires_own_receipt_and_native_viewer_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    _, base = installed_editor(tmp_path, legacy=True)
    windows_receipt = (base / "editor.install.json").read_bytes()
    monkeypatch.setattr(helper.sys, "platform", "linux")
    monkeypatch.setattr(helper.platform, "machine", lambda: "x86_64")
    assert not helper.doctor(tmp_path)["components"]["editor"]["ready"]
    layout, _ = installed_editor(tmp_path)
    monkeypatch.setattr(helper.os, "access", lambda *a: True)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        missing = command[-1].endswith("libViewer.so")
        return SimpleNamespace(returncode=0, stdout=b"libGLU.so.1 => not found\n" if missing else b"",
                               stderr=b"")

    monkeypatch.setattr(helper.subprocess, "run", run)
    status = helper.doctor(tmp_path)
    component = status["components"]["editor"]
    assert not component["ready"]
    assert component["receipt_hashes_match"]
    assert component["native_dependencies"][-1]["missing"] == ["libGLU.so.1"]
    assert all(command[0] == "ldd" for command in calls)
    assert len(calls) == 3
    assert Path(status["editor_cli"]) == base / layout["editor"]
    assert (base / "editor.install.json").read_bytes() == windows_receipt


def test_linux_doctor_does_not_probe_modified_binaries(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "linux")
    monkeypatch.setattr(helper.platform, "machine", lambda: "x86_64")
    layout, base = installed_editor(tmp_path)
    (base / layout["editor"]).write_bytes(b"modified")
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: pytest.fail("probe of unverified binary"))
    status = helper.doctor(tmp_path)["components"]["editor"]
    assert not status["ready"] and not status["receipt_hashes_match"]
    assert not status["native_dependencies_checked"]


def test_linux_doctor_requires_executable_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "linux")
    monkeypatch.setattr(helper.platform, "machine", lambda: "x86_64")
    layout, _ = installed_editor(tmp_path)
    monkeypatch.setattr(helper.os, "access", lambda *a: False)
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b"", stderr=b""))
    status = helper.doctor(tmp_path)["components"]["editor"]
    assert not status["ready"]
    assert status["not_executable"] == [layout["editor"], layout["converter"]]


def test_linux_install_selects_pinned_release_and_preserves_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    _, base = installed_editor(tmp_path, legacy=True)
    windows_receipt = (base / "editor.install.json").read_bytes()
    monkeypatch.setattr(helper.sys, "platform", "linux")
    monkeypatch.setattr(helper.platform, "machine", lambda: "x86_64")
    layout = helper.editor_layout()
    downloaded = []

    def download(url, destination, digest):
        downloaded.append((url, digest))
        destination.parent.mkdir(parents=True, exist_ok=True)
        entries = [(path.removeprefix("editor-linux/"), b"pinned") for path in layout["required"]]
        destination.write_bytes(archive_bytes(entries).read())

    monkeypatch.setattr(helper, "download", download)
    monkeypatch.setattr(helper.os, "access", lambda *a: True)
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b"", stderr=b""))
    assert helper.install(tmp_path, "editor")["components"]["editor"]["ready"]
    assert downloaded == [(helper.RELEASE + helper.LINUX_EDITOR[0], helper.LINUX_EDITOR[1])]
    receipt = json.loads((base / "editor-linux.install.json").read_text())
    assert receipt["platform"] == "linux-x86_64"
    assert set(receipt["files"]) == set(layout["required"])
    assert (base / "editor.install.json").read_bytes() == windows_receipt


@pytest.mark.parametrize("host,architecture", [("linux", "aarch64"), ("darwin", "x86_64")])
def test_unsupported_editor_host_keeps_webgl_available(tmp_path, monkeypatch, host, architecture):
    monkeypatch.setattr(helper.sys, "platform", host)
    monkeypatch.setattr(helper.platform, "machine", lambda: architecture)
    monkeypatch.setattr(helper, "download", lambda *a: pytest.fail("unsupported editor download"))
    with pytest.raises(ValueError, match="Linux x86_64"):
        helper.install(tmp_path, "editor")
    status = helper.doctor(tmp_path)
    assert not status["components"]["editor"]["supported"]
    assert "webgl" in status["components"]
    assert status["editor_cli"] is None


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


@pytest.mark.parametrize("model", [False, True])
def test_linux_conversions_use_native_paths_and_cpu_policy(mock_export, monkeypatch, model):
    source, output = mock_export
    monkeypatch.setattr(helper.sys, "platform", "linux")
    monkeypatch.setattr(helper.platform, "machine", lambda: "x86_64")
    layout = helper.editor_layout()
    base = helper.runtime_dir(source.parent)
    monkeypatch.setattr(helper, "doctor", lambda root: {
        "components": {"editor": {"ready": True}}, "editor_cli": str(base / layout["editor"]),
        "model_converter": str(base / layout["converter"])})
    if model:
        source = source.with_suffix(".obj")
        source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        output = output.with_suffix(".efkmodel")

    def run(command, **kwargs):
        expected = "converter" if model else "editor"
        assert command[0] == str(base / layout[expected])
        assert ("-cui" in command) is not model
        assert kwargs["cwd"] == base / layout["directory"] / "Tool"
        assert kwargs["env"]["OMP_NUM_THREADS"] == "3"
        assert kwargs["creationflags"] == 0
        output.write_bytes(struct.pack("<ifiiii", 6, 1.0, 1, 1, 3, 0) if model else effect_container())
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(helper.subprocess, "run", run)
    assert helper.export(source.parent, source, output, model_scale=1.0 if model else None)["state"] == "completed"
    receipt = json.loads(output.with_suffix(output.suffix + ".provenance.json").read_text())
    assert receipt["platform"] == "linux-x86_64"
    assert not receipt["rendered"]


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
