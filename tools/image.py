#!/usr/bin/env python3
"""Stages for make image; run inside the project-local Debian environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
TOOLS = BUILD / "tools"
SHARED = BUILD
BOARD = "kasli-soc"
ASSETS = [(name, entry["url"], entry["sha256"])
          for name, entry in json.loads((ROOT / "toolchains.lock.json").read_text()).items()]


def run(args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def bootstrap():
    run(["python3", ROOT / "tools/fetch_sources.py"])
    TOOLS.mkdir(parents=True, exist_ok=True)
    downloads = SHARED / "downloads"
    downloads.mkdir(exist_ok=True)
    for name, url, expected in ASSETS:
        marker = TOOLS / name / ".sha256"
        if marker.exists() and marker.read_text().strip() == expected:
            continue
        archive = downloads / url.rsplit("/", 1)[1]
        if not archive.exists():
            temporary = archive.with_suffix(".part")
            urllib.request.urlretrieve(url, temporary)
            temporary.rename(archive)
        with archive.open("rb") as f:
            actual = hashlib.file_digest(f, "sha256").hexdigest()
        if actual != expected:
            raise RuntimeError("SHA-256 mismatch: " + str(archive))
        dest = TOOLS / name if name == "openxc7" else TOOLS
        dest.mkdir(exist_ok=True)
        with tarfile.open(archive) as tf:
            tf.extractall(dest, filter="data")
        marker.write_text(expected + "\n")
    python = SHARED / "python/bin/python"
    if not python.exists():
        run(["python3", "-m", "venv", SHARED / "python"])
    run([python, "-m", "pip", "install", "-r", ROOT / "requirements.lock"])
    run([python, "-m", "pip", "install", "--no-deps",
         ROOT / "upstream/migen", ROOT / "upstream/litex",
         ROOT / "upstream/litex-boards", ROOT / "upstream/litedram",
         ROOT / "upstream/liteiclink", ROOT / "upstream/liteeth"])
    if BOARD == "kasli-soc":
        run(["rustup", "toolchain", "install", "nightly-2026-03-25",
             "--profile", "minimal", "--component", "rust-src"])
    keys = SHARED / "ssh"
    keys.mkdir(exist_ok=True)
    if not (keys / "id_ed25519").exists():
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", keys / "id_ed25519"])


def pl():
    run([SHARED / "python/bin/python", ROOT / "tools/build_pl.py",
         "--board", BOARD, "--output-dir", BUILD / "gateware",
         "--openxc7", TOOLS / "openxc7", "--yosys", TOOLS / "oss-cad-suite/bin/yosys"])


def szl():
    source = BUILD / "szl-source"
    if not (source / ".kasli-patched").exists():
        if source.exists():
            raise RuntimeError("unmarked SZL build tree exists; inspect before rebuilding")
        shutil.copytree(ROOT / "upstream/zynq-rs", source, ignore=shutil.ignore_patterns(".git", "target"))
        subprocess.run(["patch", "-p1"], cwd=source, check=True,
                       input=(ROOT / "patches/szl-fclk0.patch").read_bytes())
        (source / ".kasli-patched").write_text("FCLK0 100MHz\n")
    env = dict(os.environ, CARGO_TARGET_DIR=str(BUILD / "szl"))
    subprocess.run(["rustup", "run", "nightly-2026-03-25", "cargo", "build", "--locked",
                    "--release", "-p", "szl", "--no-default-features", "--features", "target_zc706" if BOARD == "zc706" else "target_kasli_soc"],
                   cwd=source, env=env, check=True)


def test():
    work = BUILD / "gateware/gateware"
    suite = TOOLS / "oss-cad-suite"
    subprocess.run([suite / "bin/yosys", "-Q", "-T", "-p",
                    "read_json top.json; write_verilog -noattr top_sim.v"], cwd=work, check=True)
    subprocess.run([suite / "bin/iverilog", "-g2012", "-s", "tb", "-o", BUILD / "axi-test.vvp",
                    ROOT / "tests/axi_csr_tb.v", work / "top_sim.v",
                    suite / "share/yosys/xilinx/cells_sim.v",
                    suite / "share/yosys/xilinx/cells_xtra.v"], cwd=work, check=True)
    with (BUILD / "axi-test.log").open("w") as log:
        subprocess.run([suite / "bin/vvp", BUILD / "axi-test.vvp"], cwd=work,
                       stdout=log, stderr=subprocess.STDOUT, timeout=30, check=True)
    print((BUILD / "axi-test.log").read_text(), flush=True)


def linux():
    output = BUILD / "buildroot"
    command = ["make", "-C", ROOT / "upstream/buildroot", f"O={output}",
               f"BR2_EXTERNAL={ROOT / 'buildroot'}", "BR2_WGET=wget --timeout=30",
               "BR2_PRIMARY_SITE=https://sources.buildroot.net"]
    run(command + ["zc706_defconfig" if BOARD == "zc706" else "kasli_soc_defconfig"])
    run(command + ["-j4"])


def boot():
    packer = BUILD / "mkbootimage"
    if not packer.exists():
        shutil.copytree(ROOT / "upstream/mkbootimage", packer, ignore=shutil.ignore_patterns("*.o", "mkbootimage", "exbootimage"))
    run(["make", "-C", packer, "-j4"])
    images = BUILD / "buildroot/images"
    bif = BUILD / "boot.bif"
    if BOARD == "zc706":
        # Use upstream ZC706 ps7_init (533 MHz DDR), not SZL's 667 MHz preset.
        # BootROM loads SPL from BOOT.BIN; SPL reads u-boot.img from FAT.
        bif.write_text("image: {\n    [bootloader, load=0x00000000] "
                       + str(images / "u-boot-spl.bin") + "\n}\n")
        run([packer / "mkbootimage", bif, images / "BOOT.BIN"])
        run(["python3", ROOT / "tools/check_boot_image.py", images / "BOOT.BIN",
             "--spl", images / "u-boot-spl.bin"])
        shutil.copyfile(BUILD / "gateware/gateware/top.bit", images / "top.bit")
        run([BUILD / "buildroot/host/bin/mkimage", "-A", "arm", "-T", "script",
             "-C", "none", "-n", "ZC706 Linux openXC7", "-d",
             ROOT / "buildroot/board/zc706/boot.cmd", images / "boot.scr"])
        return
    # SZL discovers PL and PS payload headers, skips its own bootloader header.
    # U-Boot's configured text base matches SZL's fixed DDR payload address.
    bif.write_text("image: {\n    [bootloader] " + str(BUILD / "szl/armv7-none-eabihf/release/szl")
                   + "\n    " + str(BUILD / "gateware/gateware/top.bit")
                   + "\n    [load=0x00100000] " + str(images / "u-boot.bin") + "\n}\n")
    run([packer / "mkbootimage", bif, images / "BOOT.BIN"])
    run(["python3", ROOT / "tools/check_boot_image.py", images / "BOOT.BIN",
         "--uboot", images / "u-boot.bin"])


def image():
    boot()
    images = BUILD / "buildroot/images"
    board = ROOT / "buildroot/board" / BOARD
    shutil.copyfile(board / "extlinux.conf", images / "extlinux.conf")
    # genimage must not copy the rootfs again: rootfs.ext4 is already built.
    temp = BUILD / "genimage"
    if temp.exists():
        shutil.rmtree(temp)
    run([BUILD / "buildroot/host/bin/genimage", "--rootpath", BUILD / "buildroot/target",
         "--tmppath", temp, "--inputpath", images, "--outputpath", images,
         "--config", board / "genimage.cfg"],
        env=dict(os.environ, PATH=str(BUILD / "buildroot/host/bin") + ":"
                 + str(BUILD / "buildroot/host/sbin") + ":" + os.environ["PATH"]))
    run(["python3", ROOT / "tools/check_sd_image.py", images / "sdcard.img"])
    with (images / "sdcard.img.gz").open("wb") as archive:
        run(["gzip", "-n", "-c", images / "sdcard.img"], stdout=archive)
    manifest = {"board": BOARD, "hardware_validated": False, "milestone_1_complete": False,
                "files": {}}
    names = ["BOOT.BIN", "zImage", f"{BOARD}.dtb", "rootfs.ext4", "sdcard.img", "sdcard.img.gz"]
    if BOARD == "zc706":
        names += ["u-boot-spl.bin", "u-boot.img", "boot.scr", "top.bit", "rootfs.cpio.gz"]
    for name in names:
        path = images / name
        with path.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        manifest["files"][name] = {"bytes": path.stat().st_size, "sha256": digest}
    (images / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (images / "SHA256SUMS").write_text("".join(
        manifest["files"][name]["sha256"] + "  " + name + "\n"
        for name in ["sdcard.img", "sdcard.img.gz"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["bootstrap", "pl", "test", "szl", "linux", "boot", "image"])
    parser.add_argument("--board", choices=["kasli-soc", "zc706"], default="kasli-soc")
    args = parser.parse_args()
    BOARD = args.board
    if BOARD == "zc706":
        BUILD = SHARED / "zc706"
    BUILD.mkdir(parents=True, exist_ok=True)
    globals()[args.stage]()
