# Jedna CERN FMC ADC na ZC706 — gateware PoC

Target: ZC706 rev. 1.2, XC7Z045-2FFG900C, **J5 LPC**, jedna
OHWR/CERN FMC ADC 100M 14b 4cha (LTC2174-14). Wszystkie używane pary
ADC i zegar DCO leżą w banku HR 10. Pełna mapa pochodzi z przypiętego
upstream CERN i audytu `evidence/zc706/fmc-adc-pin-audit-20261007.json`.
Ten target zachowuje działający PS7/UART/Ethernet z naszego ZC706.
Most LiteX Wishbone→CSR ma włączony upstreamowy tryb registered,
żeby rozdzielić długą ścieżkę AXI address/decode od większej liczby CSR.

**Build bitstreamu: PASS, bez Vivado. VADJ: użytkownik zmierzył 2.5 V na C605. Karta jest w J5 LPC; bring-up trwa, akwizycja niepotwierdzona.**

2026-10-08: fizycznie potwierdzono zegar próbek około 100 MHz i frame
`0x0f` we wcześniejszym wariancie. ADC SPI zwraca jednak `0xff` zamiast
oczekiwanego `0x20`; SI570 nie odpowiada. Nowy wariant dodaje I²C płyty
oraz wspólny jawny BUFG dla GP0 ACLK i logiki CSR. Netlist i symulacja
przechodzą. Sygnatura PL `0x4b534f43` jest odczytywana w U-Boot przy
50/100 MHz i w Linux po załadowaniu PL przed kernelem.

Przeprogramowanie PL przez JTAG podczas pracy Linux powodowało blokadę
CPU na pierwszym odczycie GP0; przyczyna sekwencji resetu pozostaje otwarta.
Na tym etapie ładuj ADC PL przed startem kernela. Test hosta
`python3 tools/test_adc_hardware.py --host ADRES_IP` zbiera wyniki już
uruchomionego targetu; opcja `--program` jest zablokowana.
Diagnostyka `tools/diagnose_fmc_board.py` tylko odczytuje presence/FRU
i chwilowo wybiera kanał multipleksera, po czym przywraca jego stan.
Nie zmienia VADJ, GPIO zasilania ani zawartości EEPROM.

Niezależny kontroler PS I²C w U-Boot potwierdził ACK multipleksera
`0x74`, wejścia U16 `00 8c` (LPC obecna, HPC pusta), oraz ACK EEPROM
LPC `0x50`. Pierwsze 128 bajtów EEPROM to `0xff`; nie ma informacji FRU
o rewizji karty. PL I²C nadal nie uzyskuje ACK tego samego multipleksera.
Dowody: `evidence/zc706/fmc-adc-bringup-20261008/`.

Element | Status
---|---
Yosys | PASS, 9 ISERDESE2 / 9 IDELAYE2 / 2 RAMB36E1
nextpnr / routing | PASS
Timing logiki sys/ADC/IDELAY | PASS przy 100/100/200 MHz
FASM / openXC7 bitstream | PASS
Frame/BITSLIP i lane ordering | PASS, model protokolarny
Snapshot / CDC / trigger / error injection | PASS, symulacja
AXI / CSR / reset | PASS, symulacja nowego SoC
SPI | PASS, model slave; fizyczny readback oczekuje
VADJ / karta / oko LVDS / akwizycja | VADJ 2.5 V zmierzone przez użytkownika; pozostałe oczekują
EEPROM calibration / DMA / druga karta | nie zaimplementowano

Dowody: `evidence/zc706/fmc-adc-build-20261007.json`;
mapa wynikowego SoC: `evidence/zc706/fmc-adc-csr.json`.
Testy RTL nie potwierdzają elektryki ani marginesu czasowego LVDS.
PoC zapisuje krótkie czterokanałowe rekordy; nie jest jeszcze portem pełnego
sterownika CERN, DMA ani aplikacji oscyloskopowej używanej na SPEC.

Gotowa paczka: [GitHub prerelease](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-fmc-adc-j5-20261007), commit `ca4c1fc`.

## Build

Z czystego checkoutu, na Linux z Dockerem i Pythonem 3:

```sh
make bootstrap BOARD=zc706
make adc-test
make adc-pl
python3 tools/environment.py python3 tools/test_adc.py --soc
```

Środowisko i wersje narzędzi są przypięte w `tools/environment.py`,
`sources.lock.json`, `requirements.lock` i `toolchains.lock.json`.
Vivado nie jest częścią buildu. Wyniki:

