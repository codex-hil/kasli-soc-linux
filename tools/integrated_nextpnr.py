#!/usr/bin/env python3
"""Isolated reserved-source checker fix and optional routing snapshots."""
import hashlib,json,shlex,subprocess
from pathlib import Path
from sfp_nextpnr import prepare as base_prepare
ROOT=Path(__file__).resolve().parents[1]

def prepare(out=None):
    base=base_prepare()
    out=out or ROOT/'build/zc706-integrated/nextpnr'
    out.mkdir(parents=True,exist_ok=True)
    original=ROOT/'build/zc706-ddr/nextpnr-source/common/route/router1.cc'
    source=out/'router1.cc'
    content=original.read_text().replace('#include <chrono>','#include <chrono>\n#include <fstream>\n#include "jsonwrite.h"')
    content=content.replace('log_assert(valid_wires_for_net.count(w));',
        'if (!valid_wires_for_net.count(w)) log_error("Orphan preroute: net=%s wire=%s strength=%d driver=%s users=%d\\n", ctx->nameOf(net_info), ctx->nameOfWire(w), int(it.second.strength), ctx->nameOf(net_info->driver.cell), int(net_info->users.entries()));')
    content=content.replace('log_assert(src_wire != WireId());',
        'log_assert(src_wire != WireId());\n            // A reserved driver root is valid before any sink arc is routed.\n            valid_wires_for_net.insert(src_wire);')
    content=content.replace('        router.setup();','''        router.setup();
        if (const char *snapshot = std::getenv("NEXTPNR_ROUTE_SNAPSHOT")) {
            std::string filename(snapshot); std::ofstream file(filename);
            if (!write_json_file(file, filename, ctx)) log_error("Snapshot failed\\n");
        }''')
    source.write_text(content)
    router2 = (original.parent/'router2.cc').read_text()
    router2 = router2.replace('#include "router2.h"', '#include "router2.h"\n#include "jsonwrite.h"')
    router2 = router2.replace('(iter % 5000000)', '(iter % 100000)')
    router2 = router2.replace('                    for (PipId dh : ctx->getPipsDownhill(curr_data.w)) {', r'''                    for (PipId dh : ctx->getPipsDownhill(curr_data.w)) {
                        if (curr_data.w == src_wire && i.idx() == 0 && net->driver.cell && net->driver.cell->type.in(ctx->id("BUFGCTRL"), ctx->id("MMCME2_ADV_MMCME2_ADV"))) {
                            auto next_debug = ctx->getPipDstWire(dh);
                            auto &wd_debug = wire_data(next_debug);
                            auto known_debug = nd.wires.find(next_debug);
                            log_info("Root-step: net=%s pip=%s box=%d avail=%d reserved=%d own=%d unavailable=%d known=%d samepip=%d\n", ctx->nameOf(net), ctx->nameOfPip(dh), int(hit_test_pip(nd.bb,ctx->getPipLocation(dh))), int(ctx->checkPipAvailForNet(dh,net)), wd_debug.reserved_net, net->udata, int(wd_debug.unavailable), int(known_debug != nd.wires.end()), int(known_debug == nd.wires.end() || known_debug->second.first == dh));
                        }''')
    router2 = router2.replace('        setup_resources();', '''        if (const char *snapshot = std::getenv("NEXTPNR_ROUTE_SNAPSHOT")) {
            std::string filename(snapshot); std::ofstream file(filename);
            if (!write_json_file(file, filename, ctx)) log_error("Snapshot failed\\n");
        }
        setup_resources();''')
    (out/'router2.cc').write_text(router2)
    xilinx = (base.parent/'source/himbaechel/uarch/xilinx/xilinx.cc').read_text()
    xilinx = xilinx.replace('    apply_prerouted();', r'''    apply_prerouted();
    for (auto &entry : ctx->nets) {
        NetInfo *net = entry.second.get();
        if (!net->driver.cell || !net->driver.cell->type.in(id_BUFGCTRL, id_MMCME2_ADV_MMCME2_ADV)) continue;
        WireId root = ctx->getNetinfoSourceWire(net);
        for (auto pip : ctx->getPipsDownhill(root)) {
            WireId dst = ctx->getPipDstWire(pip); NetInfo *bound = ctx->getBoundWireNet(dst);
            log_info("Clock-root: net=%s pip=%s available=%d dst_owner=%s\n", ctx->nameOf(net), ctx->nameOfPip(pip), int(ctx->checkPipAvailForNet(pip,net)), bound ? ctx->nameOf(bound) : "none");
            if (!bound) for (auto child : ctx->getPipsDownhill(dst)) {
                log_info("Clock-child: net=%s pip=%s available=%d\n", ctx->nameOf(net), ctx->nameOfPip(child), int(ctx->checkPipAvailForNet(child,net)));
            }
        }
    }''')
    (out/'xilinx.cc').write_text(xilinx)
    identity=dict(base_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(content.encode()).hexdigest(),router2_sha256=hashlib.sha256(router2.encode()).hexdigest(),xilinx_sha256=hashlib.sha256(xilinx.encode()).hexdigest())
    marker=out/'manifest.json';binary=out/'nextpnr-himbaechel-xilinx'
    if marker.exists() and binary.exists() and json.loads(marker.read_text())==identity:return binary
    work=ROOT/'build/zc706-ddr/nextpnr-build/himbaechel/uarch/xilinx'
    objects=work/'CMakeFiles/nextpnr-himbaechel-xilinx.dir'
    flags={}
    for line in (objects/'flags.make').read_text().splitlines():
        if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')):
            k,v=line.split('=',1);flags[k.strip()]=shlex.split(v.replace('-flto=auto','-flto=2'))
    subprocess.run(['/usr/bin/c++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-c',str(source),'-o',str(out/'router1.cc.o')],check=True)
    subprocess.run(['/usr/bin/c++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-c',str(out/'router2.cc'),'-o',str(out/'router2.cc.o')],check=True)
    subprocess.run(['/usr/bin/c++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-I'+str(base.parent/'source/himbaechel/uarch/xilinx'),'-c',str(out/'xilinx.cc'),'-o',str(out/'xilinx.cc.o')],check=True)
    command=[];output=False
    for token in shlex.split((objects/'link.txt').read_text()):
        if output:command.append(str(binary));output=False
        elif token=='-o':command.append(token);output=True
        elif token.startswith('-Wl,--dependency-file='):command.append('-Wl,--dependency-file='+str(out/'link.d'))
        elif token=='-flto=auto':command.append('-flto=2')
        elif token.endswith(('.o','.a')):
            path=work/token
            if path.name in ('fasm.cc.o','pack_io.cc.o'):path=base.parent/path.name
            if path.name in ('hold_fix.cc.o','xilinx.cc.o'):path=ROOT/'build/zc706-adc-ddr/nextpnr-hold'/path.name
            if path.name in ('router1.cc.o','router2.cc.o','xilinx.cc.o'):path=out/path.name
            command.append(str(path.resolve()))
        else:command.append(token)
    subprocess.run(command,cwd=out,check=True)
    marker.write_text(json.dumps(identity,indent=2)+'\n')
    return binary

if __name__=='__main__':print(prepare())
