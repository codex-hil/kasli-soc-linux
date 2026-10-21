import json
from fmc_adc import Registers
from wr_pll_control import Si570
reference=json.load(open('reference.json'))
opened=[]
report={'result':'FAIL','flash_otp_written':False,'cards':{}}
try:
    # Validate both cards/dividers and bounded RFREQ difference before writes.
    for card in (1,2):
        r=Registers('csr.json','/dev/uio0',card)
        s=Si570(r);opened.append((r,s))
        target=reference[str(card)]
        assert s.original[0]==target[0] and (s.original[1]&0xc0)==(target[1]&0xc0)
        delta=(s.decode(s.original)/s.decode(target)-1)*1e6
        assert abs(delta)<=50,delta
        report['cards'][str(card)]={'before':s.original[:],'reference':target,'delta_ppm':delta}
    for card,(r,s) in enumerate(opened,1):
        s.original=reference[str(card)]
        s.base=s.decode(s.original)
        s.changed=True
        s.restore()
        report['cards'][str(card)]['after']=s.i2c.read(0x55,7,6)
        assert report['cards'][str(card)]['after']==reference[str(card)]
    report['result']='PASS'
finally:
    for r,s in opened:r.mem.close()
    print(json.dumps(report,indent=2),flush=True)
