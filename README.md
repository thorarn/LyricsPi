# LyricsPi

LyricsPi ist ein Offline-Songtext-Prompter für Live-Auftritte auf dem
Raspberry Pi 3. Unter Windows lädt LyricsPi beim Start die Setlist in den
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
| Pfeil hoch / runter | Blättert innerhalb des aktuellen Songs zurück / weiter |
| Minus / Plus | Verkleinert / vergrößert die Schrift innerhalb der konfigurierten Grenzen |
| Escape | Beendet das Programm im Entwicklungsmodus |

Nach dem letzten Song folgt wieder der erste. Vom ersten Song führt Pfeil
links zum letzten. Beim Blättern bleibt die Anzeige auf der ersten bzw.
letzten Seite stehen. Songtitel und Seitenzahlen stehen nur im Protokoll
des Entwicklungsmodus.

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
| B | Pfeil runter | Nächste Seite |
| C | Pfeil links | Vorheriger Song |
| D | Pfeil rechts | Nächster Song |
| A + C | Pfeil hoch + links | Schrift verkleinern |
| B + D | Pfeil runter + rechts | Schrift vergrößern |

Drücke die beiden Tasten einer Kombination gleichzeitig oder kurz
nacheinander. Die Einzelaktionen der erkannten Kombination entfallen.
Bei aktiven Kombinationen wartet ein einzelner Pfeiltastendruck
standardmäßig 150 ms, bevor er ausgeführt wird. Plus, Minus und Escape
reagieren weiterhin sofort.

Pygame liefert Tastaturereignisse ohne Gerätekennung. Die Kombinationen
gelten daher auch für die normale Tastatur. Fehlt ein Loslassereignis,
etwa beim Abziehen des Controllers, kann dieselbe Pfeiltaste nach einer
Ruhezeit wieder verwendet werden. Diese beträgt mindestens eine Sekunde
und bei längeren Zeitfenstern das Doppelte des Kombinationsfensters.
Bei Fokusverlust verwirft LyricsPi ausstehende Pfeiltastendrücke.

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

Unter `input` stellst du das Kombinationsfenster in Millisekunden ein.
Mit `enable_combinations: false` reagieren die Pfeiltasten unmittelbar.

```json
{
  "input": {
    "combo_window_ms": 150,
    "enable_combinations": true
  }
}
```

## Songordner und USB-Stick

LyricsPi liest beim Start die TXT-Dateien im obersten Verzeichnis der
Songquelle. Die Dateiendung kann beispielsweise `.txt` oder `.TXT` lauten.
Speichere die Dateien in UTF-8. Eine UTF-8-BOM am Dateianfang wird toleriert.
Zeilenumbrüche, Leerzeilen, Einrückungen und nachgestellte Leerzeichen
bleiben erhalten.

Verwende das Namensschema `Nummer_Songname.txt`, etwa `02_Abend.txt`.
`2_Abend.txt` steht vor `10_Morgen.txt`. Führende Nullen ändern die Nummer
nicht. Bei gleicher Nummer gilt die Reihenfolge der vollständigen Dateinamen.
Unterordner und symbolische Links werden übersprungen.

Ohne weitere Einstellungen lädt LyricsPi den mitgelieferten Ordner
`demo_songs`. Für einen anderen Ordner ergänze oder ändere den Abschnitt
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

Unter Linux verwendet `usb` den konfigurierten, bereits eingehängten
Mount-Punkt. Trage dort den tatsächlichen Mount-Pfad des Sticks ein.

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
.\.venv\Scripts\python.exe -m pytest
```

Die Songtests erzeugen temporäre Dateien und simulieren die USB-Erkennung.
Die Anzeigetests verwenden den simulierten SDL-Videotreiber.
Die HID-Tests verwenden simulierte Tastaturereignisse und Zeitpunkte.
