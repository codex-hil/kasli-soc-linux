# Zakresy, offset i terminacje obu FMC — 2026-10-09

ZC706 rev.1.2, LPC J5 i HPC J4, dual snapshot bitstream
`ab7c43cd661a61b43dc35e4a299bd3cad9a75492a85febe9e88a16197f5f9560`.
Wyniki i wszystkie próbki: `evidence/zc706/adc-ranges-20261009/`.

## Sterowanie analogowe

Źródło prawdy: `upstream/fmc-adc-100m14b4cha-sw/kernel/fa-core.c`
(`zfad_hw_range`, commit `949cbe3f687f0828a16dea18d83b331eceb5f8f4`),
`kernel/fa-regtable.c` oraz golden HDL CSR. Każdy kanał ma siedem bitów
SSR, kanał CH1 w bitach 0..6, CH2 7..13, CH3 14..20, CH4 21..27.

Zakres wejścia | Normalny kod | Kalibracja, wejście odłączone
---|---|---
±5 V (10 Vpp) | `0x45` | `0x44`
±0,5 V (1 Vpp) | `0x11` | `0x40`
±50 mV (100 mVpp) | `0x23` | `0x42`
Odłączenie | `0x00` | —

Terminacja BNC 50 Ω: niezależny bit 3 (`0x08`), dodawany do kodu zakresu.
Przykład: CH1 ±5 V, 50 Ω ON = `0x4d`; OFF = `0x45`.
API `ADC.set_input(channel, full_scale_v, termination, calibration)` używa
kanałów 0..3 i zachowuje ustawienia pozostałych kanałów.
Sprawdzono na fizycznych obu bankach łącznie 96 kombinacji
(8 kanałów × 3 zakresy × 2 tryby × 2 terminacje) z odczytem CSR.
Odczyt CSR potwierdza sterowanie cyfrowe, nie rezystancję każdego BNC.

Offset: osobny 16-bitowy DAC na każdy kanał, nominalne zero `0x8000`.
Wcześniejsze fizyczne pomiary wszystkich 8 kanałów na wszystkich zakresach
potwierdziły monotoniczność, małą histerezę i niezależność regulacji:
`evidence/zc706/adc-offset-20261008/` (LPC) i
`evidence/zc706/adc-dual-20261009/offset-hpc/` (HPC).
DAC jest tylko do zapisu; nie deklarujemy sprzętowego readbacku ani
zastosowania współczynników EEPROM.

## Nowe pomiary z generatora

AFG1062 serial 1544477: sinus 1 MHz, 50 mVpp, High-Z, DC offset 0.
Po cztery niezależne snapshoty na kartę, zakres i stan:
50 Ω OFF → ON → OFF, następnie tryb kalibracji.
Każdy snapshot zawiera 1024 próbki wszystkich czterech kanałów;
zewnętrzny sygnał jest podłączony wyłącznie do CH1 obu kart.

Pomiar CH1 | LPC | HPC
---|---|---
Zmiana ±5 V → ±0,5 V | ×9,788 | ×9,805
Zmiana ±0,5 V → ±50 mV | ×9,790 | ×9,805
50 Ω ON/OFF, ±5 V | 0,350 | 0,516
50 Ω ON/OFF, ±0,5 V | 0,347 | 0,519
50 Ω ON/OFF, ±50 mV | 0,347 | 0,520
Powrót amplitudy po OFF | 0,99998–1,00104 | 0,99992–1,00107

Zakresy działają, brak clippingu i błędów ramki. Skala napięcia jest
niekalibrowana; stosunek ×9,8 nie jest końcowym pomiarem dokładności gain.
Tryby kalibracji silnie tłumią sygnał z BNC; najniższy gain pozostawia
kilka kodów szumu/przesłuchu.

**Nie kwalifikujemy jeszcze niezależnej impedancji LPC jako 50 Ω.**
`analysis.json` zachowuje wynik FAIL dla pierwotnego założenia dwóch
niezależnych źródeł 50 Ω. Dodatkowy test przy 1 Vpp, ±5 V wykazał:

Terminacja LPC/HPC | LPC, kody pp | HPC, kody pp
---|---|---
OFF/OFF | 1574 | 1664
ON/OFF | 557 | 1203
OFF/ON | 841 | 886
ON/ON | 341 | 735
OFF/OFF powtórzenie | 1574 | 1664

Włączenie terminacji jednej karty obciąża także drugą. Wyłączenie AFG CH1
usuwa sinus z **obu** kart; wyłączenie AFG CH2 pozostawia sinus na obu.
Potwierdzono więc wspólne źródło AFG CH1. Asymetria tłumienia LPC wymaga
ustalenia rozgałęzienia/impedancji toru i osobnego pomiaru bez drugiej gałęzi.
Nie przypisujemy jej automatycznie uszkodzeniu FMC.
CH2–CH4 każdej FMC wymagają przełożenia przewodów do fizycznego pomiaru
terminacji i gain toru BNC. Dotychczasowe testy ich DAC nie mierzą impedancji BNC.

## Terminacja cyfrowa LVDS i gain kalibracyjny

FPGA `DIFF_TERM=TRUE` na 22 parach obu FMC (dane, frame, DCO i trigger),
ustalony w bitstreamie openXC7. Nie jest to terminacja analogowa BNC.
LTC2174 A2 = `0x00` na obu kartach: źródłowa terminacja LVDS OFF,
normalny prąd drivera 3,5 mA. Nie włączamy równocześnie źródłowej
terminacji ADC. Fizyczne testy odbiornika oraz ON/OFF/ON były wcześniej
zapisane w `docs/hr-diff-term.md` i wynikach dual ADC.

Golden CERN ma dodatkową cyfrową korekcję `(sample + offset) * gain`,
Q1.15, unity `0x8000`, z saturacją (`hdl/adc/rtl/offset_gain_s.vhd`).
Nasz snapshot gateware zwraca surowe 14-bitowe dane: ta korekcja,
kalibracja EEPROM i kompensacja temperaturowa nie są jeszcze zaimplementowane.
Nie ma dodatkowej ciągłej regulacji analogowego PGA między trzema zakresami.

## Powtórzenie

Najpierw zatrzymane oba ADC (`control=1`, SSR=0). Skonfiguruj AFG:

```sh
python3 tools/configure_afg_sine.py --lab-repo /home/codex-hil/lab-instruments \
  --url https://192.168.2.36:8840 \
  --token-file build/zc706-afg/ssh/gateway.token \
  --ca-file build/zc706-afg/ssh/gateway-ca.crt \
  --vpp .05 --output build/zc706-afg/range-generator
```

Na ZC706, z pasującym `csr.json` oraz skryptami z `tools/`:

```sh
python3 check_adc_ranges.py --csr-json csr.json --output adc-ranges
```

Po pobraniu danych:

```sh
python3 tools/environment.py python3 tools/analyze_adc_ranges.py adc-ranges
python3 tests/adc_input_settings_test.py
```

`check_adc_loads.py` wykonuje macierz obciążeń CH1 obu kart w zakresie ±5 V.
Każde uruchomienie trenuje pełne IDELAY **i bitslip**; same zapisane taps
nie odtwarzają deserializera po resecie. Eksperyment ze skróconym treningiem
odrzucono ze względu na uszkodzone słowa HPC; nie użyto go do wniosków.

Po testach przywrócono AFG 1 MHz/1 Vpp High-Z, oba wyjścia ON;
oba ADC zatrzymane, SSR=0, DAC clear aktywny, A2=0, A3=0, błędy=0.
Nie zmieniono bitstreamu, VADJ, EEPROM ani konfiguracji zegarów.
