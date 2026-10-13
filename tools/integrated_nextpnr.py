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
            for (auto &entry : ctx->nets) {
                NetInfo *net=entry.second.get();
                if (!net->clkconstr) continue;
                auto &cc=*net->clkconstr;
                net->attrs[ctx->id("NEXTPNR_CLK_PERIOD_MIN")]=int64_t(cc.period.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_PERIOD_MAX")]=int64_t(cc.period.maxDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_HIGH_MIN")]=int64_t(cc.high.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_HIGH_MAX")]=int64_t(cc.high.maxDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_LOW_MIN")]=int64_t(cc.low.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_LOW_MAX")]=int64_t(cc.low.maxDelay());
            }
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
            for (auto &entry : ctx->nets) {
                NetInfo *net=entry.second.get();
                if (!net->clkconstr) continue;
                auto &cc=*net->clkconstr;
                net->attrs[ctx->id("NEXTPNR_CLK_PERIOD_MIN")]=int64_t(cc.period.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_PERIOD_MAX")]=int64_t(cc.period.maxDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_HIGH_MIN")]=int64_t(cc.high.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_HIGH_MAX")]=int64_t(cc.high.maxDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_LOW_MIN")]=int64_t(cc.low.minDelay());
                net->attrs[ctx->id("NEXTPNR_CLK_LOW_MAX")]=int64_t(cc.low.maxDelay());
            }
            std::string filename(snapshot); std::ofstream file(filename);
            if (!write_json_file(file, filename, ctx)) log_error("Snapshot failed\\n");
        }
        setup_resources();''')
    (out/'router2.cc').write_text(router2)
    xilinx = (base.parent/'source/himbaechel/uarch/xilinx/xilinx.cc').read_text()
    guard = 'void XilinxImpl::notifyBelChange(BelId bel, CellInfo *cell)\n{'
    assert xilinx.count(guard) == 1
    xilinx = xilinx.replace(guard, guard + r'''
    if (bel == BelId()) {
        auto attr = cell->attrs.find(ctx->id("NEXTPNR_BEL"));
        log_error("Invalid restored BEL: cell=%s bel=%s\n", ctx->nameOf(cell),
            attr == cell->attrs.end() ? "<missing>" : attr->second.as_string().c_str());
    }
