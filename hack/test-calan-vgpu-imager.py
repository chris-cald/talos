# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Offline public make-target contract for pre-GPU and final installers."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
make = shutil.which("gmake") or shutil.which("make")
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    result = base / "result.json"
    result.write_text(json.dumps({"kernel_image": "fixture-kernel", "extension_image": "fixture-grid"}))
    prefix = "registry.example.invalid/test"
    inputs = ["MAKE=echo", "PUSH=true", "PLATFORM=linux/amd64", "REGISTRY_AND_USERNAME=" + prefix,
              "IMAGE_NAME_SUFFIX=-check", "IMAGE_TAG_IN=fixture", "IMAGE_TAG_OUT=fixture",
              "BUILD_RESULT_PATH=" + str(result), "VGPU_EXTENSION_IMAGE=fixture-grid",
              "QEMU_GUEST_AGENT_EXTENSION_IMAGE=fixture-qemu", "NVIDIA_CONTAINER_TOOLKIT_EXTENSION_IMAGE=fixture-toolkit"]
    plan = subprocess.run([make, "--no-print-directory", "-f", "Makefile.calan-vgpu", "--dry-run", "vgpu-imager", *inputs], cwd=root, capture_output=True, text=True, check=True)
    commands = [shlex.split(line) for line in plan.stdout.splitlines() if line.startswith(("echo ", "python3 -c "))]
    profiles = [args for args in commands if args[0] == "echo" and "installer" in args]
    assert len(profiles) == 2, "need distinct pre-GPU and final installer profiles"
    bootstrap = next(args for args in profiles if "IMAGE_TAG_OUT=fixture-bootstrap" in args)
    final = next(args for args in profiles if args != bootstrap)
    for args in profiles:
        flags = next(value for value in args if value.startswith("IMAGER_ARGS="))
        assert "--system-extension-image fixture-grid" in flags
        assert "--system-extension-image fixture-qemu" in flags
        assert "console=tty0" in flags and "console=ttyS0,115200" in flags
    assert "fixture-toolkit" not in " ".join(bootstrap)
    assert "--system-extension-image fixture-toolkit" in " ".join(final)
    crane = base / "crane"
    crane.write_text("#!" + sys.executable + "\nimport sys\nprint('sha256:' + ('2' if sys.argv[-1].endswith('-bootstrap') else '1') * 64)\n")
    crane.chmod(0o700)
    receipt = next(args for args in commands if args[:2] == ["python3", "-c"])
    env = {**os.environ, "BUILD_RESULT_PATH": str(result), "PATH": str(base) + os.pathsep + os.environ["PATH"]}
    subprocess.run([sys.executable, *receipt[1:]], env=env, check=True, capture_output=True, text=True)
    output = json.loads(result.read_text())
    assert output["installer_image"] == prefix + "/installer-check:fixture@sha256:" + "1" * 64
    assert output["bootstrap_installer_image"] == prefix + "/installer-check:fixture-bootstrap@sha256:" + "2" * 64
    assert output["kernel_image"] == "fixture-kernel" and output["extension_image"] == "fixture-grid"
    assert set(output["build_contract"]["bootstrap_required_extensions"]) == {"siderolabs/qemu-guest-agent", "grid-kmod-nvidia"}
print("Native bootstrap and final installer profile checks passed")
