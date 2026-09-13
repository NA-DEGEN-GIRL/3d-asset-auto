import struct
import subprocess
from pathlib import Path

import pytest

from asset_auto import local_rig
from asset_auto.store import read_json, write_json


def install_stub(root):
    for relative in (".runtime/local-rig/.venv/pyvenv.cfg", ".runtime/local-rig/.venv/bin/python",
                     ".runtime/local-rig/python/cpython-test/bin/python3.11",
                     ".runtime/local-rig/source/demo.py", ".runtime/local-rig/source/src/model/tokenrig.py",
                     "scripts/local_rig/run.py", "scripts/local_rig/helper.py"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-runtime")
    metadata = {
        "ready": True, "backend": "skintokens", "platform": "linux",
        "source_revision": "pinned-code", "model_revision": "pinned-weights",
        "checkpoints": [], "patches": [],
    }
    write_json(root / ".runtime/installed/local-rig.json", metadata)
    return metadata


def test_uninstalled_local_rig_does_not_select_remote(tmp_path):
    result = local_rig.capability(tmp_path)
    assert result["available"] is False
    assert result["backend"] == "skintokens"
    assert "bootstrap_local_rig.py" in result["reason"]


def test_wsl_arguments_preserve_hash_and_spaces(tmp_path, monkeypatch):
    root = tmp_path / "# asset workspace"
    installed = {"platform": "wsl", "wsl_distribution": "Ubuntu-24.04"}
    monkeypatch.setattr(local_rig, "wsl_path", lambda path, distro: "/mnt/d/" + path.name)
    command = local_rig.command(root, root / "result space", root / "mesh #one.glb", installed)
    assert command[:4] == ["wsl", "--distribution", "Ubuntu-24.04", "--exec"]
    assert command[command.index("--input") + 1] == "/mnt/d/mesh #one.glb"
    assert "--num-beams" in command
    assert not any(value in command for value in ("sh", "bash", "-c"))


def test_changed_checkpoint_blocks_inference_before_process(tmp_path, monkeypatch):
    metadata = install_stub(tmp_path)
    path = tmp_path / ".runtime/local-rig/source/weights.ckpt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unexpected")
    metadata["checkpoints"] = [{"path": "weights.ckpt", "sha256": "trusted-hash"}]
    write_json(tmp_path / ".runtime/installed/local-rig.json", metadata)
    source = tmp_path / "source.glb"
    source.write_bytes(b"source")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must not launch"))
    with pytest.raises(RuntimeError, match="checkpoint changed"):
        local_rig.generate(tmp_path, None, tmp_path / "out", source)


def test_success_tracks_exact_source_and_output_without_network(tmp_path, monkeypatch):
    install_stub(tmp_path)
    source = tmp_path / "source.glb"
    source.write_bytes(b"immutable source")
    out = tmp_path / "out"

    def run(command, **kwargs):
        target = Path(command[command.index("--output") + 1])
        target.write_bytes(struct.pack("<4sII", b"glTF", 2, 12))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    result = local_rig.generate(tmp_path, None, out, source)
    assert result["state"] == "completed"
    assert result["credits_consumed"] == 0
    assert result["source_sha256"] == local_rig.sha256(source)
    assert result["output_sha256"] == local_rig.sha256(out / "generated.glb")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must reuse known output"))
    assert local_rig.generate(tmp_path, None, out, source) == result
    (tmp_path / "scripts/local_rig/run.py").write_bytes(b"different runtime")
    with pytest.raises(RuntimeError, match="different patched runtime"):
        local_rig.generate(tmp_path, None, out, source)


def test_parent_interruption_adopts_bound_child_receipt(tmp_path, monkeypatch):
    install_stub(tmp_path)
    source = tmp_path / "source.glb"
    source.write_bytes(b"source")
    out = tmp_path / "out"

    def completed_child(command, **kwargs):
        target = Path(command[command.index("--output") + 1])
        target.write_bytes(struct.pack("<4sII", b"glTF", 2, 12))
        receipt = read_json(out / "local-rig.json")
        receipt.update(state="completed", output_sha256=local_rig.sha256(target),
                       completed_at=receipt["started_at"])
        write_json(out / "local-rig-child.json", receipt)
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", completed_child)
    with pytest.raises(KeyboardInterrupt):
        local_rig.generate(tmp_path, None, out, source)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("do not regenerate"))
    result = local_rig.generate(tmp_path, None, out, source)
    assert result["state"] == "completed"
    assert result["output_sha256"] == local_rig.sha256(out / "generated.glb")
    source.write_bytes(b"different source")
    with pytest.raises(RuntimeError, match="another source"):
        local_rig.generate(tmp_path, None, out, source)


def test_exported_partial_is_adopted_after_worker_exits(tmp_path, monkeypatch):
    install_stub(tmp_path)
    source = tmp_path / "source.glb"
    source.write_bytes(b"source")
    out = tmp_path / "out"

    def interrupted_export(command, **kwargs):
        receipt = read_json(out / "local-rig.json")
        partial = out / f"generated-{receipt['run_id']}.partial.glb"
        partial.write_bytes(struct.pack("<4sII", b"glTF", 2, 12))
        receipt.update(state="exported", output_sha256=local_rig.sha256(partial),
                       completed_at=receipt["started_at"])
        write_json(out / "local-rig-child.json", receipt)
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupted_export)
    with pytest.raises(KeyboardInterrupt):
        local_rig.generate(tmp_path, None, out, source)
    monkeypatch.setattr(local_rig, "child_is_running", lambda *args: True)
    with pytest.raises(RuntimeError, match="finalizing"):
        local_rig.generate(tmp_path, None, out, source)
    monkeypatch.setattr(local_rig, "child_is_running", lambda *args: False)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("do not regenerate"))
    result = local_rig.generate(tmp_path, None, out, source)
    assert result["state"] == "completed"
    assert (out / "generated.glb").is_file()
    assert not list(out.glob("*.partial.glb"))


def test_capability_rejects_missing_runtime_files(tmp_path):
    install_stub(tmp_path)
    assert local_rig.capability(tmp_path)["available"]
    (tmp_path / ".runtime/local-rig/.venv/pyvenv.cfg").unlink()
    assert not local_rig.capability(tmp_path)["available"]


def test_capability_rejects_incomplete_checkpoint(tmp_path):
    metadata = install_stub(tmp_path)
    path = tmp_path / ".runtime/local-rig/source/weights.ckpt"
    path.write_bytes(b"partial")
    metadata["checkpoints"] = [{"path": "weights.ckpt", "size_bytes": 1000}]
    write_json(tmp_path / ".runtime/installed/local-rig.json", metadata)
    assert not local_rig.capability(tmp_path)["available"]


def test_recent_unknown_worker_is_not_duplicated(tmp_path, monkeypatch):
    install_stub(tmp_path)
    source = tmp_path / "source.glb"
    source.write_bytes(b"source")

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        local_rig.generate(tmp_path, None, tmp_path / "out", source)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("do not duplicate active worker"))
    with pytest.raises(RuntimeError, match="active or reconciling"):
        local_rig.generate(tmp_path, None, tmp_path / "out", source)


def test_timeout_records_failed_state(tmp_path, monkeypatch):
    install_stub(tmp_path)
    source = tmp_path / "source.glb"
    source.write_bytes(b"source")

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1850)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        local_rig.generate(tmp_path, None, tmp_path / "out", source)
    assert read_json(tmp_path / "out/local-rig.json")["state"] == "failed"