''', 1)
    xilinx = xilinx.replace('void XilinxImpl::preRoute()\n{', 'void XilinxImpl::preRoute()\n{\n    bool loading_preplaced = !cell_tags_set;', 1)
    xilinx = xilinx.replace('    find_source_sink_locs();', r'''    int restored_clocks=0;
    for (auto &entry : ctx->nets) {
        NetInfo *net=entry.second.get();
        if (!net->attrs.count(ctx->id("NEXTPNR_CLK_PERIOD_MIN"))) continue;
        auto read=[&](const char *name) {return delay_t(net->attrs.at(ctx->id(name)).as_int64());};
        net->clkconstr=std::make_unique<ClockConstraint>();
        net->clkconstr->period=DelayPair(read("NEXTPNR_CLK_PERIOD_MIN"),read("NEXTPNR_CLK_PERIOD_MAX"));
        net->clkconstr->high=DelayPair(read("NEXTPNR_CLK_HIGH_MIN"),read("NEXTPNR_CLK_HIGH_MAX"));
        net->clkconstr->low=DelayPair(read("NEXTPNR_CLK_LOW_MIN"),read("NEXTPNR_CLK_LOW_MAX"));
        ++restored_clocks;
    }
    if (restored_clocks) log_info("Restored %d snapshot clock constraints\n",restored_clocks);
    if (!restored_clocks && loading_preplaced && !std::getenv("NEXTPNR_CLOCK_DIAGNOSTIC_EXIT"))
        log_error("Preplaced snapshot lacks clock constraints; regenerate it before routing\n");
    find_source_sink_locs();''', 1)
    xilinx = xilinx.replace('    if (pip_type == PIP_TILE_ROUTING) {', r'''    if (pip_type == PIP_TILE_ROUTING) {
        // A tile pseudo-PIP must not bypass the separately driven BUFG site.
        {
            IdString dst_name(chip_tile_info(ctx->chip_info, pip.tile).wires[pip_data.dst_wire].name);
            IdString src_name(chip_tile_info(ctx->chip_info, pip.tile).wires[pip_data.src_wire].name);
            const auto &dst_text = dst_name.str(ctx);
            if (dst_text.compare(0, 17, "CLK_BUFG_BUFGCTRL") == 0 &&
                dst_text.size() > 18 && dst_text.compare(dst_text.size()-2, 2, "_O") == 0 &&
                src_name.str(ctx) == dst_text.substr(0, dst_text.size()-2) + "_I0")
                return true;
        }''', 1)
    xilinx = xilinx.replace('    apply_prerouted();', r'''    apply_prerouted();

    if (std::getenv("NEXTPNR_CLOCK_BFS")) for (auto &entry : ctx->nets) {
        NetInfo *net = entry.second.get();
        if (net->name != ctx->id("integratedsoc_ddrclock_clkout0") && net->name != ctx->id("pma_k7_gtx_basex_s7mmcm1_clkout0")) continue;
        WireId root = ctx->getNetinfoSourceWire(net);
        for (auto &usr : net->users) {
            WireId sink = ctx->getNetinfoSinkWire(net,usr,0);
            bool clock_only=std::getenv("NEXTPNR_CLOCK_ONLY");
            bool topology_only=std::getenv("NEXTPNR_CLOCK_TOPOLOGY");
            log_info("Clock-BFS-endpoints: net=%s source=%s sink=%s clock_only=%d topology_only=%d\n",ctx->nameOf(net),ctx->nameOfWire(root),ctx->nameOfWire(sink),int(clock_only),int(topology_only));
            std::queue<WireId> forward, backward;
            dict<WireId,PipId> previous, following;
            forward.push(root); previous[root]=PipId();
            backward.push(sink); following[sink]=PipId();
            WireId meet; bool found=(root==sink);
            if (found) meet=root;
            while (!forward.empty() && !backward.empty() &&
                   previous.size()+following.size()<500000 && !found) {
                bool reverse=backward.size()<forward.size();
                auto &pending=reverse ? backward : forward;
                auto &visited=reverse ? following : previous;
                auto &opposite=reverse ? previous : following;
                WireId current=pending.front();pending.pop();
                auto inspect=[&](PipId pip) {
                    if (clock_only) {
                        std::string name=ctx->nameOfPip(pip);
                        if (name.find("CLK")==std::string::npos && name.find("BUFG")==std::string::npos && name.find("MMCM")==std::string::npos) return;
                    }
                    if (!topology_only && !ctx->checkPipAvailForNet(pip,net)) return;
                    WireId next=reverse ? ctx->getPipSrcWire(pip) : ctx->getPipDstWire(pip);
                    NetInfo *owner=ctx->getBoundWireNet(next);
                    if ((!topology_only && owner && owner!=net) || visited.count(next)) return;
                    visited[next]=pip;pending.push(next);
                    if (opposite.count(next)) {meet=next;found=true;}
                };
                if (reverse) {for (auto pip : ctx->getPipsUphill(current)) inspect(pip);}
                else {for (auto pip : ctx->getPipsDownhill(current)) inspect(pip);}
            }
            log_info("Clock-BFS: net=%s found=%d forward=%zu backward=%zu pending_forward=%zu pending_backward=%zu reason=%s\n",
                     ctx->nameOf(net),int(found),previous.size(),following.size(),forward.size(),backward.size(),
                     found ? "connected" : (forward.empty() || backward.empty()) ? "exhausted" : "vertex-limit");
            if (found) {
                WireId current=meet;int length=0;
                while (current!=root && length<200) {
                    PipId pip=previous.at(current);
                    log_info("Clock-BFS-path-up: net=%s pip=%s\n",ctx->nameOf(net),ctx->nameOfPip(pip));
                    current=ctx->getPipSrcWire(pip);++length;
                }
                current=meet;length=0;
                while (current!=sink && length<200) {
                    PipId pip=following.at(current);
                    log_info("Clock-BFS-path-down: net=%s pip=%s\n",ctx->nameOf(net),ctx->nameOfPip(pip));
                    current=ctx->getPipDstWire(pip);++length;
                }
            }
        }
    }
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
    }
    if (std::getenv("NEXTPNR_CLOCK_DIAGNOSTIC_EXIT")) log_error("Clock diagnostic complete; intentionally skipping router\n");''')
    (out/'xilinx.cc').write_text(xilinx)
    hold_original=ROOT/'build/zc706-adc-ddr/nextpnr-hold/source/himbaechel/uarch/xilinx/hold_fix.cc'
    hold=hold_original.read_text().replace('    int total_buffers = 0, total_detours = 0;',
        '    int total_buffers = 0, total_detours = 0;\n    int next_buffer_id = 0;')
    old='''            NetInfo *buf_out = ctx->createNet(ctx->idf("%s$holdbuf%d$net", net->name.c_str(ctx), total_buffers));
            CellInfo *buf = ctx->createCell(ctx->idf("%s$holdbuf%d", net->name.c_str(ctx), total_buffers), id_SLICE_LUTX);'''
    new='''            IdString cell_name, net_name;
            do {
                cell_name=ctx->idf("%s$holdbuf%d",net->name.c_str(ctx),next_buffer_id);
                net_name=ctx->idf("%s$holdbuf%d$net",net->name.c_str(ctx),next_buffer_id++);
            } while (ctx->cells.count(cell_name) || ctx->nets.count(net_name) || ctx->net_aliases.count(net_name));
            NetInfo *buf_out = ctx->createNet(net_name);
            CellInfo *buf = ctx->createCell(cell_name, id_SLICE_LUTX);'''
    if hold.count(old)!=1:raise RuntimeError('Hold buffer allocation changed; re-audit')
    hold=hold.replace(old,new).replace('                ctx->nets.erase(buf_out->name);',
        '                ctx->net_aliases.erase(buf_out->name);\n                ctx->nets.erase(buf_out->name);',1)
    hold=hold.replace('                if (buf_out)\n                    ctx->nets.erase(buf_out->name);',
        '                if (buf_out) {\n                    ctx->net_aliases.erase(buf_out->name);\n                    ctx->nets.erase(buf_out->name);\n                }')
    # An unsuccessful detour must leave the exact original private branch.
    hold = hold.replace('    if (!detour_reached_sink) {',
        '    if (!detour_reached_sink || acc < target) {', 1)
    hold = hold.replace('    return acc >= target;', '    return true;', 1)
    hold = hold.replace('    std::vector<PipId> priv_pips;',
        '    std::vector<PipId> priv_pips;\n    std::vector<decltype(net->wires.begin()->second.strength)> priv_strengths;', 1)
    hold = hold.replace('        priv_pips.push_back(pip);',
        '        priv_pips.push_back(pip);\n        priv_strengths.push_back(it->second.strength);', 1)
    hold = hold.replace('ctx->bindPip(priv_pips[i], net, STRENGTH_STRONG);',
        'ctx->bindPip(priv_pips[i], net, priv_strengths[i]);', 1)
    (out/'hold_fix.cc').write_text(hold)

    identity=dict(base_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(content.encode()).hexdigest(),router2_sha256=hashlib.sha256(router2.encode()).hexdigest(),xilinx_sha256=hashlib.sha256(xilinx.encode()).hexdigest(),hold_sha256=hashlib.sha256(hold.encode()).hexdigest())
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
    subprocess.run(['/usr/bin/c++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-I'+str(base.parent/'source/himbaechel/uarch/xilinx'),'-c',str(out/'hold_fix.cc'),'-o',str(out/'hold_fix.cc.o')],check=True)
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
            if path.name in ('router1.cc.o','router2.cc.o','xilinx.cc.o','hold_fix.cc.o'):path=out/path.name
            command.append(str(path.resolve()))
        else:command.append(token)
    subprocess.run(command,cwd=out,check=True)
    marker.write_text(json.dumps(identity,indent=2)+'\n')
    return binary

if __name__=='__main__':print(prepare())
