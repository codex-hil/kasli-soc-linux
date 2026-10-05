# Kasli-SoC Linux / LiteX / openXC7

Prace trwają. **Milestone 1 nie został osiągnięty ani potwierdzony na hardware.**
Repo jest oddzielone od upstream ARTIQ; checkouty `upstream/` pozostają bez zmian.

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
