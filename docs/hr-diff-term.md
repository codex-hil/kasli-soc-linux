# Terminacja różnicowa HR w openXC7

Stan 2026-10-08: rzeczywiste `DIFF_TERM` dla wejść **HR LVDS_25 przy VCCO
2.5 V** zmapowane i zwalidowane na ZC706 rev. 1.2 z CERN FMC ADC v6.1
w J5 LPC. HP oraz inne standardy różnicowe pozostają poza zakresem tej łatki.
Nie jest to walidacja parametrów analogowych karty.

## Co zostało zmierzone

Opcjonalny comparator Vivado 2019.1 zbudował jeden design dla XC7Z020CLG400-1,
wykorzystując **wszystkie 60 wyprowadzonych par HR**. Po routingu zmieniano
wyłącznie właściwość `DIFF_TERM` portu P. Wygenerowano baseline OFF,
60 wariantów pojedynczej pary ON, ALL ON oraz powtórzony OFF.
Nie wykonywano ponownego routingu między wariantami.

`bitread` i `tools/analyze_diff_term_reference.py` potwierdziły:

| Funkcja kafla | Bity lokalne |
|---|---|
| `LIOB33.DIFF.DIFF_TERM` | `38_100 39_97` |
| `RIOB33.DIFF.DIFF_TERM` | `38_100 39_97` |

Każdy wariant zmienił dokładnie dwa bity w swoim kaflu, bez zmian poza nim.
ALL ON jest dokładną sumą pojedynczych zmian; powtórzony OFF ma identyczną
konfigurację. Wyłączono z porównania wyłącznie wyliczany ECC, słowo 50.
Hash każdego bitstreamu i mapa wszystkich par są w
`evidence/zc706/hr-diff-term-20261008/all-hr-mapping.json`.

Mapa `zc706-pins.csv` obejmuje 562 piny sygnałowe w dostępnej bazie obudowy,
w tym wszystkie **350 pinów PL**: 192 piny w 96 parach HR, 144 piny w 72
parach HP oraz 14 pojedynczych pinów. Uwzględnia istniejący, audytowany
patch brakujących HR w bazie XC7Z045FFG900. Dla HR podaje dokładne adresy
frame/word/bit z geometrii tilegrid. Jest to mapa obudowy i konfiguracji,
a nie deklaracja fizycznego testu każdego pinu. Fizycznie sprawdzono 11
odbiorników w naszym designie ADC, w tym wejście zegara referencyjnego.
Piny PS i transceiverów są jawnie opisane jako `not PL I/O`.

## Zmiany w narzędziach

Pinned nextpnr gubił parametr podczas dekompozycji IBUFDS. Łatka zachowuje
wybór terminacji na głównym PAD i emituje funkcję kafla `DIFF.DIFF_TERM`.
Jawna właściwość portu ma pierwszeństwo przed parametrem prymitywu.
Sprzeczne właściwości P/N, HP i niezweryfikowane standardy kończą się błędem.
Nie zmieniono chipdb ani checkoutu upstream.

Dotychczasowa grupowa funkcja `IN_ONLY` zawierała negacje `!38_100 !39_97`,
ponieważ te same bity uczestniczą w konfiguracji wyjścia różnicowego.
Dodajemy osobną `IOB_Y0.LVDS_25.IN_ONLY`, zwalniając dokładnie te dwie
negacje; pozostałe bity i stara funkcja pozostają zachowane.

W Project X-Ray fuzzer `030-iob` już losował `DIFF_TERM`, ale nie zapisywał
jego tagu. Łatka dodaje tag dla LVDS_25 oraz tworzenie aliasu `IN_ONLY`
w postprocessorze z bitów wyznaczonych przez segmatcher. Testy obejmują
oba stany, wykluczenie PUDC, inne standardy, wejście pojedyncze oraz
zachowanie pozostałych negacji. Pełny losowy fuzzer z Vivado 2017.2 nie
został tutaj uruchomiony; wykonano kontrolowany eksperyment Vivado 2019.1.

