# LyricsPi

LyricsPi ist ein Offline-Songtext-Prompter für Live-Auftritte auf dem
Raspberry Pi 2 und 3. Unter Windows lädt LyricsPi beim Start die Setlist in den
Arbeitsspeicher und zeigt den ersten Song in einem Pygame-Fenster. Der
Text ist standardmäßig weiß auf schwarzem Hintergrund und beginnt
linksbündig am oberen Rand. Die Bedienung erfolgt per Tastatur oder
M-VAVE-USB-Fußcontroller im HID-Modus.

## Einrichtung unter Windows

Vorausgesetzt werden Windows, PowerShell und Python ab 3.11. Für die
Entwicklung unter Windows wird Python 3.13 verwendet. Führe die folgenden
Befehle im Projektordner aus. Falls `.venv` bereits existiert, reicht der
zweite Befehl für die Installation.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## LyricsPi starten

```powershell
.\.venv\Scripts\python.exe -m lyricspi.main
```

In einer aktivierten `.venv` genügt `python -m lyricspi.main`. Die
Anwendung protokolliert Tastaturaktionen im Entwicklungsmodus im Terminal.

| Taste | Wirkung |
| --- | --- |
| Pfeil links / rechts | Wechselt zum vorherigen / nächsten Song, jeweils auf Seite 1 |
| Pfeil hoch / runter (kurz) | Blättert zurück / beim Loslassen weiter |
| Pfeil runter (mindestens 15 Sekunden halten) | Beendet LyricsPi |
| Minus / Plus | Verkleinert / vergrößert die Schrift innerhalb der konfigurierten Grenzen |
| Escape | Beendet das Programm im Entwicklungsmodus |

Nach dem letzten Song folgt wieder der erste. Vom ersten Song führt Pfeil
links zum letzten. Beim Blättern bleibt die Anzeige auf der ersten bzw.
letzten Seite stehen.

Die feste Kopfzeile zeigt links den Songtitel und rechts die Songnummer
aus dem Dateinamen samt führender Nullen. Titel, Nummer, Songtext und
Abschnittsmarker verwenden dieselbe Schriftgröße. Plus und Minus ändern
sie gemeinsam.
Lange Titel werden mit Auslassungspunkten gekürzt. Die Songtexte
beginnen darunter. Der Balken links zeigt die Position innerhalb des
Songs. Seine Markierung steht auf der ersten Seite oben und auf der
letzten Seite unten. Bei einem einseitigen Song steht sie mittig.

Lange Zeilen werden entsprechend der Fensterbreite umgebrochen. Strophen
bleiben nach Möglichkeit zusammen. Zu lange Strophen werden auf mehrere
Seiten verteilt. Nach einer Schrift- oder Fenstergrößenänderung berechnet
LyricsPi die Seiten neu und behält den ausgewählten Song bei. Falls die
bisherige Seite entfällt, zeigt LyricsPi die letzte verfügbare Seite.
Ist das Fenster zu klein für Songtext, zeigt es einen Hinweis.

Für Akkorde verwendet LyricsPi bevorzugt eine Monospace-Systemschrift.
Führende Leerzeichen bleiben beim Darstellen erhalten. Tabs werden zur
Anzeige in Abstände mit vier Spalten pro Tabstopp umgesetzt. Wenn lange
Akkord- und Textzeilen an unterschiedlichen Stellen umbrechen, können sich
die Akkorde relativ zum Text verschieben. Ist keine der unterstützten
Monospace-Schriften installiert, verwendet Pygame seine Standardschrift.

## M-VAVE-Fußcontroller

Verbinde den M-VAVE per USB im Tastaturmodus (HID) und gib dem
LyricsPi-Fenster den Tastaturfokus. Die Fußtasten senden dieselben
Pfeiltasten wie eine normale Tastatur.

| Fußtaste | Tastatursignal | Funktion |
| --- | --- | --- |
| A | Pfeil hoch | Vorherige Seite |
| B (kurz) | Pfeil runter | Beim Loslassen genau eine Seite weiter |
| B (mindestens 15 Sekunden halten) | Pfeil runter | LyricsPi beenden |
| C | Pfeil links | Vorheriger Song |
| D | Pfeil rechts | Nächster Song |

