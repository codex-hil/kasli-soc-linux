# Jedna CERN FMC ADC na ZC706 — gateware PoC

Target: ZC706 rev. 1.2, XC7Z045-2FFG900C, **J5 LPC**, jedna
OHWR/CERN FMC ADC 100M 14b 4cha (LTC2174-14).
Użytkownik potwierdził świeżą produkcję, rewizję karty **v6.1**.
Wszystkie używane pary ADC i zegar DCO leżą w banku HR 10. Pełna mapa pochodzi z przypiętego
upstream CERN i audytu `evidence/zc706/fmc-adc-pin-audit-20261007.json`.
Ten target zachowuje działający PS7/UART/Ethernet z naszego ZC706.
Most LiteX Wishbone→CSR ma włączony upstreamowy tryb registered,
żeby rozdzielić długą ścieżkę AXI address/decode od większej liczby CSR.

**Build i fizyczny test czterokanałowego snapshotu: PASS, bez Vivado.**
VADJ 2.5 V zmierzone na C605; karta v6.1 w J5 LPC. Potwierdzone SPI,
I²C SI570, 100 MS/s, odbiór 34 wzorców (139264 wartości kanałów) oraz
snapshot 1024 próbek z wyłączonym wzorcem. Wejścia pozostają odłączone;
nie jest to pełna walidacja parametrów analogowych. ADC i PL DDR nadal niezależne.

**Wewnętrzny offset DAC → ADC: PASS.** Cztery kanały, wszystkie trzy zakresy,
933888 wartości; cyfrowy wzorzec wyłączony. [Opis i wykresy](zc706-adc-offset.md).

Rozwiązano dwa problemy: dostęp MMIO musi być wyrównanym słowem 32-bit,
a łącze LVDS wymaga terminacji. Dodaliśmy izolowaną łatkę nextpnr i overlay
bazy Project X-Ray, które emitują rzeczywiste `DIFF_TERM` w bankach HR.
Aktualny test fizyczny przechodzi z terminacją FPGA i `A2=0` w ADC.
Wcześniejszy zwalidowany release pozostaje dostępny: używał terminacji
wewnętrznej ADC (`A2=0xf0`) i nie miał terminacji FPGA.
Szczegóły pomiaru bitów i testu A/B: [hr-diff-term.md](hr-diff-term.md).
Dodatkowo każda linia danych ma własny trening IDELAY i BITSLIP.
Nowy licznik potwierdza zegar deserializacji około 400 MHz, objęty także
jawnym constraintem 2.5 ns. Sygnatura GP0 jest sprawdzana w U-Boot,
przed startem Linux, a test Linux używa `/dev/uio0`.

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
o rewizji karty. PL I²C po poprawce MMIO również uzyskuje ACK tego multipleksera.
Dowody: `evidence/zc706/fmc-adc-bringup-20261008/`.

**Aktualizacja: wcześniejsze NACK/`0xff` rozwiązane.** Driver używa teraz
natywnych, wyrównanych dostępów `ctypes.c_uint32` do MMIO. ARM-owy
`struct.pack_into('<I')` wykonuje zapisy bajtowe (`strb`, potwierdzone
disassembly naszego CPython 3.14.8), które zakłócały bitbang przez CSR.
Po zmianie: multiplekser ACK, ADC register 1 = `0x20`, SI570 odczytany.
PS→PL i PL→PS przekazywanie poziomów I²C potwierdzono niezależnie przez
chwilowe przełączenie MIO50/51 na GPIO; rejestry przywrócono.
Wcześniejsze błędy wzorców rozwiązano terminacją ADC i treningiem linii;
poniżej zapisano eksperymenty oraz dowody fizycznego PASS.

Niezależny audyt RapidWright 2026.1.1-beta potwierdził wszystkie 350 mapowań
pin → site → tile: 200 istniejących IOB i 150 dodanych w naszej nakładce.
Wynik i hashe bazy/JAR są w `package-audit*.json` w katalogu dowodów.
`tools/audit_xc7z045_package.py` odtwarza porównanie przez Jython RapidWright.
RapidWright służy wyłącznie do audytu, bez wywoływania Vivado; build
Yosys/nextpnr/openXC7 nie wymaga go.

