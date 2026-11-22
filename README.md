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

Die feste Kopfzeile zeigt links den Songtitel und rechts die Songnummer
aus dem Dateinamen samt führender Nullen. Titel, Nummer, Songtext und
Abschnittsmarker verwenden dieselbe Schriftgröße. Plus und Minus ändern
sie in der Songansicht und Songliste um eine Stufe.
Lange Titel werden mit Auslassungspunkten gekürzt. Die Songtexte
beginnen darunter. Der Scrollbalken links zeigt Position und Größe des
sichtbaren Ausschnitts. Umgebrochene Zeilen zählen einzeln. Bei einem
einseitigen Song füllt der weiße Balken die ganze Spur. Auf der letzten
Seite endet er bündig am unteren Rand.

Lange Zeilen werden entsprechend der Fensterbreite umgebrochen. LyricsPi
füllt jede Seite mit vollständigen Zeilen. Strophen, Refrains und
Abschnittsmarker können über Seitengrenzen hinweg dargestellt werden.
Nach einer Änderung von Schriftgröße, Rotation oder Fenstergröße berechnet LyricsPi die
Seiten neu und zeigt die Seite mit der bisherigen Textposition an.
Ist das Fenster zu klein für Songtext, zeigt es einen Hinweis.

Für Akkorde verwendet LyricsPi bevorzugt eine Monospace-Systemschrift.
Führende Leerzeichen bleiben beim Darstellen erhalten. Tabs werden zur
Anzeige in Abstände mit vier Spalten pro Tabstopp umgesetzt. Wenn lange
Akkord- und Textzeilen an unterschiedlichen Stellen umbrechen, können sich
die Akkorde relativ zum Text verschieben. Ist keine der unterstützten
Monospace-Schriften installiert, verwendet Pygame seine Standardschrift.

## Bedienung mit Fußcontroller und Tastatur

Verbinde den M-VAVE per USB im Tastaturmodus (HID) und gib dem
LyricsPi-Fenster den Tastaturfokus. Die Fußtasten senden dieselben
Pfeiltasten wie eine normale Tastatur.

| Fußtaste | Tastatursignal | Songansicht (`SONG_VIEW`) | Hauptmenü (`MAIN_MENU`) | Songliste (`SONG_LIST`) |
| --- | --- | --- | --- | --- |
| A | Pfeil hoch | Kurz zum vorherigen Song. Ab 5 Sekunden Hauptmenü öffnen. | Nächste Schriftgröße | Auswahl nach oben |
| B | Pfeil runter | Kurz zum nächsten Song. Ab 15 Sekunden herunterfahren oder LyricsPi beenden. | Ausgabe um 90° im Uhrzeigersinn drehen | Auswahl nach unten |
| C | Pfeil links | Vorherige Seite | Songliste öffnen | Markierten Song auf Seite 1 öffnen |
| D | Pfeil rechts | Nächste Seite | Zur vorherigen Songansicht zurückkehren | Zurück zum Hauptmenü |

In der Songansicht lösen A und B ihren Kurzdruck beim Loslassen aus.
C und D sowie die Menütasten reagieren beim Drücken. Ein ausgelöster
Langdruck verbraucht den Tastendruck. Der Songwechsel beginnt auf Seite 1
und läuft in beide Richtungen zwischen erstem und letztem Song um.
Beim Blättern bleibt die Anzeige an der ersten bzw. letzten Seite stehen.

Songtext, Kopfzeile, Hauptmenü und Songliste verwenden dieselbe Schriftgröße.
Im Hauptmenü wechselt A zyklisch in 4-px-Schritten von 28 bis 64 px. B schaltet
zwischen 0°, 90°, 180° und 270° um. Das Hauptmenü zeigt alle vier Optionen
auf einer Seite. Bei wenig Platz werden die Beschriftungen gekürzt. Falls
vier Zeilen mit der eingestellten Schriftgröße nicht passen, erscheint
der Hinweis „Fenster zu klein“.
Die Songliste zeigt Nummer und Titel in numerischer Reihenfolge und markiert
die Auswahl. Lange Einträge werden umgebrochen. Wenn ein markierter Titel
mehrere Bildschirmseiten braucht, wechselt die Anzeige automatisch weiter.
Die Tasten bleiben dabei direkt bedienbar.
Mit D aus der Songliste und erneut D im Hauptmenü kehrst du zur bisherigen
Textstelle zurück. Escape beendet LyricsPi im Windows-Entwicklungsmodus.