* `build/zc706-adc/gateware/gateware/top.bit`: bitstream.
* `build/zc706-adc/gateware/csr.json`: wygenerowana mapa rejestrów.
* `build/zc706-adc/gateware/gateware/manifest.json`: hash i polecenia buildu.
* `build/zc706-adc/gateware/gateware/stage{0,1,2,3}.log`: kolejne etapy.
* `build/zc706-adc/tests/`: logi symulacji.

Dotychczasowy probe i obraz SD pozostają w osobnym `build/zc706/`.
Nie zastępuj automatycznie bitstreamu ładowanego przez działający U-Boot.

Opcjonalna paczka bitstreamu, drivera, mapy CSR, logów i skryptu SD:
`make linux BOARD=zc706` (narzędzie mkimage), następnie `make adc-package`.
Wynik: `build/zc706-adc/zc706-fmc-adc-j5.tar.xz` z `SHA256SUMS`.

Na kopii sprawdzonej karty SD ZC706 umieść `adc-j5.bit` i `adc-j5.scr`
na partycji FAT obok dotychczasowych plików. Po sprawdzeniu karty/VADJ
przerwij autoboot U-Boot i uruchom:

```sh
load mmc 0:1 ${scriptaddr} adc-j5.scr
source ${scriptaddr}
```

Skrypt załaduje alternatywny PL i uruchomi istniejący Linux/DTS/rootfs.
Bez `saveenv`; standardowy `boot.scr` i `top.bit` pozostają dostępne.
Ten sposób ładowania nowego targetu oczekuje na test fizyczny.

## Odbiornik i bufor

LTC2174 działa w trybie dwóch linii na kanał, 16-bit serialization,
100 MS/s. DCO ma 400 MHz; odbiór DDR daje osiem bitów na linię.
IBUFDS → IDELAYE2 → ISERDESE2 odbiera osiem linii danych oraz FR.
MMCM generuje spójne fazowo zegary 400 i 100 MHz, rozprowadzane przez
dwa BUFG (wariant NETWORKING opisany w UG471).
Drugi MMCM z FCLK0 100 MHz dostarcza niezależne 200 MHz do IDELAYCTRL.
Reset odbiornika jest zwalniany po RDY i LOCKED.

FR `0x0f` steruje automatycznym BITSLIP. Dopiero osiem poprawnych słów
ustawia aligned. Dane są przeplatane B/A zgodnie z referencją CERN,
po cztery 16-bit słowa na próbkę, dwie najmłodsze pozycje równe zero.
Zachowano referencyjną konwencję polaryzacji DCO/FR; nie odwracamy jej
ponownie na podstawie nazw pinów schematu.

Snapshot zawiera 1024 × 64 bity (10.24 µs przy 100 MS/s), przechowywane
w dwóch RAMB36E1. Arm jest przenoszony między domenami jako toggle;
wynik pozostaje zamrożony do następnego arm. Licznik przechodzi przez
CDC w kodzie Graya. Liczba próbek i błędów są odczytywane po ack i
ustaleniu utrzymywanego wyniku. Wyzwalanie programowe albo zboczem
zewnętrznego triggera, zsynchronizowanego do domeny próbek.
Nie jest to pretrigger; nie gwarantujemy rozdzielczości triggera poniżej
jednego okresu próbkowania.

SPI obsługuje ADC i cztery DAC offsetu; SI570 ma I²C z open-drain.
SSR domyślnie odłącza wejścia; termination 50 Ω pozostaje wyłączone.
Po konfiguracji wszystkie DAC dostają nominalne zero `0x8000`.
Kalibracja analogowa z EEPROM nie jest jeszcze przeniesiona.

## AXI / CSR

GP0 → LiteX Wishbone → CSR, bazowy region UIO 0x40000000 / 64 KiB.
Dokładne adresy każdego rejestru są w generowanym `csr.json`.

Blok | Baza | Zawartość
---|---|---
probe | 0x40000800 | dotychczasowy scratch, counter, signature
adc | 0x40001000 | control, arm, status, frame, count, captured, errors, read_address, data_low/high, ssr, tap0..8
adc_spi | 0x40001800 | upstream LiteX bitbang SPI
adc_i2c | 0x40002000 | upstream LiteX bitbang I²C

Control: bit 0 reset, bit 1 SI570 OE, bit 2 trigger zewnętrzny,
bit 3 zwolnienie DAC CLR, bity 4..7 wybór DAC CS.
Status: bit 0 IDELAY ready, bit 1 aligned, bit 2 busy, bit 3 done,
bit 4 błąd zarejestrowany w ostatnim rekordzie.
Tap0..7 dotyczą danych, tap8 FR; zakres 0..31.
ABI ADC=1; sygnatura starego probe pozostaje `0x4b534f43`.

