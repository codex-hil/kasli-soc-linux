# Kasli-SoC Linux / LiteX / openXC7

Prace trwają. **Milestone 1 Kasli-SoC nie został potwierdzony na hardware.**
Repo jest oddzielone od upstream ARTIQ; checkouty `upstream/` pozostają bez zmian.

**Fizyczna ZC706 rev. 1.2:** BootROM → upstream U-Boot SPL → U-Boot →
openXC7 PL → Linux 6.18.40 / Buildroot działa z SD bez JTAG i Vivado.
UART, Ethernet 1 Gb/s, DHCP i SSH działają. Testy AXI/CSR przez `/dev/mem`
i `/dev/uio0` przeszły po 10036 zapisów/odczytów; licznik ma ~100 MHz.
DDR naszego Linuksa przeszedł `memtester 128M 3` i dodatkową pętlę na
finalnym obrazie. Pełny zapis/odczyt SD i końcowy zestaw testów są PASS.
Fizyczna Kasli-SoC nadal oczekuje na walidację.

## CERN FMC ADC na ZC706

Dodany target dla **jednej karty w J5 LPC**: cztery kanały,
odbiornik ISERDES, snapshot 1024 próbek, SPI/I²C i automatyczny test wzorców.
Build: `make bootstrap BOARD=zc706`, `make adc-test`, `make adc-pl`.
Karta jest w J5 LPC, VADJ 2.5 V zmierzone. Bring-up trwa: zegar/frame
potwierdzone, SPI/I²C i fizyczna akwizycja pozostają niewalidowane.
Opis, mapa CSR i ograniczenia: [docs/zc706-fmc-adc.md](docs/zc706-fmc-adc.md).

## Hardware i źródła prawdy

Platforma Migen `migen/build/platforms/sinara/kasli_soc.py`: **XC7Z030-FFG676-3**,
LED AF19/AF23 LVCMOS25. Dodatkowe piny PS/DDR:
`migen-axi/src/migen_axi/platforms/kasli_soc.py`.
Target ARTIQ: `artiq-zynq/src/gateware/kasli_soc.py`.
Rewizja fizycznego egzemplarza nie jest jeszcze ustalona. Platforma Migen deklaruje
stopień -3; aktualny schemat ma symbol XC7Z030-2FFG676I. Routing -1 jest
konserwatywny dla obu, lecz oznaczenie zamontowanego układu wymaga potwierdzenia.

Inicjalizacja PS pochodzi z **M-Labs zynq-rs SZL**, nie z nowego presetu Vivado:

* PS_CLK 33 333 333 Hz: `libboard_zynq/src/clocks/source.rs`.
* ARM 1 GHz i IO PLL 1 GHz: `szl/src/main.rs`.
* DDR3L: golden kod opisuje MT41K256M16HA-125:E, pracuje w **16-bit**,
  wyłącza slice 2/3 i udostępnia **512 MiB**, zegar 533 333 333 Hz:
  `libboard_zynq/src/ddr/{mod,regs}.rs`. SZL wykonuje konfigurację kontrolera,
  IOB i kalibrację; tych wartości nie zmieniamy. Schemat prowadzi 32 linie
  do dwóch MT41K256M16TW-107:P (łącznie 1 GiB fizycznie), lecz Linux korzysta
  z konserwatywnego obszaru udostępnianego przez golden loader.
* UART1 115200 8N1, TX MIO48 / RX MIO49, bank 1.8 V:
  `libboard_zynq/src/uart/mod.rs` i `stdio.rs`. PL serial Y18/AA18 to inne piny.
* SD0 MIO40–45, card detect MIO46: `libboard_zynq/src/sdio/mod.rs`.
* GEM0 RGMII MIO16–27, MDIO MIO52/53, reset PHY GPIO MIO47:
  `libboard_zynq/src/eth/mod.rs`. Schemat `Kasli-SOC_ETH_PHY.SchDoc`
  potwierdza Marvell 88E1512 i zawiera uwagę **"PHY MDIO address is 0"**.
* Reset i level shifters: `slcr.rs::init_preload_fpga/init_postload_fpga`.
* QSPI: w przejrzanym upstream schemacie brak kości QSPI NOR; SZL obsługuje
  boot SD/JTAG. Nie zakładamy istnienia bootloadera QSPI.
* USB: złącze służy FT4232H (JTAG/UART/I²C/POR), nie znaleziono PHY ULPI
  dla kontrolera USB PS. PS USB pozostaje wyłączone.
* GTX/SFP, zegary RTIO i EEM nie są potrzebne do minimalnego PL.