Dokumentacja CERN wskazuje v6.1 jako EDA-02063-V6-1. Lista zmian v6.0→v6.1
opisuje wymianę 16 kondensatorów i zastąpienie L8 zworą 0 Ω dla stabilności
zasilania; nie opisuje zmiany interfejsu cyfrowego. Pełny schemat v6.1
pozostaje do pozyskania z EDMS:
https://edms.cern.ch/nav/EDA-02063-V6-1 . Źródło listy zmian:
https://gitlab.com/ohwr/project/fmc-adc-100m14b4cha-hw/-/wikis/v6_0_to_v6_1 .

Element | Status
---|---
Yosys | PASS, 9 ISERDESE2 / 9 IDELAYE2 / 2 RAMB36E1
nextpnr / routing | PASS
Timing logiki sys/ADC/IDELAY | PASS przy 100/100/200 MHz; serial 400 MHz
FASM / openXC7 bitstream | PASS
Frame/BITSLIP i lane ordering | PASS, model protokolarny
Snapshot / CDC / trigger / error injection | PASS, symulacja
AXI / CSR / reset | Symulacja PASS; fizyczna sygnatura PASS po konfiguracji przed kernelem; reset/reconfiguration nadal niestabilne
SPI | PASS na hardware po użyciu natywnych dostępów MMIO 32-bit
VADJ / karta / oko LVDS / akwizycja | PASS: 2.5 V, LPC, kalibracja 8 linii, 34 wzorce, snapshot 1024 próbek; analog bez walidacji
EEPROM calibration / DMA / druga karta | nie zaimplementowano

Dowody: `evidence/zc706/fmc-adc-build-20261007.json`;
mapa wynikowego SoC: `evidence/zc706/fmc-adc-csr.json`.
Testy RTL nie potwierdzają elektryki ani marginesu czasowego LVDS.
PoC zapisuje krótkie czterokanałowe rekordy; nie jest jeszcze portem pełnego
sterownika CERN, DMA ani aplikacji oscyloskopowej używanej na SPEC.

Archiwalna paczka sprzed bring-upu: [GitHub prerelease](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-fmc-adc-j5-20261007), commit `ca4c1fc`.

## Build

Z czystego checkoutu, na Linux z Dockerem i Pythonem 3:

```sh
make bootstrap BOARD=zc706
make adc-test
make adc-pl
python3 tools/environment.py python3 tools/test_adc.py --soc
```

Zdalny start PL przed kernelem (host Python wymaga pyserial):

```sh
python3 tools/boot_adc_jtag.py --host AKTUALNY_ADRES_IP
python3 tools/test_adc_hardware.py --host NOWY_ADRES_IP
```

Pierwszy skrypt synchronizuje działający Linux, resetuje PS, zatrzymuje
U-Boot, ładuje PL przez wskazany adapter JTAG i sprawdza sygnaturę przy
100 MHz, następnie bootuje istniejący kernel/DTS/rootfs z SD i wypisuje
nowy adres DHCP. Bez `saveenv`, zapisu obrazu SD i QSPI. Test fizyczny
tej sekwencji przeszedł (`automated-boot.json`).

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
adc | 0x40001000 | control, arm, status, frame, count, captured, errors, read_address, data_low/high, ssr, tap0..8, live/raw, serial_count, slip_toggle
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
3. Skanuje opóźnienie ramki, potem opóźnienia 8 linii danych 0..31.
   Trenuje BITSLIP każdej linii dwoma asymetrycznymi wzorcami; wymaga
   okna co najmniej trzech tapów i wybiera jego środek. Starszy PL bez
   CSR `slip_toggle` zachowuje wcześniejszy wspólny skan.
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

### Bezpośredni odczyt odbiornika — 2026-10-08

Karta fizyczna: v6.1 (informacja użytkownika). Dodano `adc_live_low` i
`adc_live_high`: dwie synchronizowane części słowa odbiornika przed BRAM.
Służą wyłącznie diagnostyce stałych wzorców; nie zapewniają spójnej akwizycji
zmiennych danych. `tools/diagnose_adc_live.py` porównuje 19 wzorców przed
pamięcią i w snapshotach 1024 próbek. Fizyczny test nowego bitstreamu
wykazał te same błędy w obu miejscach: walking-one daje zero; wzorce
0x1555/0x2aaa dają 0x5555/0xaaaa zamiast 0x5554/0xaaa8.
Błąd występuje przed pamięcią snapshot. Nie zaliczamy akwizycji ADC.
Dowód: `evidence/zc706/fmc-adc-bringup-20261008/live-vs-bram.json`.
Build Yosys/nextpnr/openXC7 przeszedł timing; boot z JTAG przed kernelem
i Linux/SSH przeszły. Nie zapisano SD/QSPI.

