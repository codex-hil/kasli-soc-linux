#!/usr/bin/env python3
"""Decode seven diagnostic CSR words latched from an ARP RX header."""
import argparse
import ipaddress
import json
import struct
from pathlib import Path


def decode(status):
    raw=b''.join(status[f'mac_status_arp_reply_header{i}'].to_bytes(4,'little') for i in range(7))
    hwtype,proto,hwsize,protosize,opcode,smac,sip,tmac,tip=struct.unpack('!HHBBH6sI6sI',raw)
    mac=lambda value: ':'.join(f'{b:02x}' for b in value)
    return dict(raw_hex=raw.hex(),hwtype=hwtype,proto=proto,hwsize=hwsize,
        protosize=protosize,opcode=opcode,sender_mac=mac(smac),
        sender_ip=str(ipaddress.IPv4Address(sip)),target_mac=mac(tmac),
        target_ip=str(ipaddress.IPv4Address(tip)),
        sender_ip_matches_csr=sip==status['mac_status_arp_sender_ip'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('validation',type=Path)
    args=parser.parse_args()
    result=json.loads(args.validation.read_text())
    print(json.dumps({key:decode(result[key]['status']) for key in
        ('external_probe','external_after')},indent=2))

if __name__=='__main__':main()