Für einen Langdruck muss das Betriebssystem die Pfeiltaste durchgehend
als gedrückt melden. Bei kurzen HID-Impulsen stehen die Langdruckfunktionen
nur über eine Tastatur mit tatsächlich gehaltenen Tasten zur Verfügung.
Autorepeat wird ignoriert. Bei Fokusverlust oder wenn der gemeldete
Tastenzustand ohne `KEYUP` endet, verwirft LyricsPi die Messung.
Das Debug-Protokoll enthält die Tastenereignisse und gemessenen Haltezeiten.

Auf dem Raspberry Pi im Produktivmodus gibt LyricsPi bei langem B zuerst
die Anzeige frei und fordert anschließend über logind das reguläre
Herunterfahren an. Unter Windows und im Entwicklungsmodus endet nur die
Anwendung. Der Langdruck beginnt bei 15 Sekunden, sofern die Konfiguration
keine längere Haltedauer vorgibt.

Die Schritte zur Hardwareabnahme stehen in der Installationsanleitung.
[HDMI, Stick und Controller abnehmen](docs/raspberry-pi-installation.md#4-hdmi-stick-und-controller-abnehmen)

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

- `display` bestimmt Fenstergröße, Farben (`#RRGGBB`), Rand
  in ganzen Prozent (0–49) und zusätzlichen Zeilenabstand
  (`line_spacing`, standardmäßig 4 Pixel). Mit `fullscreen: true` startet
  die Anwendung im Vollbild bei Desktop-Auflösung.
- `system.development_mode` aktiviert Tastaturprotokollierung und unter
  Windows das Beenden per Escape. In diesem Modus lässt sich die Fenstergröße ändern.
  `system.allow_keyboard` steuert die Tastatur insgesamt.
  `system.show_splash` wird eingelesen und validiert.
- Änderungen der Schriftgröße und Rotation werden sofort in `settings.json`
  gespeichert. Ohne lokale Vorgabe ist der Standard 28 px bei 0°. Beim
  ersten Start nach einem Update werden gültige Werte aus `display.font_size` und `display.rotation`
  übernommen, sofern sie in der lokalen Konfiguration vorliegen. Danach
  haben die gespeicherten Einstellungen Vorrang. Eine übernommene Größe
  außerhalb des neuen Zyklus bleibt bis zur nächsten Größenänderung gültig.
- Unter Windows liegt die Datei in `%LOCALAPPDATA%\LyricsPi`. Der
  Raspberry-Pi-Dienst legt sie unter `/var/lib/lyricspi` ab.

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
In Zeile 1 steht der Titel für die Kopfzeile. Zeile 2 ist die Trennzeile.
Der angezeigte Songtext beginnt in Zeile 3. Ab dort bleiben Zeilenumbrüche,
Leerzeilen, Einrückungen und nachgestellte Leerzeichen beim Laden erhalten.
Bei einer leeren Titelzeile übernimmt LyricsPi den Titel aus dem Dateinamen.

Verwende `Nummer_Songname.txt` oder `Nummer - Songname.txt`, etwa
`02_Abend.txt` oder `002 - Abend.txt`.
`2_Abend.txt` steht vor `10_Morgen.txt`. Führende Nullen ändern die Nummer
nicht. Bei gleicher Nummer gilt die Reihenfolge der vollständigen Dateinamen.
Unterordner und symbolische Links werden übersprungen.

Ohne weitere Einstellungen lädt LyricsPi die Songs aus `demo_songs`.
Abschnittsmarker wie `[Strophe 1]`,
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