A, C und D reagieren beim Drücken. Die bisherigen Tastenkombinationen
entfallen. Die Schriftgröße änderst du mit Plus und Minus auf der Tastatur.
Da Pygame dieselben Tastaturereignisse für beide Geräte liefert, gilt der
lange Druck auch für Pfeil runter auf der normalen Tastatur.

Für einen kurzen Druck braucht LyricsPi ein zusammengehöriges `KEYDOWN`
und `KEYUP`. Für das lange Halten muss das Betriebssystem Pfeil runter
durchgehend als gedrückt melden. Sendet der M-VAVE beim Halten nur kurze
HID-Impulse, ist die Beenden-Funktion mit diesem Controller nicht verfügbar.
Autorepeat verlängert oder startet die Messung nicht neu. Bei Fokusverlust
oder wenn der gemeldete Tastenzustand ohne `KEYUP` endet, verwirft LyricsPi
die Messung. Im Entwicklungsmodus protokolliert das Terminal
`KEYDOWN Arrow Down`, `KEYUP Arrow Down`, die gemessene Haltezeit und die Aktion.

Unter Windows und im Entwicklungsmodus beendet ein langer Druck LyricsPi
über `EXIT`. Im eingerichteten Raspberry-Pi-Produktivmodus gibt LyricsPi
zuerst die Anzeige frei und fordert anschließend über logind das reguläre
Herunterfahren an.

Für die Hardwareabnahme starte LyricsPi im Entwicklungsmodus mit einem
mehrseitigen Song und prüfe A, B, C und D. Drücke B zunächst kurz und prüfe,
dass beim Loslassen genau eine Seite weitergeblättert wird. Halte B dann
mindestens 15 Sekunden. LyricsPi soll sich dabei ohne Seitenwechsel schließen.
Wenn sich die Anwendung nicht schließt, prüfe im Terminal, ob der Controller
beim Halten vorzeitig `KEYUP` sendet.

## Konfiguration

Ohne lokale Konfigurationsdatei startet der Simulator mit den
Standardwerten. Für eigene Einstellungen kopiere die Beispieldatei und
bearbeite die Kopie.

```powershell
Copy-Item config/config.example.json config/config.json
```

`config/config.json` wird relativ zum aktuellen Arbeitsverzeichnis geladen.
Mit `--config PFAD` lässt sich eine andere Datei auswählen. Fehlende Felder
verwenden ihre Standardwerte. Ungültige Dateien führen zu einer
Fehlermeldung im Terminal.

- `display` bestimmt Fenstergröße, Schrift, Farben (`#RRGGBB`), Rand
  in ganzen Prozent (0–49) und zusätzlichen Zeilenabstand
  (`line_spacing`, standardmäßig 4 Pixel). Mit `fullscreen: true` startet
  die Anwendung im Vollbild bei Desktop-Auflösung.
- `system.development_mode` aktiviert Tastaturprotokollierung und das
  Beenden per Escape. In diesem Modus lässt sich die Fenstergröße ändern.
  `system.allow_keyboard` steuert die Tastatur insgesamt.
  `system.show_splash` wird eingelesen und validiert.
- Änderungen der Schriftgröße per Tastatur gelten bis zum Programmende.

Unter `input` steht `shutdown_key` auf `"down"` für Pfeil runter.
`shutdown_hold_ms` legt die Haltedauer fest. Der Standard und zugleich
die Untergrenze sind 15000 ms. Ersetze einen älteren M5-`input`-Abschnitt
durch die folgenden Werte.

```json
{
  "input": {
    "shutdown_key": "down",
    "shutdown_hold_ms": 15000
  }
}
```

## Songordner und USB-Stick

