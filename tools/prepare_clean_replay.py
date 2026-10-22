#!/usr/bin/env python3
"""Prepare isolated source/object-cache replay using pinned local source/tool caches."""
import argparse,hashlib,json,os,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-archive',type=Path,required=True)
p.add_argument('--destination',type=Path,required=True)
p.add_argument('--git-bundle-cache',type=Path,help='Pinned source-only bundles when runtime checkouts lack Git metadata')
a=p.parse_args();archive=a.source_archive.resolve();dest=a.destination.resolve()
if dest.exists():raise SystemExit('Destination exists; refusing to reuse or remove it')
dest.mkdir(parents=True)
with tarfile.open(archive) as t:t.extractall(dest,filter='data')
lock=json.loads((dest/'sources.lock.json').read_text());sources=[]
required=['migen','litex','litex-boards','litedram','liteeth','liteiclink','nextpnr','prjxray-db','general-cores-wr','wr-cores-afcz-v5']
for name in required:
 entry=lock[name]
 src=ROOT/'upstream'/name
 bundle=(a.git_bundle_cache/(name+'.bundle')).resolve() if a.git_bundle_cache else None
 if bundle and bundle.exists():
  target=dest/'upstream'/name;target.parent.mkdir(exist_ok=True)
  subprocess.run(['git','clone','--quiet','--no-checkout',bundle,target],check=True)
  subprocess.run(['git','-C',target,'checkout','--quiet','--detach',entry['rev']],check=True)
  sources.append(dict(name=name,revision=entry['rev'],bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest()))
  continue
 actual=subprocess.check_output(['git','-C',src,'rev-parse','HEAD'],text=True).strip()
 if actual!=entry['rev']:raise RuntimeError('Source cache revision mismatch: '+name)
 target=dest/'upstream'/name;target.parent.mkdir(exist_ok=True)
 subprocess.run(['git','clone','--quiet','--shared','--no-checkout',src,target],check=True)
 subprocess.run(['git','-C',target,'checkout','--quiet','--detach',entry['rev']],check=True)
 sources.append(dict(name=name,revision=actual))
# Preseed only the pinned metadata gitlink from the local object cache; runtime is offline.
np=dest/'upstream/nextpnr';meta='himbaechel/uarch/xilinx/meta'
subprocess.run(['git','-C',np,'submodule','init',meta],check=True)
subprocess.run(['git','-C',np,'config','submodule.'+meta+'.url',str(ROOT/'upstream/nextpnr'/meta)],check=True)
subprocess.run(['git','-c','protocol.file.allow=always','-C',np,'submodule','update','--init',meta],check=True)
expected=subprocess.check_output(['git','-C',np,'rev-parse','HEAD:'+meta],text=True).strip()
actual=subprocess.check_output(['git','-C',np/meta,'rev-parse','HEAD'],text=True).strip()
if expected!=actual:raise RuntimeError('Metadata gitlink mismatch')
# Only compiler/tool assets are reused. No generated FPGA build outputs are copied.
build=dest/'build';build.mkdir(exist_ok=True)
assets=json.loads((dest/'toolchains.lock.json').read_text())
for name,entry in assets.items():
 marker=ROOT/'build/tools'/name/'.sha256'
 if marker.read_text().strip()!=entry['sha256']:raise RuntimeError('Tool archive marker mismatch: '+name)
(build/'tools').symlink_to(ROOT/'build/tools')
paths=[dest/'upstream'/n for n in ['migen','litex','litex-boards','litedram','liteeth','liteiclink']]
env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,paths)),PYTHONNOUSERSITE='1')
probe='import json,migen,litex,litex_boards,litedram,liteeth,liteiclink; print(json.dumps({m.__name__:m.__file__ for m in [migen,litex,litex_boards,litedram,liteeth,liteiclink]}))'
imports=json.loads(subprocess.check_output([sys.executable,'-c',probe],env=env,text=True))
if any(not Path(v).is_relative_to(dest/'upstream') for v in imports.values()):raise RuntimeError('Nonisolated Python source import')
report=dict(result='PREPARED_NOT_BUILT',hardware_access=False,source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
 destination=str(dest),sources=sources,metadata_revision=actual,python_imports=imports,
 pythonpath=env['PYTHONPATH'],interpreter=sys.executable,reused='pinned source Git objects, tool assets and runtime only',generated_objects_copied=False)
(dest/'replay-preparation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
