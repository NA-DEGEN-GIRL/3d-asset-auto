"""Run the Linux Blender RPC helper only while its inference parent is alive."""

from __future__ import annotations

import argparse
import ctypes
import os
import signal
import sys
from pathlib import Path


def bind_parent_lifetime(parent_pid):
    """Arm kernel termination before importing any upstream or GPU modules."""
    if sys.platform != "linux":
        raise RuntimeError("The local rig Blender helper requires Linux")
    if parent_pid <= 1:
        raise ValueError("Expected a live inference parent PID greater than one")
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
    libc.prctl.restype = ctypes.c_int
    # PR_SET_PDEATHSIG: the kernel signals this process when its parent dies.
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    # If the parent exited before prctl, the death event has already passed.
    if os.getppid() != parent_pid:
        raise RuntimeError("Inference parent exited or changed before Blender helper startup")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    bind_parent_lifetime(args.parent_pid)
    source_root = args.source_root.resolve()
    os.chdir(source_root)
    sys.path.insert(0, str(source_root))
    from src.server.bpy_server import run

    run()


if __name__ == "__main__":
    main()