Commity źródeł znajdują się w `sources.lock.json`. Projekt korzysta z
[LiteX Zynq7000](https://github.com/enjoy-digital/litex/blob/master/litex/soc/cores/cpu/zynq7000/core.py)
i [openXC7](https://github.com/openXC7/toolchain-nix).

## Mapa przeniesienia

ARTIQ/Migen element | LiteX/openXC7 odpowiednik | Status
---|---|---
Sinara Kasli-SoC platform/LED | mała lokalna platforma `gateware/kasli_soc.py` | elaboracja działa
zynq-rs SZL PS/DDR/MIO | ten sam loader, dodana konfiguracja FCLK0 | make szl PASS
Migen-AXI PS7 | upstream LiteX Zynq7000 / natywny prymityw PS7 | synteza działa
ARTIQ AXI/CSR | GP0 → upstream AXI3/Wishbone bridge → LiteX CSR | PL zbudowany, hardware oczekuje
Vivado place-and-route | Yosys → nextpnr openXC7 → FASM → X-Ray bitstream | build eksperymentalny działa
ARTIQ runtime | upstream U-Boot → upstream Linux → Buildroot | obraz SD zbudowany
ARTIQ RTIO/DRTIO | późniejszy PoC | nie rozpoczęto

## Architektura i boot

PS7 GP0 → AXI3 → LiteX Wishbone → CSR, FCLK0 100 MHz → `sys`.
Scratch i licznik 32-bit, sygnatura `0x4b534f43`, LED AF19 z bitu 25 licznika.
Pełna mapa jest generowana jako `build/gateware/csr.json`:

Rejestr | Adres | Dostęp
---|---|---
scratch | 0x40000800 | RW
counter | 0x40000804 | RO
signature | 0x40000808 | RO

Wybrany boot flow: BootROM SD → SZL → PL → U-Boot → Linux/rootfs.
U-Boot remapuje OCM na górę przestrzeni adresowej i udostępnia DDR od 0
(`arch/arm/mach-zynq/cpu.c::arch_cpu_init`). UART/SD zachowują MIO z SZL.
U-Boot nie ma sterownika pinctrl Zynq7000; Ethernet MIO inicjalizuje Linux.
Wspólny DTS używa bazowego `zynq-7000.dtsi` z przypiętych źródeł upstream;
w buildzie U-Boot bazowy plik pochodzi z jego `dts/upstream`, ponieważ
stary plik `arch/arm/dts` nie zawiera węzła pinctrl.
SZL ładuje payload pod 0x00100000; U-Boot trzeba zlinkować zgodnie z tym adresem.
SZL pozostaje źródłem konfiguracji DDR/MIO. Mały patch dodaje FCLK0:
IO PLL / 10 / 1. Linux musi utrzymać ten zegar aktywny.
Nie wykonano żadnego programowania QSPI ani operacji na karcie SD.
Przełączniki boot mode należy ustawić według dokumentacji fizycznej rewizji.
Powrót do ARTIQ: dotychczasowa karta/tryb boot; istniejące artefakty pozostają zachowane.

## Build i struktura

* `gateware/`: minimalna platforma i SoC zgodne z API LiteX.
* `tools/pl_test.py`: hardware test wzorców, walking-one, losowych zapisów,
  sygnatury i częstotliwości licznika; przywraca początkowy scratch.
* `tools/hardware_test.py`: ping, SSH, memtester 128 MiB × 3, PL, dump PS7;
  zapisuje osobne logi i nie oznacza milestone jako zakończony bez audytu UART/boot.
* `tools/capture_uart.py`: przechwycenie wskazanego UART 115200 bez wysyłania znaków.
* `tools/dump_ps7_state.py`: odczyt SLCR/DDRC z `/dev/mem`, JSON i porównanie.
  Nie czyta FIFO. Dla ARTIQ potrzebny jest jeszcze transport JTAG lub integracja dumpu.
* `upstream/`, `.venv/`, `build/`: ignorowane katalogi robocze.
* `evidence/`: dowody z buildów; nie są dowodami działania fizycznej płyty.

Droga od czystego checkoutu (Docker + Python3 + Git na hoście, x86_64 Linux):

```sh
make image
```

`make image` kolejno przygotowuje przypięty Debian z datowanym snapshotem APT,
pobiera źródła z `sources.lock.json`, sprawdza SHA-256 paczek FPGA, instaluje
lokalne zależności Python i Rust, buduje PL, SZL, U-Boot, kernel i rootfs,
a następnie składa `build/buildroot/images/sdcard.img` i manifest SHA-256.
Etapy można uruchamiać osobno: `make bootstrap`, `make pl`, `make test-pl`,
`make szl`, `make linux`. Bootstrap, PL, test PL i SZL przeszły przez tę ścieżkę.
U-Boot, Linux 6.18.40, rootfs i składanie obrazu również przeszły; pełny przebieg
`make image` zakończył się kodem 0. Obraz ma 335 544 832 bajty.
Kontener ma zapisywalne `/usr` i `/var` na woluminie projektu w `build/environment/`,
więc instalacja zależności nie zapełnia partycji systemowej hosta.
Do diagnostyki elaboracji można też użyć lokalnego środowiska Python:
`.venv/bin/python gateware/kasli_soc.py`.

Pakiety FPGA użyte w pierwszym eksperymencie:
openXC7 release 2026-10-03, nextpnr c68c1358, prjxray-db a90f27c1;
OSS CAD Suite 2026-10-05, Yosys 0.69+190 / 0e8336b4e.
SZL wymaga Rust nightly-2026-03-25, rust-src i clang.
Buildy i większe zależności przechowujemy na dodatkowym woluminie, ponieważ
partycja systemowa ma mniej niż 1 GB wolnego miejsca.

## Walidacja

Yosys: CHECK 0 problemów. nextpnr: 143.84 MHz, PASS dla 100 MHz.
`make test-pl`: PASS dla 1000 transakcji AXI/CSR z opóźnionymi AW/W
i backpressure na B/R, sprawdzeniem ID, sygnatury, scratch i licznika.
Test symuluje netlistę po Yosys; PS7 jest blackboxem z pobudzanymi portami.
Nie sprawdza CPU, DDR, MIO ani fizycznego FPGA.
Powstał bitstream 5.8 MiB przez fasm2frames + xc7frames2bit, bez Vivado.
Obecna baza zawiera FBG676-1 zamiast FFG676-3; routing używa konserwatywnego
stopnia -1. Mapowanie obudowy jest sprawdzane z oficjalnymi pinoutami AMD;
nie wolno uznać samego powodzenia routingu za hardware validation.
Nowy nextpnr używa `--device` i `-o xdc=... -o fasm=...`; aktualny backend
LiteX generuje starsze argumenty. Adapter `tools/build_pl.py` używa nowego CLI i przeszedł pełny build.

Po uruchomieniu Linuxa:

```sh
python3 /usr/bin/pl_test.py --csr-json /etc/litex/csr.json --iterations 10000
python3 /usr/bin/dump_ps7_state.py > /tmp/ps7-linux.json
```

SSH, DHCP, ping, stabilność DDR i pełny test PS→PL jeszcze nie były wykonane.
Podłączone USB adaptery nie identyfikują Kasli-SoC; nie wysyłamy komend do
niezidentyfikowanych urządzeń.

Element | Status
---|---
PS7 | golden reference i SZL zbudowane; natywny PS7 zsyntezowany
DDR | konfiguracja zynq-rs znaleziona; hardware niebadany
UART | UART1/MIO48–49 ustalone; hardware niebadany
SD | obraz MBR/FAT/ext4 zbudowany; boot fizyczny niebadany
U-Boot | build PASS; entry 0x00100000; boot fizyczny niebadany
Linux | upstream 6.18.40 zbudowany; boot fizyczny niebadany
Ethernet | GEM0/88E1512/adres 0/reset ustalone; hardware niebadany
SSH | Dropbear i klucz w rootfs; połączenie fizyczne niebadane
AXI PS→PL | build PL przeszedł; hardware niebadany
LiteX CSR | mapa wygenerowana; 1000 transakcji w symulacji PASS; hardware niebadany
Yosys | synteza PASS
nextpnr-xilinx | routing i timing PASS, adapter nowego CLI działa
openXC7 bitstream | artefakt zbudowany; pinout aliasu zweryfikowany; hardware niebadany
ARTIQ RTIO PoC | oczekuje na milestone 1

## Obraz SD i pierwsze połączenie

Artefakt: `build/buildroot/images/sdcard.img`; sumy wszystkich payloadów:
`build/buildroot/images/manifest.json`. Bieżący manifest zapisano też w
`evidence/image-manifest.json`. To obraz bring-up, jeszcze niezweryfikowany na płycie.
Partycja 1: FAT 64 MiB, BOOT.BIN, zImage, DTB i extlinux.conf.
Partycja 2: ext4 256 MiB. Po identyfikacji właściwej, odmontowanej karty SD:

```sh
# Zastąp ścieżkę faktycznym identyfikatorem karty, bez sufiksu -partN.
sudo dd if=build/buildroot/images/sdcard.img of=/dev/disk/by-id/WLASCIWA_KARTA_SD bs=4M conv=fsync status=progress
```

UART: 115200 8N1, login `root`, puste hasło konsoli w tym PoC.
Ethernet pobiera adres przez DHCP. SSH dopuszcza klucz, hasła są wyłączone:

```sh
ssh -i build/ssh/id_ed25519 root@ADRES_Z_DHCP
python3 tools/hardware_test.py --help
```

Klucz prywatny pozostaje w ignorowanym `build/ssh`; bootstrap generuje nowy
dla nowego checkoutu. Nie publikuj go razem z obrazem. Test fizyczny musi
jeszcze potwierdzić boot, DDR, UART, sieć i PS→PL.

Każdy `make image` automatycznie sprawdza MBR, granice i brak nakładania
partycji oraz ich zgodność bajt po bajcie z boot.vfat/rootfs.ext4.
Powtórzenie audytu: `python3 tools/check_sd_image.py build/buildroot/images/sdcard.img`.

## Pliki potrzebne do odtworzenia z Git

Wszystkie wejścia projektu są śledzone przez Git:

* `Makefile`, `tools/environment.py`, `tools/image.py`: środowisko i cały build.
* `sources.lock.json`: adresy upstreamów i dokładne commity.
* `toolchains.lock.json`: archiwa narzędzi FPGA i sprawdzane SHA-256.
* `requirements.lock`: wersje zależności Python.
* `gateware/`, `tests/`: LiteX PL i test netlisty AXI.
* `patches/`: patch golden SZL dla FCLK0.
* `buildroot/`: konfiguracje Linux/U-Boot/rootfs, DTS, overlay, boot i SD.

Host wymaga Linux x86_64, Docker z dostępem użytkownika, Git, Make, Python 3
i tar. Zarezerwuj przynajmniej 30 GiB na checkout i build oraz dostęp do sieci.
Nie trzeba kopiować `.venv`, `upstream/`, `build/` ani zależności z tej maszyny:
`make image` pobiera je z przypiętych źródeł i generuje wszystkie artefakty.
Referencyjny wykaz pakietów kontenera jest w `evidence/debian-packages.txt`;
instalację odtwarza datowany snapshot APT zapisany w `tools/environment.py`.

Powtarzalna ścieżka od czystego checkoutu:

```sh
git clone https://github.com/codex-hil/kasli-soc-linux.git kasli-soc-linux
cd kasli-soc-linux
make image
```

Obraz nie jest identyczny bajtowo między checkoutami: generowany klucz SSH,
znaczniki czasu i identyfikatory filesystemów mogą się różnić. Każdy build
zapisuje własny manifest SHA-256. Prywatne klucze i gotowe obrazy nie są
commitowane. Repozytorium: https://github.com/codex-hil/kasli-soc-linux (prywatne; wymaga dostępu do konta).

## ZC706 jako etap pośredni

Sprawdzono lokalne przypięte upstreamy: LiteX-Boards ma platformę
`xilinx_zc706` dla `xc7z045ffg900-2`, a dostarczony openXC7 zawiera
zarówno dokładny part FFG900-2, jak i chipdb XC7Z045. SZL z istniejącym
patchem FCLK0 zbudował się z `--no-default-features --features target_zc706`.
Golden zynq-rs ustawia CPU 800 MHz, PS_CLK 33.333333 MHz, DDR 32-bit/666.666666 MHz.
Upstream Linux ma `zynq-zc706.dts`, 1 GiB pamięci i PHY pod adresem MDIO 7.

Obecny gotowy target LiteX-Boards używa softcore i DDR PL; nie jest targetem
Linux PS7. Dodany target używa naszego minimalnego PS7/CSR,
LED G2/LVCMOS15, DTS i konfiguracji obrazu ZC706. Nie należy bootować obrazu Kasli na
ZC706: konfiguracja DDR i PHY jest inna. PL ZC706 zbudowano przez Yosys/nextpnr/openXC7 (133.30 MHz dla 100 MHz),
SZL i test 1000 transakcji AXI/CSR również przeszły w pierwszym sprawdzeniu
programowym, zapisanym w `evidence/zc706-feasibility.json`.
Aktualny target używa SPL; fizyczne wyniki są poniżej. ZC706 jest etapem
pośrednim i nie zastępuje milestone Kasli.

### Build targetu ZC706

```sh
make BOARD=zc706 image
```

Wynik: `build/zc706/buildroot/images/sdcard.img`. Etapy: `make BOARD=zc706 pl`,
`test-pl`, `linux`. ZC706 używa U-Boot SPL z upstreamowego `ps7_init`;
SZL jest używany przez Kasli. Domyślny `make image` nadal buduje Kasli.
Narzędzia, pobrane źródła i klucz SSH są współdzielone; PL, loader, Buildroot
i obrazy mają oddzielne katalogi. Mapa CSR i hardware test są takie same.
LED G2/LVCMOS15 pochodzi z platformy LiteX ZC706; Y21 jest nieobecna w
używanej bazie openXC7. DTS ZC706 skopiowano z przypiętego upstream Linux
i dodano wyłącznie węzeł LiteX UIO/FCLK0. Status przygotowanego wówczas obrazu pozostawał niezweryfikowany;
aktualne wyniki fizycznej rev. 1.2 znajdują się poniżej.

Bring-up ZC706: SD w J30; boot SD w tabeli 1-2 UG954 to SW11.1–5 =
`0 0 1 1 0` (przy ustawianiu sprawdź oznaczenia na własnej płycie).
UART przez USB Mini-B J21/CP2103, UART1 MIO48/49, 115200 8N1.
Ethernet przez RJ45 P3/Marvell 88E1116R. Źródło:
[AMD UG954 v1.8, str. 17, 49–52](https://docs.amd.com/api/khub/documents/m4fPXowvxKd5JZRfe046WQ/content).
Boot z SD nie wymaga zapisu QSPI.

Etap `linux` odtwarza defconfig wybranej płyty. Po zmianie konfiguracji
kernela w istniejącym katalogu Buildroot użyj także `linux-reconfigure`
(lub nowego katalogu buildu), zgodnie z normalnym workflow Buildroot.

Obraz SD ZC706 ma 335 544 832 bajty; BOOT.BIN i partycje przeszły audyt.
Manifest i wyniki są w `evidence/zc706/`, a bieżące dowody fizycznego
bootu, DDR, sieci i PS→PL w `evidence/zc706/hardware-rev12-20261007/`.

Dostęp USB na tym hoście: nowy CP2103 UART i Digilent serial 210251841109
pojawiły się po podłączeniu ZC706. Konto codex-hil nie ma dostępu do
urządzeń. Administrator może nadać chwilowy ACL tylko tej parze:

```sh
sudo python3 /home/codex-hil/kasli-soc-linux/tools/grant_zc706_usb_access.py
```

Skrypt rozwiązuje bieżące numery USB z sysfs i nie zmienia pozostałych
adapterów. Po odłączeniu USB ACL może wymagać ponownego nadania. JTAG
IDCODE potwierdził XC7Z045 (`0x03731093`); oba rdzenie odpowiadają przez JTAG.

### Fizyczna diagnostyka ZC706, 2026-10-07

Bezpośredni test nadajnika PS UART wysłał `ZC706 UART TEST` do CP2103.
Kod standardowego upstream U-Boot SPL wykonuje się w OCM; odczyt pierwszych
64 KiB odpowiada przesłanemu obrazowi. Konsola U-Boot i boot Linuxa nie
zostały jeszcze uzyskane. Pierwsze odczyty rejestrów debuggera bywają
niespójne; pojedynczy wynik DDR nie potwierdza uszkodzenia pamięci.
Dowody i jawny status: `evidence/zc706/hardware-20261007/`.

Do niezależnego testu przygotowano gotowe obrazy opublikowane przez
[PULP/HERO dla ZC706](https://pulp-platform.org/hero/doc/downloads/images/zc706/).
To osobny comparator z historycznie wygenerowanym PL, **nie** nasz build
openXC7. FSBL/U-Boot próbowano uruchomić z RAM przez JTAG; nie uzyskano
konsoli. Obraz referencyjny zapisano na fizycznej karcie 32 GB (31 914 983 424 bajty),
a SHA-256 odczytu zwrotnego jest identyczny z obrazem. Wynik:
`evidence/zc706/hardware-20261007/sd-write.json`. Boot z tej karty oczekuje
na przełożenie jej do ZC706 i włączenie zasilania.
QSPI pozostało bez zmian. Czytnik USB i karta testowa zostały udostępnione.

Odtworzenie obrazu referencyjnego (po przygotowaniu toolchainu ZC706):

```sh
python3 tools/environment.py python3 tools/zc706_reference.py --image
```

Wynik: `build/zc706-vendor-baseline/sdcard.img`, partycja FAT 64 MiB
z `BOOT.bin`, `uImage`, `devicetree.dtb`, `uramdisk.image.gz`.
`configs/zc706-reference.json` przypina SHA-256 każdego pobranego pliku;
zmiana pod upstreamowym adresem `latest` zatrzyma odtwarzanie.
Skrypt tworzy wyłącznie plik obrazu i nie zapisuje żadnego urządzenia.

Po włączeniu z kartą referencyjną: UART pusty, PC BootROM `0xffffff28`,
`BOOT_MODE=5` (SD), `REBOOT_STATUS=0x00401000`. Odczyty potwierdzono
opcjonalnie przez AMD XSDB / istniejący hw_server. FSBL nie został załadowany
z SD; przyczyna wymaga dalszej diagnostyki. Próby ładowania gotowego FSBL
i U-Boot przez JTAG również nie dały konsoli. Nie jest to dowód uszkodzenia
płyty ani zakończony test DDR. Build nie korzysta z narzędzi AMD.

Nowszy wynik diagnostyki: użytkownik potwierdził **ZC706 rev. 1.0**,
POWER GOOD świeci, J7 jest OPEN. Po inicjalizacji PS7 opublikowanym
HERO FSBL DDR gubi bit 12: `ffffffff → ffffefff`, `00001000 → 00000000`,
`55555555 → 55554555`, powtarzalnie pod `01000000`, `01000040`, `11000000`.
Identyczne zapisy/odczyty w OCM (`00020000`) są poprawne. Instrukcja skoku
U-Boot `eaffffeb` odczytuje się jako `eaffefeb`; krokowanie potwierdza skok
pod niewłaściwy adres i wyjątek. Wynik nie rozstrzyga jeszcze usterki płyty
wobec konfiguracji specyficznej dla rewizji. Następny eksperyment to ten sam
obraz na dostępnej rev. 1.2. BootROM SD jest osobnym nierozwiązanym problemem.
Logi: `ddr-bit12-patterns.log`, `ocm-ddr-control.log`, `branch-readback.log`
w katalogu dowodów hardware. QSPI bez zmian.

### Sukces obrazu referencyjnego na ZC706 rev. 1.2

Ta sama karta bootuje Linux `4.9.0-xilinx-v2017.2`, BusyBox i konsolę
UART. JTAG `0x23731093`, MCTRL `0x30800100`; adapter `210251842914`.
Ethernet 1000/Full, DHCP `192.168.2.7`, ping i SSH kluczem projektu PASS.
Kernel widzi 901732 KiB RAM; test `memtester 128M 3` trwa. Pełny log
U-Boot wymaga jeszcze przechwycenia restartu. Dowody:
`evidence/zc706/hardware-rev12-20261007/`.
To **referencyjny system HERO z vendorowym PL**, nie nasz Linux/openXC7;
milestone 1 nadal nie jest osiągnięty. Rev. 1.0 i jej wyniki pozostają
osobno zapisane. Klucz SSH dodano w RAM systemu referencyjnego; znika
po restarcie. Domyślne logowanie tego obrazu opisuje
[README HERO SDK](https://github.com/pulp-platform/hero-sdk/blob/master/README.md).

### Fizyczny sukces PL openXC7 na rev. 1.2

Na działającym systemie referencyjnym załadowano nasz `top.bit` przez
`/dev/xdevcfg` (bez narzędzi AMD). Przesłanie SHA-256 zweryfikowane,
PCAP DONE=1. FCLK0 ustawiono przez sterownik zegara Linux na ~100 MHz.
PS → AXI → LiteX CSR działa: sygnatura `4b534f43`, scratch RW,
**10000 transakcji PASS**, licznik 99990601 Hz, scratch przywrócony.
PL jest zbudowany przez Yosys/nextpnr/openXC7; jego SHA-256:
`e5a836508795b7bca585caee43ab4fe65b00ede398fbdc2d7d90468f861357d2`.
Dowody: `openxc7-program.log`, `csr-smoke.log`, `pl-test.log`.

Odtworzenie na systemie referencyjnym z dostępem SSH kluczem projektu:

```sh
python3 tools/load_pl_xdevcfg.py 192.168.2.7
python3 tools/environment.py /work/build/zc706/buildroot/host/bin/arm-linux-gcc \
  -static -O2 -Wall -Wextra /work/tools/pl_test.c -o /work/build/pl-test
ssh -i build/ssh/id_ed25519 -o UserKnownHostsFile=build/ssh/known_hosts \
  root@192.168.2.7 'cat > /tmp/pl-test; chmod 755 /tmp/pl-test; /tmp/pl-test 10000' \
  < build/pl-test
```

`load_pl_xdevcfg.py` jest helperem dla legacy kernela referencyjnego;
nie zapisuje SD ani QSPI. Ponowny boot karty referencyjnej przywróci HERO PL.
Nadal pozostają: pełny log startu U-Boot, wynik długiego testu DDR oraz boot
**naszego** obrazu SZL/upstream U-Boot/upstream Linux/Buildroot/openXC7.
Nie utożsamiamy hybrydowego bring-upu z zakończeniem milestone 1 Kasli-SoC.

PS7 działającego systemu referencyjnego z naszym PL zapisano jako
`ps7-reference-openxc7.json` (108 rejestrów, UART_CLK_CTRL `00001402`,
FPGA0_CLK_CTRL `00200500`, 100 MHz). Hostowy transport SSH dumpu nie wymaga
Pythona na starym rootfs:

```sh
python3 tools/dump_ps7_state.py --ssh-address 192.168.2.7 > ps7.json
```

Nasz obraz `build/zc706/buildroot/images/sdcard.img` zapisano następnie
z działającego systemu RAM na tę samą kartę SC32G, CID
`035344534333324780d55bcc91012a00`, po sprawdzeniu braku mountów SD.
Odczyt 335544832 bajtów ma SHA-256 identyczny z manifestem:
`c771c39018c5f32d16f8afb3e5bae3610fb36c1bc713c61dc5044fd4d44f8015`.
Restart do naszego obrazu nastąpi po zakończeniu testu DDR. Karta nie
zawiera już obrazu HERO; jego kopia i skrypt odtworzenia pozostają na hoście.

Aktualny status fizycznej ZC706 rev. 1.2 (własny Linux i upstream SPL):

Element | Status
---|---
PS7 | PASS, upstream U-Boot SPL ZC706 z istniejącym ps7_init
DDR | PASS, 1 GiB / 533 MHz; memtester 128M 3 na naszym Linuxie, bez błędów
UART | PASS, 115200 8N1
SD | PASS, pełny własny obraz zapisany, odczyt SHA-256 zgodny, boot bez JTAG
U-Boot | PASS, SPL i main 2026.10-rc5, pełny log UART
Linux | PASS, własny upstream 6.18.40 i rootfs Buildroot z SD
Ethernet | PASS, 1000/Full, DHCP 192.168.2.15, ping
SSH | PASS, klucz projektu
AXI PS→PL | PASS na fizycznej płycie
LiteX CSR | PASS, po 10036 zapisów/odczytów przez devmem i UIO, licznik ~100 MHz
Yosys | PASS, użyty do zbudowanego i załadowanego PL
nextpnr-xilinx/openXC7 | PASS, place-and-route i timing
openXC7 bitstream | PASS, PCAP DONE i fizyczny test CSR
ARTIQ RTIO PoC | nie rozpoczęto

Pełny test DDR systemu referencyjnego zakończył się kodem 0:
`memtester 128M 3`, wszystkie wzorce i trzy pętle PASS. Log zapisano
bez animacji terminalowych w `ddr-memtester.log`; SHA-256 surowego logu
jest w `status.json`.

### ZC706: upstream Linux uruchomiony, korekta loadera (2026-10-07)

Pierwszy pełny restart naszego SD uruchomił SZL, lecz programowanie PL
zakończyło się `DoneTimeout`. Partycja PL zawiera poprawne dane PCAP;
odczyty wzorców DDR przez JTAG wykazały przekłamania przy konfiguracji
SZL (667 MHz). Nie traktujemy tego jako awarii bitstreamu ani dowodu
uszkodzenia rev. 1.2.

Upstreamowy U-Boot SPL korzystający z istniejącego
`board/xilinx/zynq/zynq-zc706/ps7_init_gpl.c` inicjalizuje DDR na 533 MHz,
tak jak działający obraz HERO. Załadowano SPL i nasz U-Boot przez
open-source OpenOCD, następnie U-Boot uruchomił z SD nasz Linux
6.18.40 i rootfs Buildroot. UART, 1 GiB DDR, DHCP (192.168.2.15), ping
i SSH działają. Logi są w `evidence/zc706/hardware-rev12-20261007/`.
Pełny test DDR tego systemu trwa; PL w tym starcie nie został załadowany.

Target ZC706 przechodzi na standardowy flow BootROM → U-Boot SPL →
`u-boot.img` → `boot.scr` → openXC7 `top.bit` → Linux/ext4.
`boot.cmd` jest źródłem reprodukowalnego skryptu startowego. Używamy
upstreamowego opisu ZC706 i PS7, bez generowania konfiguracji w Vivado.
Kasli-SoC nadal używa golden SZL/ARTIQ. Pełny start nowego wariantu ZC706
z SD bez JTAG pozostaje do sprawdzenia; milestone 1 Kasli nie jest zakończony.

Pełne `make BOARD=zc706 image` w wariancie SPL zakończyło się kodem 0.
Obraz ma 335544832 bajty; bieżące hashe znajdują się w
`evidence/zc706/image-manifest.json`. `BOOT.BIN` zawiera wyłącznie
upstreamowy SPL; PL ładuje U-Boot z pliku `top.bit`, przed uruchomieniem
kernela. Niepowodzenie ładowania PL zatrzymuje skrypt startowy.

Obraz zawiera również `rootfs.cpio.gz`, pozwalający uruchomić ten sam
userspace w RAM. `tools/boot_zc706_uart.py --ram-root` przechwytuje
autoboot i wybiera ten tryb bez zapisywania środowiska U-Boot.
Narzędzie wymaga hostowego Pythona z `pyserial==3.5` oraz jawnej ścieżki
UART i adresu SSH działającej płyty. Przykład dla tego egzemplarza:

```sh
.venv/bin/python tools/boot_zc706_uart.py \
  --port /dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0 \
  --reboot-ssh-address ADRES_IP --ram-root --output build/hardware/ram-boot
```

Po potwierdzeniu rootfs w RAM można zapisać obraz przez LAN:

```sh
python3 tools/write_sd_over_ssh.py ADRES_IP \
  --cid 035344534333324780d55bcc91012a00 \
  --image build/zc706/buildroot/images/sdcard.img \
  --output build/hardware/sd-write.json
```

CID powyżej identyfikuje udostępnioną kartę SC32G; dla innej karty trzeba
podać jej własny CID. Skrypt odmawia zapisu, jeśli rootfs nie działa w RAM
lub SD jest zamontowana, sprawdza CID i pojemność, a następnie porównuje
SHA-256 pełnego odczytu z obrazem. Odmowę przy rootfs z SD sprawdzono
na fizycznej płycie. QSPI nie jest używana. Test PL obsługuje
`--device /dev/uio0` oprócz `/dev/mem`.

Końcowy obraz ma SHA-256
`729c58c976ce71c6171a5a6e20f8d827a000702b7edc2853ad219f25d076d7de`.
Zapisano go w całości z recovery RAM, odczytano wszystkie 335544832 bajty
i potwierdzono zgodność hasha. Następnie uruchomiono ten obraz z SD:
SPL, U-Boot, PL, Linux, konsola, rootfs ext4, DHCP, ping (0% strat) i SSH PASS.
Klucz publiczny SSH hosta jest pobierany przez fizyczny UART i wpisywany do
projektowego `build/ssh/known_hosts`; świeży rootfs/recovery może generować
nowy klucz hosta. Nie wyłączamy sprawdzania kluczy SSH.

U-Boot korzysta z losowego MAC przy środowisku w RAM. Po uzyskaniu lub
odnowieniu DHCP hook BusyBox wysyła gratuitous ARP, aby odświeżyć wpisy
hosta/routera po restarcie. Nie zapisujemy środowiska w QSPI.

Pełny test automatyczny:

```sh
python3 tools/hardware_test.py ADRES_IP --output build/hardware/validation
```

Domyślnie testuje `memtester 128M 3`; `--ddr-loops 1` pozwala skrócić
kontrolę kolejnego bootu. Po wcześniejszym PASS trzech pętli wykonujemy
jedną dodatkową pętlę na finalnym obrazie, następnie test UIO i dump PS7.
Wyniki finalnego testu są zapisywane osobno i nie zastępują logów wcześniejszych.

### Finalny wynik ZC706 rev. 1.2 — PASS

W `evidence/zc706/hardware-rev12-20261007/final-validation/` wszystkie
kontrole zakończyły się kodem 0: ping (5/5, bez strat), SSH, `memtester 128M 1`,
UIO (10036 zapisów/odczytów, licznik ~100 MHz) i odczyt rejestrów PS7.
`validation.json` łączy te wyniki z logiem bootu i hashem pełnego odczytu SD.
BootROM/SPL/U-Boot/PL/Linux działają bez ładowania przez JTAG.
Potwierdzono restarty programowe; pełnego odłączenia zasilania nie testowano.
Rev. 1.0 pozostaje osobnym, nierozwiązanym przypadkiem diagnostycznym.

[Gotowy obraz SD i sumy kontrolne](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-poc-20261007).
`make BOARD=zc706 image` odtwarza również `sdcard.img.gz` i `SHA256SUMS`.
Archiwum rozpakowuje się do dokładnie zweryfikowanego obrazu SD.

SSH z tego stanowiska:

```sh
ssh -i build/ssh/id_ed25519 -o UserKnownHostsFile=build/ssh/known_hosts root@192.168.2.15
```

To zakończony bring-up ZC706. Milestone 1 Kasli-SoC wymaga nadal testów
na fizycznej Kasli-SoC; RTIO PoC nie został rozpoczęty.

Investigation of the older ZC706 engineering-sample silicon, relevant errata, and the next controlled DDR experiment: [silicon revision comparison](evidence/zc706/silicon-revisions-20261007.md). The rev. 1.0 DDR fault remains unresolved.

FMC ADC connectivity audit: [both ZC706 slots](evidence/zc706/fmc-adc-pin-audit-20261007.md). DCO and all ADC data lanes share an HR bank in each slot; J5 LPC is recommended for first acquisition. ADC gateware and physical acquisition remain unvalidated.

Independent PL SODIMM bring-up: [architecture, build and current status](docs/zc706-pl-ddr.md).
Yosys, patched nextpnr routing/timing and openXC7 bitstream generation PASS
at 333⅓ MHz DDR / 83⅓ MHz system / 50 MHz GP1 and BIST. The static ARM
diagnostic and simulations (including clock crossings, injected errors,
byte lanes and synthesized GP0 CSRs) pass. `make ddr-package` reproduces
the bring-up bundle. Physical JTAG programming, eight-lane DDR leveling,
GP1 address checks and three full-1-GiB BIST passes PASS on rev. 1.2 with
zero errors: [hardware evidence](evidence/zc706/pl-ddr-20261008/validation.json).
ADC remains separate; SD/QSPI unchanged. DCI termination is not supported
by the current backend; long-term signal-integrity qualification remains pending.
