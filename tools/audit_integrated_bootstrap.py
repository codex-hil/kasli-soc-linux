#!/usr/bin/env python3
"""Read-only inventory of qualified integrated build bootstrap dependencies."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--checkout',type=Path,default=Path(__file__).resolve().parents[1])
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=a.checkout.resolve()
chain=['srl_nextpnr','integrated_nextpnr','sfp_nextpnr','adc_ddr_nextpnr','adc_nextpnr','ddr_nextpnr']
rows=[]
for name,entry in json.loads((root/'sources.lock.json').read_text()).items():
 path=root/'upstream'/name
 actual=None
 if (path/'.git').exists():
  actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
 rows.append(dict(name=name,expected=entry['rev'],actual=actual,pinned_match=actual==entry['rev']))
generators={
 'build/zc706-ddr/nextpnr-build':'tools/ddr_nextpnr.py: CMake configure/build from pinned nextpnr',
 'build/zc706-adc/nextpnr-term':'tools/adc_nextpnr.py: baseline then isolated patch/relink',
 'build/zc706-adc-ddr/nextpnr-hold':'tools/adc_ddr_nextpnr.py: ADC baseline then isolated patch/relink',
 'build/zc706-sfp/nextpnr':'tools/sfp_nextpnr.py: hold baseline then GTX patches',
 'build/zc706-integrated-srl-timing/nextpnr':'tools/srl_nextpnr.py: integrated backend plus SDF model',
 'build/wr-ddmtd':'tools/build_wr_ddmtd.py: GHDL translation',
 'build/zc706-ddr/chipdb':'tools/ddr_chipdb.py: metadata submodule and chipdb generation'}
result=dict(scope='static/bootstrap inventory; not a clean build qualification',hardware_access=False,
 clean_replay_executed=False,nextpnr_prepare_chain=chain,sources=rows,
 generated_cache_rebuilders=generators,tool_archives=json.loads((root/'toolchains.lock.json').read_text()),
 prerequisites=['Container/runtime OS development packages from tools/environment.py',
 'Pinned source checkouts and nextpnr metadata submodule (network or preseeded Git objects)',
 'Python environment from tools/image.py bootstrap',
 'Pinned openXC7 and OSS CAD Suite archives; GHDL and C++/CMake toolchain'],
 remaining_proof=['Fresh isolated build directory with no copied generated nextpnr objects/chipdb',
 'Verify Python imports resolve isolated checkouts, not existing editable install paths',
 'Record runtime package/compiler versions; package names alone are not immutable pins',
 'Rebuild and compare admitted timing/netlist/bitstream; hardware equivalence only after admission'])
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'pinned_sources':sum(r['pinned_match'] for r in rows),'total_sources':len(rows),'clean_replay_executed':False}))