`tools/adc_nextpnr.py` buduje osobny backend z przypiętych obiektów bazowych.
`tools/adc_termination_db.py` tworzy osobny overlay i sprawdza hashe źródła.
Kontroler PL DDR korzysta dalej z poprzedniego backendu. ADC i DDR nadal
pracują niezależnie.

## Fizyczne ON/OFF/ON

Oba stany używają tego samego routingu, mapy CSR i drivera. Terminacja źródła
ADC jest wyłączona (`A2=0`, 3.5 mA). Wariant OFF powstaje przez usunięcie
11 funkcji z FASM. Dekodowanie obu bitstreamów potwierdza dokładnie 22
zmienione bity konfiguracji, poza wyliczanym ECC.

| Wariant | Wynik |
|---|---|
| FPGA ON, ADC OFF, pierwszy cold boot | PASS: 139264 wartości wzorców i snapshot 1024 próbek/kanał |
| FPGA OFF, ADC OFF, ten sam routing | FAIL: brak stabilnego okna danych >=3 taps, wszystkie osiem linii |
| FPGA ON, ADC OFF, kolejny cold boot | PASS: powtórzenie pełnego testu |

ON SHA-256: `850752ddb769991c646046fbc67acc5e8edd823a15b9c18c92c5de9ece805bfe`.
OFF SHA-256: `8b8fa945e0d5a6b9736981a7c24f64ec6d50e1f50def12f0d427590c3c2f3802`.
Wyniki, walidacje i logi bootu: `evidence/zc706/hr-diff-term-20261008/`.
ZC706 pozostaje na wersji ON. Używano wyłącznie ulotnego programowania JTAG
przed uruchomieniem Linux; nie zapisywano SD, QSPI ani środowiska U-Boot.

## Odtwarzanie

Produkcja nadal nie wymaga Vivado:

```sh
make bootstrap BOARD=zc706
make adc-pl
make adc-test
python3 tools/map_hr_diff_term_pins.py
```

Opcjonalne odtworzenie pomiaru bitów:

```sh
python3 tools/prepare_diff_term_reference.py --all-pairs \
  --output build/zc706-adc/termination-reference/all-hr
```

Uruchomić wygenerowany `reference.tcl` w Vivado, w katalogu z `top.v`.
Comparator używa przypiętego obrazu
`kkrizka/vivado@sha256:f08ed71496b6ec4d1709c49eee92286d256ecb11ea7dbf23f75d89fc6fe2162c`,
bez sieci i urządzeń USB, z mountem wyłącznie katalogu eksperymentu.
Dla każdego pliku `.bit` uruchomić `bitread --part_file PART/part.yaml -y -z
-o NAME.bits NAME.bit`, potem:

```sh
python3 tools/analyze_diff_term_reference.py \
  build/zc706-adc/termination-reference/all-hr
python3 tests/diff_term_reference_test.py
python3 tests/adc_termination_db_test.py
```

Opcjonalna kontrola OFF: `python3 tools/environment.py python3 tools/build_diff_term_ab.py`.
Nie publikować jej jako obrazu użytkowego. Driver wybiera `A2=0` dla nowych
map CSR z `adc_fpga_diff_term=1`; stare mapy zachowują sprawdzone `A2=0xf0`.

## Upstream

Głównym miejscem zgłoszenia jest `f4pga/prjxray`. `prjxray-db` zgodnie ze
swoim CONTRIBUTING nie przyjmuje bezpośrednich zmian wygenerowanej bazy.
Gotowe patche są w `patches/prjxray-hr-diff-term-fuzzer.patch` oraz
`patches/prjxray-hr-diff-term-db.patch`. Zgłoszenie wymaga podpisu DCO z
prawdziwym imieniem i nazwiskiem. Na wyraźne polecenie użytkownika dodano
`Signed-off-by: Greg Kasprowicz <gkasprow@gmail.com>`.

[PR #2575](https://github.com/f4pga/prjxray/pull/2575) jest gotowy do przeglądu.
Check DCO zakończył się SUCCESS dla commitu
`ecc21ef834edf6631ed7e51c4d1b43da9a3d8446`.
