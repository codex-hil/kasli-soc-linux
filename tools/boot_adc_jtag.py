#!/usr/bin/env python3
"""Load verified ZC706 ADC PL at the U-Boot prompt, then boot existing SD Linux.

Default: volatile JTAG and PS system reset, without SD/QSPI writes.
--sd: upload a checksummed bitstream file to the existing ext4 SD rootfs,
reboot Linux, then load through U-Boot. Never changes QSPI, default boot
files or persistent U-Boot environment. Supply --host to sync before reset.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import time
import serial

ROOT = Path(__file__).resolve().parents[1]
UART = '/dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit', type=Path, default=ROOT/'build/zc706-adc/gateware/gateware/top.bit')
    p.add_argument('--jtag-serial', default='210251842914')
    p.add_argument('--port', default=UART)
    p.add_argument('--host', type=ipaddress.ip_address)
    p.add_argument('--output', type=Path)
    p.add_argument('--sd', action='store_true', help='Upload a new content-addressed SD file and load via U-Boot; no JTAG needed')
    a = p.parse_args()
    if a.sd and not a.host:
        p.error("--sd requires --host for safe upload and reboot")
    if not re.fullmatch(r'[0-9]+', a.jtag_serial):
        p.error('Expected numeric Digilent adapter serial')
    manifest = json.loads((a.bit.parent/'manifest.json').read_text())
    digest = hashlib.sha256(a.bit.read_bytes()).hexdigest()
    if manifest.get('design') != 'fmc-adc' or manifest.get('bitstream_sha256') != digest:
        p.error('ADC bitstream must match its successful build manifest')
    out = a.output or ROOT/'build/zc706-adc/hardware'/datetime.now(timezone.utc).strftime('boot-%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True, exist_ok=True)
    suite = ROOT/'build/tools/oss-cad-suite/bin'
    if a.host:
        subprocess.run(['ssh', '-i', str(ROOT/'build/ssh/id_ed25519'),
            '-o', 'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),
            '-o', 'HostKeyAlias=192.168.2.15', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', 'root@'+str(a.host), 'sync'], check=True, timeout=15)
    config = out/'openocd.cfg'
    config.write_text('adapter driver ftdi\nftdi vid_pid 0x0403 0x6014\n'
        'adapter serial '+a.jtag_serial+'\nftdi channel 0\n'
        'ftdi layout_init 0x00e8 0x60eb\nadapter speed 1000\n'
        'set zynq_pl zynq_pl\nsource [find target/zynq_7000.cfg]\n')
    reset = ('gdb_port disabled; telnet_port disabled; tcl_port disabled; init; '
        'zynq.dap apreg 0 0 0x23000052; zynq.dap apreg 0 4 0xf8000008; '
        'zynq.dap apreg 0 0xc 0xdf0d; zynq.dap apreg 0 4 0xf8000200; '
        'zynq.dap apreg 0 0xc 1; shutdown')
    if a.sd:
        ssh = ['ssh', '-i', str(ROOT/'build/ssh/id_ed25519'),
            '-o', 'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),
            '-o', 'HostKeyAlias=192.168.2.15', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', 'root@'+str(a.host)]
        sd_name = 'adc-'+digest+'.bit'
        # The minimal kernel has no VFAT driver; use its existing ext4 rootfs.
        sd_path = '/root/'+sd_name
        subprocess.run(ssh+['cat > '+sd_path+'.tmp'], input=a.bit.read_bytes(), check=True, timeout=30)
        actual = subprocess.check_output(ssh+['sha256sum '+sd_path+'.tmp'], timeout=15).decode().split()[0]
        if actual != digest:
            raise RuntimeError('SD upload checksum mismatch')
        subprocess.run(ssh+['mv '+sd_path+'.tmp '+sd_path+' && sync'], check=True, timeout=15)
    uart = serial.Serial(baudrate=115200, timeout=.1)
    uart.port, uart.dtr, uart.rts = a.port, False, False
    uart.open()
    result = {'bitstream_sha256': digest, 'sd_qspi_written': False,
              'jtag_serial': a.jtag_serial, 'boot_passed': False,
              'sd_written': a.sd, 'qspi_written': False, 'boot_environment_written': False,
              'method': 'sd-ext4-uboot' if a.sd else 'jtag', 'jtag_used': not a.sd}
    if a.sd:
        result['sd_qspi_written'] = True
        result['sd_file'] = sd_name
    try:
        with (out/'uart.log').open('wb') as log:
            def read():
                block = uart.read(4096)
                log.write(block); log.flush()
                return block
            def command(text):
                uart.write(text.encode()+b'\r')
                transcript = b''
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    transcript += read()
                    if b'Zynq> ' in transcript:
                        return transcript
                raise TimeoutError('U-Boot command did not complete: '+text)
            print('Resetting PS and stopping U-Boot', flush=True)
            with (out/'reset.log').open('w') as f:
                if a.sd:
                    reboot = subprocess.run(ssh+['reboot'], stdout=f, stderr=subprocess.STDOUT, timeout=15)
                    if reboot.returncode not in (0, 255):
                        raise RuntimeError('Linux reboot failed')
                else:
                    subprocess.run([suite/'openocd', '-f', config, '-c', reset],
                        stdout=f, stderr=subprocess.STDOUT, check=True, timeout=15)
            transcript = b''; interrupted = False
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                transcript += read()
                if not interrupted and b'Hit any key' in transcript:
                    uart.write(b' '); interrupted = True
                if interrupted and b'Zynq> ' in transcript:
                    break
            if not interrupted or b'Zynq> ' not in transcript:
                raise TimeoutError('Did not stop U-Boot')
            print('Loading ADC bitstream into volatile PL', flush=True)
            with (out/'program.log').open('w') as f:
                if a.sd:
                    programmed = command('ext4load mmc 0:2 ${kernel_addr_r} '+sd_path+' && fpga loadb 0 ${kernel_addr_r} ${filesize}')
                    f.write(programmed.decode(errors='replace'))
                    if b'Error' in programmed or b'Failed' in programmed:
                        raise RuntimeError('U-Boot FPGA loading failed')
                else:
                    subprocess.run([suite/'openFPGALoader', '-b', 'zc706',
                        '--usb-serial-num', a.jtag_serial, '--write-sram', a.bit],
                        stdout=f, stderr=subprocess.STDOUT, check=True, timeout=60)
            probe = command('mw.l 0xf8000008 0xdf0d; mw.l 0xf8000900 0xf; '
                'mw.l 0xf8000240 0xf; mw.l 0xf8000240 0; '
                'mw.l 0xf8000170 0x00100a00; md.l 0x40000808 1')
            if not re.search(rb'40000808:\s+4b534f43', probe):
                raise RuntimeError('U-Boot PL signature check failed')
            print('PL signature PASS; starting Linux from existing SD', flush=True)
            uart.write(('load mmc 0:1 ${fdt_addr_r} zc706.dtb && '
                'load mmc 0:1 ${kernel_addr_r} zImage && '
                'setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rootwait rw '
                'clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio && '
                'bootz ${kernel_addr_r} - ${fdt_addr_r}\r').encode())
            transcript = b''; logged_in = False; next_probe = None
            deadline = time.monotonic()+60
            while time.monotonic() < deadline:
                transcript += read()
                if not logged_in and b'zc706-linux login:' in transcript:
                    uart.write(b'root\r'); logged_in = True; next_probe = time.monotonic()+1
                if next_probe is not None and time.monotonic() >= next_probe:
                    uart.write(b'ip -4 addr show eth0; uptime\r'); next_probe = time.monotonic()+5
                match = re.search(rb'inet (\d+\.\d+\.\d+\.\d+)/\d+.*scope global', transcript)
                if match:
                    result['host'] = str(ipaddress.ip_address(match.group(1).decode()))
                    result['boot_passed'] = True
                    break
            if not result['boot_passed']:
                raise TimeoutError('Linux UART login/DHCP did not complete')
            print(json.dumps(result, indent=2), flush=True)
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        uart.close()
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