LyricsPi liest beim Start die TXT-Dateien im obersten Verzeichnis der
Songquelle. Die Dateiendung kann beispielsweise `.txt` oder `.TXT` lauten.
Speichere die Dateien in UTF-8. Eine UTF-8-BOM am Dateianfang wird toleriert.
Zeilenumbrüche, Leerzeilen, Einrückungen und nachgestellte Leerzeichen
bleiben erhalten.

Verwende `Nummer_Songname.txt` oder `Nummer - Songname.txt`, etwa
`02_Abend.txt` oder `002 - Abend.txt`.
`2_Abend.txt` steht vor `10_Morgen.txt`. Führende Nullen ändern die Nummer
nicht. Bei gleicher Nummer gilt die Reihenfolge der vollständigen Dateinamen.
Unterordner und symbolische Links werden übersprungen.

Ohne weitere Einstellungen lädt LyricsPi die fünf frei erfundenen,
mehrseitigen Songs in `demo_songs`. Abschnittsmarker wie `[Strophe 1]`,
`[Refrain]` und `[Solo]` erscheinen als Teil des Songtexts.
Für einen anderen Ordner ergänze oder ändere den Abschnitt
`songs` in `config/config.json`. Relative Songordner und Mount-Pfade
beziehen sich auf den Projektroot. Absolute Pfade sind ebenfalls möglich.

```json
{
  "songs": {
    "source_mode": "directory",
    "directory": "demo_songs",
    "encoding": "utf-8-sig",
    "extension": ".txt",
    "sort_mode": "numeric_prefix",
    "recursive": false
  }
}
```

Setze unter Windows `"source_mode": "usb"`, um beim Start nach
eingebundenen Laufwerken zu suchen, die Windows als Wechseldatenträger
meldet. Bei mehreren Kandidaten bittet LyricsPi darum, nur einen
anzuschließen. Für ein USB-Laufwerk, das Windows als festes Laufwerk
einstuft, kann dessen Laufwerkswurzel explizit mit `directory` gewählt werden.

Auf dem Raspberry Pi erkennt der installierte systemd-Hilfsdienst den
ersten geeigneten FAT32- oder exFAT-USB-Stick und bindet ihn nur lesend
unter `/media/lyricspi/USB` ein. Ein Dienstneustart prüft den Stick erneut.
Bei einem direkten Linux-Start außerhalb des Dienstes kann ein bereits
eingehängter Ordner über die Konfiguration angegeben werden.

```json
{
  "songs": {
    "source_mode": "usb",
    "linux_mount_path": "/media/lyricspi/USB"
  }
}
```

Die Songquelle wird nur gelesen. Änderungen werden beim nächsten Start
übernommen. Ein fehlender Stick, ein fehlender oder nicht lesbarer Songordner
und eine leere Setlist erscheinen als Hinweis. Ungültige,
leere oder nicht lesbare Einzeldateien werden übersprungen und protokolliert.
Das Terminal zeigt die Anzahl geladener Songs und im Entwicklungsmodus den
aktuellen Song, die Seite und die Gesamtseitenzahl.

## Tests ausführen

```powershell
$lyricsPiTestTemp = Join-Path $env:TEMP ('lyricspi-test-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $lyricsPiTestTemp -p no:cacheprovider
```

Die Songtests erzeugen temporäre Dateien und simulieren die USB-Erkennung.
Die Anzeigetests verwenden den simulierten SDL-Videotreiber.
Die HID-Tests verwenden simulierte Tastaturereignisse und Zeitpunkte.
Die Installertests verwenden Bash, unter Windows beispielsweise Git Bash.

## Raspberry Pi 2 und 3

1. Raspberry Pi OS Lite 32 Bit installieren.
2. Im Repository `sudo bash deploy/install.sh` ausführen.
3. Einen FAT32- oder exFAT-USB-Stick mit den Songtexten einstecken.
4. Den Raspberry Pi neu starten. LyricsPi startet automatisch.

Die [Installationsanleitung](docs/raspberry-pi-installation.md) beschreibt
Raspberry Pi OS Lite, HDMI über DRM/KMS, den schreibgeschützten USB-Mount,
den systemd-Autostart, die Hardwareabnahme und die Wartung über SSH.