### Terminacja i trening osobnych linii — 2026-10-08

Eksperyment A/B na identycznym PL: `A2=0x00` (3.5 mA bez terminacji)
i `0x40` (4.5 mA bez terminacji) gubiły walking-one. `0xf0` włączyło
terminację wewnętrzną ADC i poprawiło wszystkie badane wzorce.
Następnie pełny test na tym PL przeszedł 139264 porównania oraz snapshot.
Źródło konfiguracji: [datasheet LTC2174, rejestr A2, str. 27](https://www.analog.com/media/en/technical-documentation/data-sheets/21754314fa.pdf).
Nie włączamy TERMON przy ustawieniu prądu 3.5/4/4.5 mA.

Analiza przypiętego nextpnr `c68c13582e972292c86a5025140d52e713384cbc`
potwierdza brak obsługi parametru `DIFF_TERM` w writerze FASM. Wszystkie
11 IBUFDS mają ten parametr TRUE w netliście, lecz nie powoduje on
konfiguracji terminacji. Przyczynę elektryczną wnioskujemy z kodu i testu
A/B; nie wykonano pomiaru oscyloskopem. Terminacja ADC jest obecnie
sprawdzonym obejściem; dodanie prawidłowej terminacji odbiornika do
openXC7 pozostaje osobnym zadaniem.

Nowy build z diagnostyką ujawnił różne przesunięcia słów na liniach.
Skan z nieruchomą ramką i surowym odczytem wykazał potrzebę niezależnego
IDELAY/BITSLIP. Po dodaniu CSR toggle-mask i treningu każdy z 8 torów
ma stabilne okno 14–15 tapów, a pełny test przechodzi. Nie zapamiętujemy
na sztywno tapów ani liczby BITSLIP: inicjalizacja trenuje je ponownie.
`--tap` omija skan opóźnień, ale nadal trenuje BITSLIP i sprawdza wzorce.

Dodatkowe CSR (ABI 1, dopisane bez przesunięcia istniejących adresów):

CSR | Adres | Znaczenie
---|---|---
adc_live_low/high | 0x40001050 / 0x40001054 | steady word przed BRAM
adc_raw_low/high | 0x40001058 / 0x4000105c | 8 surowych bajtów B,A dla kanałów 1..4
adc_raw_frame | 0x40001060 | surowy bajt FR
adc_serial_count | 0x40001064 | licznik SYS zboczy narastających IOCLK/32; różnica ×32 daje IOCLK
adc_slip_toggle | 0x40001068 | zmiana każdego bitu generuje BITSLIP na odpowiedniej linii danych

Odczyty live/raw są wyłącznie do stałych wzorców; nie gwarantują spójności
zmiennych danych. Maskę slip zmieniaj dopiero po wyrównaniu ramki,
z przerwą co najmniej 1 ms między poleceniami w naszym sterowniku.
Dowody i hashe: `evidence/zc706/fmc-adc-bringup-20261008/`.

Powtórka po drugim pełnym resecie PS i konfiguracji JTAG: PASS.
Ponownie 139264 wartości kanałów, 1024 próbki, te same centra tapów;
serial clock 399999250 Hz, ADC A1=0x20 / A2=0xf0.
Nowa paczka: [fizycznie sprawdzony target](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-fmc-adc-validated-20261008).
Paczka dołącza wynik hardware tylko gdy hashe bitstreamu i sterownika
pasują do ostatniego fizycznego PASS. Pole `hardware_validated=false`
w build-manifest jest stanem przy budowaniu; dowód fizyczny znajduje się
w `evidence/hardware/validation.json`.
Opcjonalny skrypt SD zawiera teraz sprawdzoną sekwencję FCLK0/reset/level
shifters; sam wariant bootowania ADC z SD nie był wykonywany na płycie.
Walidowana ścieżka to `tools/boot_adc_jtag.py` i Linux z istniejącej SD.

## Druga karta HPC

Opcjonalny target dwóch kart i niezależna akwizycja w J4 HPC:
[zc706-adc-dual.md](zc706-adc-dual.md). Target jednej karty pozostaje dostępny.
