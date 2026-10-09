#!/usr/bin/env python3
"""Verify beginning, middle and end of each CH1 analog buffer read from PL DDR."""
import argparse,hashlib,json
from pathlib import Path
from analyze_adc_sine import np,plt,fit_sine
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('capture',type=Path);a=p.parse_args()
result=dict(result='FAIL',source='PL DDR GP1 readback',synchronized=False,
            sample_rate_hz=100000000,voltage_calibrated=False,cards={})
fig,axes=plt.subplots(2,1,figsize=(12,7),layout='constrained')
for card in (1,2):
    raw=(a.capture/f'card{card}-analog.bin').read_bytes()
    if len(raw)%8 or len(raw)<8192:raise RuntimeError('Incomplete four-channel buffer')
    all_values=np.frombuffer(raw,dtype='<i2').reshape(-1,4)[:,0].astype(float)/4
    windows=[]
    for start in sorted(set((0,len(all_values)//2,len(all_values)-1024))):
        if start+1024>len(all_values):continue
        checked,_=fit_sine(all_values[start:start+1024],100e6)
        windows.append(dict(start_sample=start,**checked))
    values=all_values[:1024]
    measurement,fitted=fit_sine(values,100e6)
    measurement.update(samples_in_buffer=len(all_values),windows=windows,
        buffer_sha256=hashlib.sha256(raw).hexdigest())
    measurement['passed']=all(w['passed'] for w in windows)
    result['cards'][str(card)]=measurement
    ax=axes[card-1];t=np.arange(1024)/100
    ax.plot(t,values,'.',markersize=2,label='ADC → FIFO → DDR → GP1')
    ax.plot(t,fitted,label='Sine fit');ax.grid(alpha=.25);ax.legend()
    ax.set_xlabel('Time from this card’s capture start (µs)');ax.set_ylabel('Signed 14-bit ADC codes')
    ax.set_title(f"{'LPC' if card==1 else 'HPC'} CH1: {measurement['frequency_hz']/1e6:.6f} MHz, "
                 f"{measurement['vpp_adc_codes']:.1f} codes pp, R²={measurement['r_squared']:.7f}")
result['result']='PASS' if all(m['passed'] for m in result['cards'].values()) else 'FAIL'
fig.suptitle('AFG1062 1 MHz / 1 Vpp into two parallel FMC inputs — PL DDR acquisition\nIndependent clocks/epochs; nominal 100 MS/s; uncalibrated voltage scale')
fig.savefig(a.capture/'ddr-waveforms.png',dpi=160);fig.savefig(a.capture/'ddr-waveforms.svg')
(a.capture/'analog-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if result['result']!='PASS':raise SystemExit(1)
