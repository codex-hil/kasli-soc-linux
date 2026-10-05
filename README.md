# Kasli-SoC Linux / LiteX / openXC7

Prace trwają. **Milestone 1 nie został osiągnięty ani potwierdzony na hardware.**
Repo jest oddzielone od upstream ARTIQ; checkouty `upstream/` pozostają bez zmian.

## Hardware i źródła prawdy

Platforma Migen `migen/build/platforms/sinara/kasli_soc.py`: **XC7Z030-FFG676-3**,
LED AF19/AF23 LVCMOS25. Dodatkowe piny PS/DDR:
`migen-axi/src/migen_axi/platforms/kasli_soc.py`.
Target ARTIQ: `artiq-zynq/src/gateware/kasli_soc.py`.
Rewizja fizycznego egzemplarza nie jest jeszcze ustalona.

Inicjalizacja PS pochodzi z **M-Labs zynq-rs SZL**, nie z nowego presetu Vivado:

* PS_CLK 33 333 333 Hz: `libboard_zynq/src/clocks/source.rs`.
* ARM 1 GHz i IO PLL 1 GHz: `szl/src/main.rs`.
* DDR3L MT41K256M16HA-125:E, 32-bit, 512 MiB, zegar 533 333 333 Hz:
  `libboard_zynq/src/ddr/{mod,regs}.rs`. SZL wykonuje konfigurację kontrolera,
  IOB i kalibrację; tych wartości nie zmieniamy.
* UART1 115200 8N1, TX MIO48 / RX MIO49, bank 1.8 V:
  `libboard_zynq/src/uart/mod.rs` i `stdio.rs`. PL serial Y18/AA18 to inne piny.
* SD0 MIO40–45, card detect MIO46: `libboard_zynq/src/sdio/mod.rs`.
* GEM0 RGMII MIO16–27, MDIO MIO52/53, reset PHY GPIO MIO47:
  `libboard_zynq/src/eth/mod.rs`. Schemat `Kasli-SOC_ETH_PHY.SchDoc`
  potwierdza Marvell 88E1512. Adres MDIO wymaga jeszcze potwierdzenia strapów.
* Reset i level shifters: `slcr.rs::init_preload_fpga/init_postload_fpga`.
* QSPI i USB: jeszcze niezweryfikowane; wyłączone w pierwszym bring-upie.
* GTX/SFP, zegary RTIO i EEM nie są potrzebne do minimalnego PL.

Commity źródeł znajdują się w `sources.lock.json`. Projekt korzysta z
[LiteX Zynq7000](https://github.com/enjoy-digital/litex/blob/master/litex/soc/cores/cpu/zynq7000/core.py)
i [openXC7](https://github.com/openXC7/toolchain-nix).

## Mapa przeniesienia

ARTIQ/Migen element | LiteX/openXC7 odpowiednik | Status
---|---|---
Sinara Kasli-SoC platform/LED | mała lokalna platforma `gateware/kasli_soc.py` | elaboracja działa
zynq-rs SZL PS/DDR/MIO | ten sam loader, dodana konfiguracja FCLK0 | build w toku
Migen-AXI PS7 | upstream LiteX Zynq7000 / natywny prymityw PS7 | synteza działa
ARTIQ AXI/CSR | GP0 → upstream AXI3/Wishbone bridge → LiteX CSR | PL zbudowany, hardware oczekuje
Vivado place-and-route | Yosys → nextpnr openXC7 → FASM → X-Ray bitstream | build eksperymentalny działa
ARTIQ runtime | upstream U-Boot → upstream Linux → Buildroot | implementacja w toku
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
* `tools/dump_ps7_state.py`: odczyt SLCR/DDRC z `/dev/mem`, JSON i porównanie.
  Nie czyta FIFO. Dla ARTIQ potrzebny jest jeszcze transport JTAG lub integracja dumpu.
* `upstream/`, `.venv/`, `build/`: ignorowane katalogi robocze.
* `evidence/`: dowody z buildów; nie są dowodami działania fizycznej płyty.

Obecnie elaboracja: `.venv/bin/python gateware/kasli_soc.py`.
Docelowe `make image`, bootstrap środowiska i gotowy obraz SD są w przygotowaniu.
Nie deklarujemy jeszcze odtwarzalnego kompletnego obrazu.

Pakiety FPGA użyte w pierwszym eksperymencie:
openXC7 release 2026-10-03, nextpnr c68c1358, prjxray-db a90f27c1;
OSS CAD Suite 2026-10-05, Yosys 0.69+190 / 0e8336b4e.
SZL wymaga Rust nightly-2026-03-25, rust-src i clang.
Buildy i większe zależności przechowujemy na dodatkowym woluminie, ponieważ
partycja systemowa ma mniej niż 1 GB wolnego miejsca.

## Walidacja

Yosys: CHECK 0 problemów. nextpnr: 143.84 MHz, PASS dla 100 MHz.
Powstał bitstream 5.8 MiB przez fasm2frames + xc7frames2bit, bez Vivado.
Obecna baza zawiera FBG676-1 zamiast FFG676-3; routing używa konserwatywnego
stopnia -1. Mapowanie obudowy jest sprawdzane z oficjalnymi pinoutami AMD;
nie wolno uznać samego powodzenia routingu za hardware validation.
Nowy nextpnr używa `--device` i `-o xdc=... -o fasm=...`; aktualny backend
LiteX generuje starsze argumenty. Adapter buildu jest w przygotowaniu.

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
PS7 | golden reference znaleziony; natywny PS7 zsyntezowany
DDR | konfiguracja zynq-rs znaleziona; hardware niebadany
UART | UART1/MIO48–49 ustalone; hardware niebadany
SD | SD0/MIO40–46 ustalone; obraz jeszcze niegotowy
U-Boot | integracja w toku
Linux | integracja w toku
Ethernet | GEM0/88E1512/reset ustalone; adres PHY do ustalenia
SSH | oczekuje na rootfs
AXI PS→PL | build PL przeszedł; hardware niebadany
LiteX CSR | mapa wygenerowana; hardware niebadany
Yosys | synteza PASS
nextpnr-xilinx | routing i timing PASS, adapter nowego CLI w toku
openXC7 bitstream | artefakt zbudowany; alias obudowy weryfikowany; hardware niebadany
ARTIQ RTIO PoC | oczekuje na milestone 1
