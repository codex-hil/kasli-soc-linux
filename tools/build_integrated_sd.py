#!/usr/bin/env python3
"""Package a separate ZC706 integrated SD image from verified build outputs.

Run on Dell inside the existing CAD runtime. Does not touch a physical SD card
or modify the baseline Buildroot output. Rebuild the base via image.py first
when a fresh Linux/U-Boot/rootfs build is required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=ROOT/'build/zc706/buildroot')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    host = args.base.resolve()/'host'
    if os.geteuid() != 0:
        # Preserve ownership through extraction, installation and filesystem build.
        os.execv(str(host/'bin/fakeroot'), ['fakeroot', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rootfs = out/'target'
    rootfs.mkdir()
    images = out/'images'
    images.mkdir()
    base = args.base.resolve()/'images'
    work = args.work_dir.resolve()
    bit = work/'gateware/gateware/top.bit'
    manifest = json.loads((bit.parent/'manifest.json').read_text())
    validation = json.loads(args.validation.read_text())
    bit_hash = digest(bit)
    if (manifest.get('design') != 'integrated' or manifest.get('bitstream_sha256') != bit_hash
            or validation.get('bitstream_sha256') != bit_hash
            or validation.get('result') != 'PASS' or not validation.get('restoration_passed')
            or not validation.get('core_integration_passed')):
        raise RuntimeError('Require the exact physically qualified integrated PL')
    subprocess.run(['tar', '-xf', str(base/'rootfs.tar'), '-C', str(rootfs)], check=True)
    runtime = rootfs/'opt/zc706-integrated'
    runtime.mkdir(parents=True)
    for name in ('pl-ddr-test', 'adc-ddr-read', 'i2c.so'):
        if digest(work/name) != validation['files'][name]:
            raise RuntimeError('Qualified software hash mismatch: '+name)
        shutil.copy2(work/name, runtime/name)
    names = ('integrated_service.py', 'run_wr_pll_dual.py', 'run_wr_pll.py',
             'fmc_adc.py', 'measure_fmc_clocks.py', 'wr_pll_control.py',
             'sfp_probe.py', 'capture_adc_ddr.py')
    for name in names:
        shutil.copy2(ROOT/'tools'/name, runtime/name)
    csr = rootfs/'etc/litex/csr.json'
    shutil.copy2(work/'gateware/csr.json', csr)
    runtime_manifest = dict(bitstream_sha256=bit_hash, csr_sha256=digest(csr),
                            files={p.name:digest(p) for p in runtime.iterdir()})
    (runtime/'runtime-manifest.json').write_text(json.dumps(runtime_manifest, indent=2)+'\n')
    shutil.copy2(ROOT/'buildroot/board/zc706/S99integrated', rootfs/'etc/init.d/S99integrated')
    (rootfs/'etc/init.d/S99integrated').chmod(0o755)
    for name in ('BOOT.BIN', 'u-boot.img', 'zImage', 'zc706.dtb'):
        shutil.copy2(base/name, images/name)
    shutil.copy2(bit, images/'top.bit')
    subprocess.run([str(host/'bin/mkimage'), '-A', 'arm', '-T', 'script', '-C', 'none',
                    '-n', 'ZC706 integrated SD', '-d', str(ROOT/'buildroot/board/zc706/boot-integrated.cmd'),
                    str(images/'boot.scr')], check=True)
    config = out/'genimage.cfg'
    config.write_text('''image rootfs.ext4 {
    ext4 { label = "zc706-root" }
    size = 256M
}
image boot.vfat {
    vfat { files = { "BOOT.BIN", "u-boot.img", "boot.scr", "top.bit", "zImage", "zc706.dtb" } }
    size = 64M
}
image sdcard.img {
    hdimage { }
    partition boot {
        partition-type = 0xC
        bootable = "true"
        image = "boot.vfat"
    }
    partition rootfs {
        partition-type = 0x83
        image = "rootfs.ext4"
    }
}
''')
    env = dict(os.environ, PATH=str(host/'bin')+':'+str(host/'sbin')+':'+os.environ['PATH'])
    subprocess.run([str(host/'bin/genimage'), '--rootpath', str(rootfs),
                    '--tmppath', str(out/'genimage-tmp'), '--inputpath', str(images),
                    '--outputpath', str(images), '--config', str(config)], env=env, check=True)
    subprocess.run([sys.executable, str(ROOT/'tools/check_sd_image.py'), str(images/'sdcard.img')], check=True)
    with (images/'sdcard.img.gz').open('wb') as compressed:
        subprocess.run(['gzip', '-n', '-c', str(images/'sdcard.img')], stdout=compressed, check=True)
    result = dict(board='zc706', hardware_validated=False, sd_boot_tested=False,
                  bitstream_sha256=bit_hash, base_rootfs_sha256=digest(base/'rootfs.tar'),
                  runtime=runtime_manifest,
                  files={p.name:dict(sha256=digest(p), bytes=p.stat().st_size) for p in images.iterdir()})
    (images/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print('SD image packaged; physical standalone boot remains NOT_RUN', flush=True)


if __name__ == '__main__':
    main()
