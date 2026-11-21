# LyricsPi

LyricsPi ist ein Offline-Songtext-Prompter für Live-Auftritte auf dem
Raspberry Pi 3. Der Windows-Simulator (M1) zeigt einen festen Beispieltext
in einem Pygame-Fenster. Der Text ist standardmäßig weiß auf schwarzem
Hintergrund und lässt sich per Tastatur vergrößern und verkleinern.

## Einrichtung unter Windows

Vorausgesetzt werden Windows, PowerShell und Python ab 3.11. Für die
Entwicklung unter Windows wird Python 3.13 verwendet. Führe die folgenden
Befehle im Projektordner aus. Falls `.venv` bereits existiert, reicht der
zweite Befehl für die Installation.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Simulator starten

```powershell
.\.venv\Scripts\python.exe -m lyricspi.main
```

In einer aktivierten `.venv` genügt `python -m lyricspi.main`. Die
Anwendung protokolliert Tastaturaktionen im Entwicklungsmodus im Terminal.

| Taste | Wirkung |
| --- | --- |
| Pfeil links / rechts | Protokolliert `PREVIOUS_SONG` / `NEXT_SONG` |
| Pfeil hoch / runter | Protokolliert `PREVIOUS_PAGE` / `NEXT_PAGE` |
| Minus / Plus | Verkleinert / vergrößert die Schrift innerhalb der konfigurierten Grenzen |
| Escape | Beendet das Programm im Entwicklungsmodus |

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

- `display` bestimmt Fenstergröße, Schrift, Farben (`#RRGGBB`) und Rand
  in ganzen Prozent (0–49). Mit `fullscreen: true` startet die Anwendung
  im Vollbild bei Desktop-Auflösung.
- `system.development_mode` aktiviert Tastaturprotokollierung und das
  Beenden per Escape. `system.allow_keyboard` steuert die Tastatur insgesamt.
  `system.show_splash` wird eingelesen und validiert. Die Demo startet
  direkt mit dem Beispieltext.
- Änderungen der Schriftgröße per Tastatur gelten bis zum Programmende.
  Bei einer sehr kleinen Fensterhöhe kann der Beispieltext unten abgeschnitten
  werden.

## Tests ausführen

```powershell
.\.venv\Scripts\python.exe -m pytest
```
