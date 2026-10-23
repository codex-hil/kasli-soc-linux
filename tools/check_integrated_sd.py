#!/usr/bin/env python3
"""Offline content/ownership audit of the integrated SD image, not a boot test."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from check_sd_image import audit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(images, host):
    manifest = json.loads((images/'manifest.json').read_text())
    result = dict(sd_audit=audit(images/'sdcard.img'), hardware_boot_tested=False)
    for name, expected in manifest['files'].items():
        with (images/name).open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected['sha256']:
            raise RuntimeError('Image manifest mismatch: '+name)
    result['file_hashes'] = 'PASS'
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        for name in ('BOOT.BIN', 'u-boot.img', 'boot.scr', 'top.bit', 'zImage', 'zc706.dtb'):
            target = tmp/name
            subprocess.run([str(host/'bin/mcopy'), '-i', str(images/'boot.vfat'),
                            '::'+name, str(target)], check=True)
            if sha(target.read_bytes()) != manifest['files'][name]['sha256']:
                raise RuntimeError('FAT payload mismatch: '+name)
        expected = {'/opt/zc706-integrated/'+name:digest
                    for name,digest in manifest['runtime']['files'].items()}
        expected['/etc/litex/csr.json'] = manifest['runtime']['csr_sha256']
        source = Path(__file__).resolve().parents[1]/'buildroot/board/zc706/S99integrated'
        expected['/etc/init.d/S99integrated'] = sha(source.read_bytes())
        for index,(name,digest) in enumerate(expected.items()):
            target = tmp/('rootfs-'+str(index))
            subprocess.run([str(host/'sbin/debugfs'), '-R', 'dump '+name+' '+str(target),
                            str(images/'rootfs.ext4')], check=True, capture_output=True)
            if sha(target.read_bytes()) != digest:
                raise RuntimeError('Rootfs payload mismatch: '+name)
        stat = subprocess.check_output([str(host/'sbin/debugfs'), '-R',
            'stat /etc/init.d/S99integrated', str(images/'rootfs.ext4')], text=True)
        if 'User:     0   Group:     0' not in stat or '0755' not in stat:
            raise RuntimeError('Init script ownership/mode mismatch: '+stat)
        result.update(fat_payloads='PASS', runtime_payloads='PASS', init_stat=stat)
    result['result'] = 'PASS'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.images.resolve(), args.host.resolve())
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
