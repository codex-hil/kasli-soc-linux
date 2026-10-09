# ZC706 / obie FMC / Tektronix AFG1062

2026-10-09: przygotowane przechwycenie CH1 obu kart. **Pomiar zadanego
sinusa 1 MHz / 1 Vpp nie został jeszcze wykonany** — generator nie został
przestawiony, brak dostępu SSH/API do Pi mostu.

Pi rozpoznane przez odpowiedź mDNS PTR: `RPI-USBTMC.local`,
`192.168.2.36`, MAC `b8:27:eb:01:74:4d`. SSH odpowiada, most nie słucha
na standardowych portach. Pi `192.168.2.8` to osobny projekt RNG.
ZC706: po przywróceniu huba i linku Ethernet `192.168.2.10`.

Bitstream dwóch kart załadowany ponownie z istniejącego pliku ext4 przez
UART/U-Boot, bez JTAG, bez zapisu SD/QSPI i bez SSH:

```sh
python3 tools/boot_adc_jtag.py --sd-existing --allow-no-network \
  --bit build/zc706-adc-dual/gateware/gateware/top.bit
```

Wymaga zalogowanej konsoli root Linuksa oraz istniejącego
`/root/adc-<SHA256>.bit`; loader weryfikuje SHA-256 przed restartem.
`--allow-no-network` potwierdza tylko działający shell UART, nie DHCP.
Standardowy tryb loadera pozostaje bez zmian.

Skrypt przechwycenia na płytę: `tools/capture_adc_sine.py` wraz z
`tools/fmc_adc.py` i wygenerowanym `csr.json`. Każda karta ma osobny trening,
ADC generator wzorców zostaje wyłączony, tylko CH1 dołączony na zakresie
±5 V, analogowe 50 Ω wyłączone. Cztery snapshoty po 1024 próbek na kanał,
RAW BIN i CSV, bez założenia wspólnej fazy między kartami.

```sh
python3 capture_adc_sine.py --csr-json csr.json --output capture
```

Skrypt wymaga początkowego `control=1`, `ssr=0` na obu kartach. Po pomiarze
odłącza wejścia i zatrzymuje odbiorniki. Nie steruje generatorem i nie
uznaje samego odczytu próbek za potwierdzenie częstotliwości/amplitudy.

Próbny odczyt obu kart PASS bez błędów frame, ale na wejściach nie było
zadanego przebiegu. Pierwsze snapshoty CH1: LPC −2..21 kodów ADC,
HPC −6..15 kodów ADC. To **baseline bez potwierdzonych nastaw generatora**,
nie pomiar sinusa ani charakterystyka szumów. Zapis:
`evidence/zc706/afg-bringup-20261009/`.

Do kontynuacji potrzebny login SSH do `RPI-USBTMC.local` albo dostępna usługa
mostu z konfiguracją klienta. Zakładamy sinus 1 MHz, 1 Vpp, offset 0 V;
obciążenie AFG trzeba odczytać/ustawić jawnie dla wejść wysokiej impedancji.
