#!/usr/bin/env python3
"""Project-local Debian container, with its writable /usr and /var in build/."""
import argparse
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "debian@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a"
NAME = "kasli-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
PACKAGES = ("build-essential patch perl python3 python3-venv python3-pip bison flex "
            "bc cpio unzip rsync file wget xz-utils libssl-dev libncurses-dev git "
            "ca-certificates libelf-dev clang llvm device-tree-compiler rustup "
            "openssh-client curl").split()


def call(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare():
    state = ROOT / "build/environment"
    state.mkdir(parents=True, exist_ok=True)
    filesystem = state / "rootfs"
    if not filesystem.exists():
        call(["docker", "pull", IMAGE])
        cid = subprocess.check_output(["docker", "create", IMAGE], text=True).strip()
        filesystem.mkdir()
        try:
            export = subprocess.Popen(["docker", "export", cid], stdout=subprocess.PIPE)
            call(["tar", "-xf", "-", "-C", str(filesystem)], stdin=export.stdout)
            export.stdout.close()
            if export.wait():
                raise RuntimeError("container export failed")
        finally:
            call(["docker", "rm", cid])
    active = subprocess.run(["docker", "inspect", NAME], capture_output=True).returncode == 0
    if not active:
        cmd = ["docker", "run", "-d", "--name", NAME, "--workdir", "/work"]
        for name in ("usr", "etc", "var"):
            cmd += ["--mount", f"type=bind,src={filesystem/name},dst=/{name}"]
        cmd += ["--mount", f"type=bind,src={ROOT},dst=/work", IMAGE,
                "tail", "-f", "/dev/null"]
        call(cmd)
    else:
        call(["docker", "start", NAME], stdout=subprocess.DEVNULL)
    if not (state / "ready").exists():
        # A dated immutable Debian snapshot avoids unrecorded moving package versions.
        sources = filesystem / "etc/apt/sources.list.d/debian.sources"
        sources.write_text("Types: deb\nURIs: http://snapshot.debian.org/archive/debian/20261005T000000Z/\n"
                           "Suites: trixie\nComponents: main\nCheck-Valid-Until: no\n"
                           "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n")
        call(["docker", "exec", NAME, "apt-get", "update"])
        call(["docker", "exec", "-e", "DEBIAN_FRONTEND=noninteractive", NAME,
              "apt-get", "install", "-y", "--no-install-recommends", *PACKAGES])
        with (state / "packages.txt").open("w") as f:
            call(["docker", "exec", NAME, "dpkg-query", "-W"], stdout=f)
        (state / "ready").write_text(IMAGE + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs=argparse.REMAINDER, default=[])
    args = p.parse_args()
    prepare()
    if args.command:
        call(["docker", "exec", "-w", "/work", "-e", "CARGO_HOME=/work/build/cargo",
              "-e", "RUSTUP_HOME=/work/build/rustup", NAME, *args.command])


if __name__ == "__main__":
    main()