## Pierwszy test na sprzęcie

Przed montażem wyłącz płytę. Sprawdź rewizję karty i wymagane napięcie
I/O; referencja CERN używa **LVDS_25/LVCMOS25 i VADJ 2.5 V**.
VADJ jest wspólne dla obu FMC. Nie ustawiaj 1.8 V na podstawie samego
określenia LVDS. Ten bitstream zakłada 2.5 V, które trzeba zmierzyć.
Pomiar użytkownika z 2026-10-08: **2.5 V na C605**. Schemat ZC706
rev. 1.2, arkusz 14, potwierdza C605 między VADJ_FPGA i GND.
[Zapis pomiaru](../evidence/zc706/vadj-20261008.json).
Karta powinna być w J5 LPC. Najpierw bez zewnętrznego źródła analogowego.

Po bezpiecznym załadowaniu bitstreamu do działającego Linuksa skopiuj
`csr.json` i `tools/fmc_adc.py` na płytę, następnie:

```sh
sudo python3 fmc_adc.py --csr-json csr.json --device /dev/uio0 --output adc-evidence
```

Alternatywnie `--device /dev/mem`. Skrypt:

1. Sprawdza sygnaturę PL, inicjalizuje ADC i weryfikuje SPI readback.
2. Odczytuje SI570 (adres domyślny 0x55) i mierzy częstotliwość próbek.
3. Skanuje wspólne opóźnienie 0..31 dwoma asymetrycznymi wzorcami,
   wymaga okna co najmniej trzech tapów i wybiera jego środek.
4. Sprawdza 34 wzorce, w tym walking-one/zero: 139264 wartości kanałów.
5. Zapisuje cztery kanały do `samples.bin`, `samples.csv` i `result.json`.
6. Odłącza wejścia, resetuje odbiornik i wyłącza OE także po błędzie.

`--tap N` pozwala wybrać opóźnienie ręcznie, lecz nadal wykonuje test wzorców.
`--range 5V` włącza najszerszy zakres do pierwszego testu analogowego;
pozostałe to `0.5V` i `0.05V`. Domyślnie `open`.
`--external-trigger` czeka na następne zbocze (timeout 2 s).
CSV zawiera signed 14-bit codes, **nie skalibrowane wolty**.

Skrypt wymaga fabrycznej konfiguracji SI570 100 MHz; nie przelicza jeszcze
częstotliwości SI570 z nieznanego oscylatora. Błędną częstotliwość zgłasza
jako FAIL. Wynik sprzętowy nie jest oznaczony PASS bez faktycznego testu.

## Poprawki openXC7 i ograniczenia

Przypięta baza XC7Z045 FFG900 pomija 150 pinów HR banków 11–13.
Są one potrzebne do sterowania kartą, mimo że sam ADC jest w banku 10.
`tools/adc_chipdb.py` tworzy oddzielną bazę dla tego targetu:

* stałe mapowanie w `patches/xc7z045-ffg900-missing-hr.csv` pochodzi z
  XC7Z035 FFG900 i zostało porównane z oficjalnym pinoutem XC7Z045;
* istniejące IOB FFG900 są rekonstruowane i porównywane z bazą binarną;
* dopisywane są tylko wpisy package oraz string IDs (schema 6);
* routing, timing, site/bel i pozostałe packages pozostają bez zmian;
* hashe/proweniencja trafiają do osobnego `chipdb/manifest.json`.

Pełny generator XC7Z045 przekroczył RAM hosta (SIGKILL). Uzupełnienie samych
wpisów package ma małe wymagania pamięci i nie zmienia upstreamów.
Metadane Zynq7 nie zawierają BUFR. Wariant BUFIO + MMCM miał nieroutowalne
rozgałęzienie DCO w przypiętym flow. Dlatego CLK i CLKDIV używają wyjść
jednego MMCM przez BUFG. Nieużywane wejścia kaskady i zegara pamięci
ISERDES pozostają niepodłączone; próba routowania stałych do tych
dedykowanych wejść również kończyła się błędem.
Timing raportowany przez nextpnr nie zastępuje pomiaru fizycznego oka ADC.
Test odbiornika używa modeli **protokolarnych** prymitywów, bez symulacji
opóźnień analogowych, MMCM jittera ani IDELAY.

Źródła: [CERN gateware](https://gitlab.com/ohwr/project/fmc-adc-100m14b4cha-gw),
[CERN software](https://gitlab.com/ohwr/project/fmc-adc-100m14b4cha-sw),
[LTC2174 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/21754314fa.pdf),
[ZC706 UG954](https://docs.amd.com/api/khub/documents/m4fPXowvxKd5JZRfe046WQ/content).
