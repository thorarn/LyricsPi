# AGENTS.md – LyricsPi

## 1. Projektbeschreibung

**Projektname:** LyricsPi  
**Version:** 1.0 (in Entwicklung)  
**Plattform:** Raspberry Pi 3  
**Entwicklungsumgebung:** Windows 11 / VSCode / Codex  
**Programmiersprache:** Python 3

LyricsPi ist ein minimalistischer, vollständig offline nutzbarer Songtext-Prompter für Live-Auftritte.

Ein Raspberry Pi 3 zeigt Songtexte auf einem HDMI-Monitor an. Die Songtexte werden von einem USB-Stick eingelesen. Die Bedienung erfolgt über einen USB-MIDI-Fußcontroller mit vier Tasten.

Nach dem Einschalten des Raspberry Pi startet LyricsPi automatisch und zeigt den ersten Song an.

### Projektziele

- Zuverlässiger Betrieb auf der Bühne.
- Vollständig offline nutzbar.
- Sehr geringer Ressourcenverbrauch.
- Keine Desktop-Oberfläche im produktiven Betrieb.
- Einfache Bedienung über MIDI-Fußcontroller.
- Große und gut lesbare Songtexte.
- Einfache Wartung über SSH und Git.
- Saubere, modulare Softwarearchitektur.
- Möglichst wenige externe Abhängigkeiten.

---

## 2. Hardware und Betriebssystem

### Zielhardware

- Raspberry Pi 3
- HDMI-Monitor
- USB-Stick mit TXT-Songtexten
- M-VAVE MIDI-Fußcontroller mit vier Tasten (MVA-MCP)
- MicroSD-Karte mit Raspberry Pi OS

### Betriebssystem

- Raspberry Pi OS Lite (32 Bit), soweit mit dem eingesetzten Raspberry-Pi-Modell kompatibel.
- Kein vollständiger Desktop erforderlich.
- Automatischer Programmstart über systemd.
- SSH für Wartungsarbeiten.
- Keine permanente Internetverbindung erforderlich.

### Entwicklungsumgebung

- Windows 11
- Visual Studio Code
- OpenAI Codex
- Python 3.13
- Python Virtual Environment (`.venv`)
- Git / GitHub
- PowerShell

### Python-Kompatibilität

- Unter Windows wird Python 3.13 verwendet.
- Die Zielplattform verwendet die vom Raspberry Pi OS unterstützte Python-Version.
- Der Anwendungscode soll mit Python 3.11 oder neuer kompatibel bleiben.
- Ausschließlich in Python 3.13 verfügbare Sprachfunktionen dürfen nicht verwendet werden.
- Externe Bibliotheken müssen auf dem Raspberry Pi 3 verfügbar und lauffähig sein.
- Plattformabhängige Funktionen müssen gekapselt werden.

---

## 3. Technologiestack

### Verbindliche Technologien

| Bereich | Technologie |
|---|---|
| Programmiersprache | Python 3 |
| Darstellung | Pygame / SDL2 |
| MIDI-Kommunikation | Mido / python-rtmidi |
| Konfiguration | JSON |
| Tests | pytest |
| Paketverwaltung | pip / pyproject.toml |
| Versionsverwaltung | Git |
| Autostart | systemd |
| Logging | Python logging / systemd-Journal |

### Nicht erlaubte Technologien

Ohne ausdrückliche Genehmigung dürfen folgende Technologien nicht eingesetzt werden:

- Flask
- FastAPI
- Django
- Vue
- React
- Angular
- Electron
- Docker
- Datenbanken
- Browserbasierte Oberflächen
- Node.js als Laufzeitumgebung
- Cloud-Dienste

LyricsPi ist eine eigenständige Python-Anwendung ohne Webserver.

---

## 4. Verbindliche Projektstruktur

Die folgende Ordnerstruktur ist verbindlich.

Codex darf vorhandene Verzeichnisse und Module nicht eigenmächtig verschieben, umbenennen oder durch eine alternative Architektur ersetzen.

```text
LyricsPi/
│
├── src/
│   └── lyricspi/
│       ├── __init__.py
│       ├── main.py
│       ├── app.py
│       ├── config.py
│       ├── song_loader.py
│       ├── setlist.py
│       ├── layout.py
│       ├── renderer.py
│       ├── navigation.py
│       ├── midi_controller.py
│       ├── keyboard_controller.py
│       └── shutdown.py
│
├── tools/
│   └── midi_diagnostic.py
│
├── assets/
│   ├── logo.png
│   └── fonts/
│
├── config/
│   └── config.example.json
│
├── deploy/
│   ├── lyricspi.service
│   └── install.sh
│
├── tests/
│   └── __init__.py
│
├── docs/
│
├── AGENTS.md
├── README.md
├── pyproject.toml
└── .gitignore
```

### Regeln für die Projektstruktur

1. Die vorgegebene Ordnerstruktur muss erhalten bleiben.
2. Vorhandene Dateien dürfen nicht ohne ausdrückliche Anweisung umbenannt werden.
3. Vorhandene Dateien dürfen nicht verschoben werden.
4. Es dürfen keine alternativen Verzeichnisstrukturen eingeführt werden.
5. Neue Testdateien innerhalb von `tests/` sind ausdrücklich erlaubt.
6. Neue Dokumentationen innerhalb von `docs/` sind erlaubt.
7. Neue Dateien dürfen nur angelegt werden, wenn sie für den aktuellen Meilenstein erforderlich sind.
8. Neue Python-Module innerhalb von `src/lyricspi/` benötigen eine nachvollziehbare Begründung.
9. Änderungen an der Grundarchitektur benötigen eine ausdrückliche Freigabe.
10. Codex darf keine ungefragte Umstrukturierung oder Modernisierung durchführen.

Die virtuelle Umgebung `.venv/` befindet sich im Projektroot, wird aber nicht in Git versioniert.

---

## 5. Modulverantwortlichkeiten

### main.py

Programmeinstieg.

Verantwortlich für:
- Start der Anwendung.
- Einlesen der Startparameter.
- Initialisierung der Konfiguration.
- Aufruf der Anwendung.
- Behandlung schwerwiegender Startfehler.

### app.py

Zentrale Anwendungssteuerung.

Verantwortlich für:
- Hauptschleife.
- Anwendungszustand.
- Koordination der Komponenten.
- Verarbeitung interner Aktionen.
- Kontrolliertes Beenden.

### config.py

Konfigurationsverwaltung.

Verantwortlich für:
- JSON-Konfiguration einlesen.
- Konfigurationswerte validieren.
- Standardwerte bereitstellen.
- Fehlermeldungen bei ungültigen Einstellungen.

### song_loader.py

Laden der Songtexte.

Verantwortlich für:
- USB-Stick erkennen.
- TXT-Dateien finden.
- UTF-8-Dateien einlesen.
- Fehlerhafte Dateien behandeln.
- Inhalte im RAM bereitstellen.

### setlist.py

Songverwaltung.

Verantwortlich für:
- Numerische Sortierung der Dateien.
- Verwaltung der Songliste.
- Zugriff auf einzelne Songs.
- Verwaltung der aktuellen Songposition.

### layout.py

Text- und Seitenlayout.

Verantwortlich für:
- Automatischen Zeilenumbruch.
- Automatischen Seitenumbruch.
- Berücksichtigung der Schriftgröße.
- Berücksichtigung der Bildschirmauflösung.
- Berechnung der Seiten.
- Behandlung langer Strophen.
- Erhaltung notwendiger Leerzeichen und Zeilenstrukturen.

### renderer.py

Bildschirmausgabe.

Verantwortlich für:
- Initialisierung von Pygame.
- Ermittlung der Bildschirmauflösung.
- Vollbilddarstellung.
- Schwarzer Hintergrund.
- Weiße Schrift.
- Darstellung des aktuellen Songtextes.
- Darstellung von Start- und Fehlermeldungen.

### navigation.py

Navigation.

Verantwortlich für:
- Vorheriger Song.
- Nächster Song.
- Vorherige Seite.
- Nächste Seite.
- Begrenzung der Seitennavigation.
- Rücksprung auf Seite 1 beim Songwechsel.
- Umlauf vom letzten zum ersten Song.

### midi_controller.py

MIDI-Eingabeverarbeitung.

Verantwortlich für:
- MIDI-Geräte erkennen.
- MIDI-Nachrichten empfangen.
- MIDI-Tasten zuordnen.
- Tastenkombinationen erkennen.
- Entprellung und Mehrfachauslösungen verhindern.
- MIDI-Ereignisse in interne Aktionen übersetzen.
- Fehler bei unterbrochener MIDI-Verbindung behandeln.

### keyboard_controller.py

Tastatursteuerung.

Verantwortlich für:
- Tastatureingaben erkennen.
- Tastatureingaben in interne Aktionen übersetzen.
- Notbedienung ermöglichen.
- Windows-Entwicklung ohne MIDI-Controller ermöglichen.

### shutdown.py

Herunterfahren.

Verantwortlich für:
- Shutdown-Anforderung entgegennehmen.
- Sicherheitsbedingungen prüfen.
- Kontrolliertes Beenden der Anwendung.
- Sicheres Herunterfahren des Raspberry Pi.

Der produktive Shutdown muss mit möglichst geringen Systemberechtigungen umgesetzt werden.

---

## 6. Songdateien

### Dateiformat

- Ausschließlich TXT-Dateien.
- UTF-8-Encoding.
- Dateien befinden sich im Root-Verzeichnis des USB-Sticks.
- Unterverzeichnisse werden ignoriert.

### Dateinamen

Beispiele:

```text
01_Wonderwall.txt
02_Hallelujah.txt
03_Hotel_California.txt
04_Stand_By_Me.txt
```

### Sortierung

- Songdateien werden anhand des numerischen Präfixes sortiert.
- Die Sortierung erfolgt numerisch und nicht lexikografisch.
- Dateien ohne gültiges numerisches Präfix werden ignoriert und protokolliert.
- Bei gleichem numerischem Präfix entscheidet der Dateiname über die Reihenfolge.
- Die ursprünglichen Dateinamen werden nicht verändert.

### Laden der Dateien

- Songtexte werden beim Start geladen.
- Die Setlist wird einmalig aufgebaut.
- Änderungen am USB-Stick werden erst nach einem Neustart der Anwendung berücksichtigt.
- Nach erfolgreichem Einlesen befinden sich alle Songtexte im RAM.
- Der USB-Stick wird ausschließlich lesend verwendet.

### Fehlerbehandlung

- Kein USB-Stick: Hinweis auf dem Bildschirm.
- Keine gültigen Songdateien: Verständliche Hinweismeldung.
- Fehlerhafte Songdatei: Datei überspringen und Fehler protokollieren.
- Ein Fehler in einer Songdatei darf die Anwendung nicht beenden.

---

## 7. Darstellung

### Grundregeln

- Schwarzer Hintergrund.
- Weiße Schrift.
- Vollbilddarstellung.
- Keine Songtitel.
- Keine Menüleiste.
- Keine Fensterrahmen.
- Keine dauerhaft sichtbaren Bedienelemente.
- Keine Seitenzahlen im produktiven Modus.

### Textlayout

- Gut lesbare Schrift.
- Linksbündige Darstellung als vorläufige Standardannahme.
- Automatische Anpassung an die Bildschirmauflösung.
- Konfigurierbarer Seitenrand.
- Automatischer Zeilenumbruch.
- Automatischer Seitenumbruch.
- Leerzeilen zwischen Strophen erhalten.
- Lange Strophen bei Bedarf auf mehrere Seiten verteilen.
- Keine abgeschnittenen Zeilen.

### Schriftgröße

- Standardgröße aus JSON-Konfiguration.
- Verkleinerung über MIDI-Tastenkombination.
- Vergrößerung über MIDI-Tastenkombination.
- Mindest- und Höchstgröße konfigurierbar.
- Nach Änderung der Schriftgröße wird die Seiteneinteilung neu berechnet.
- Änderungen werden nicht dauerhaft gespeichert.
- Nach einem Neustart gilt wieder die konfigurierte Standardgröße.

### Akkorddarstellung

Songtexte können Akkorde enthalten.

- Führende Leerzeichen dürfen nicht unkontrolliert entfernt werden.
- Die Positionierung von Akkorden muss beim Layout berücksichtigt werden.
- Die genaue Darstellung von Akkorden wird vor Implementierung des endgültigen Textlayouts festgelegt.

---

## 8. MIDI-Steuerung

### Controller

M-VAVE MIDI-Fußcontroller mit vier Tasten.

Die tatsächlichen MIDI-Nachrichten werden vor der Implementierung mit einem Diagnoseprogramm ermittelt.

Keine festen MIDI-Note- oder Control-Change-Werte annehmen, bevor die Hardware getestet wurde.

### Tastenbelegung

| Taste | Funktion |
|---|---|
| 1 | Vorheriger Song |
| 2 | Nächster Song |
| 3 | Vorherige Seite |
| 4 | Nächste Seite |

### Tastenkombinationen

| Kombination | Funktion |
|---|---|
| 1 + 3 | Schrift verkleinern |
| 2 + 4 | Schrift vergrößern |

### Kombinationsregeln

- Kombinierte Tastendrücke müssen getrennt von Einzelaktionen behandelt werden.
- Eine erkannte Kombination darf nicht zusätzlich die Einzelaktionen auslösen.
- Die Erkennung muss das tatsächliche MIDI-Verhalten des Controllers berücksichtigen.
- Das Zeitfenster für Kombinationen soll konfigurierbar sein.
- Nicht unterstützte MIDI-Nachrichten werden ignoriert oder im Diagnosemodus protokolliert.
- Die Abschaltkombination wird nach einem Hardwaretest endgültig festgelegt.

---

## 9. Navigation

### Songwechsel

- Jeder Song beginnt beim Aufruf auf Seite 1.
- Taste 1 wechselt zum vorherigen Song.
- Taste 2 wechselt zum nächsten Song.
- Nach dem letzten Song beginnt die Navigation wieder beim ersten Song.
- Das Verhalten beim Zurückspringen vom ersten Song wird abschließend konfiguriert.

### Seitennavigation

- Taste 3 wechselt zur vorherigen Seite.
- Taste 4 wechselt zur nächsten Seite.
- Auf der ersten Seite bewirkt Zurückblättern keinen Seitenwechsel.
- Auf der letzten Seite bewirkt Weiterblättern keinen Seitenwechsel.
- Ein Seitenwechsel darf niemals automatisch den Song wechseln.

---

## 10. Tastatursteuerung

Die Anwendung muss auch ohne MIDI-Controller bedienbar sein.

### Standardbelegung

| Taste | Funktion |
|---|---|
| Pfeil links | Vorheriger Song |
| Pfeil rechts | Nächster Song |
| Pfeil hoch | Vorherige Seite |
| Pfeil runter | Nächste Seite |
| Minus | Schrift verkleinern |
| Plus | Schrift vergrößern |
| Escape | Anwendung im Entwicklungsmodus beenden |

Die Tastatur verwendet dieselbe interne Aktionsschnittstelle wie der MIDI-Controller.

---

## 11. Startverhalten

### Produktivbetrieb

1. Raspberry Pi wird eingeschaltet.
2. Raspberry Pi OS startet.
3. systemd startet LyricsPi automatisch.
4. LyricsPi zeigt einen kurzen Startbildschirm mit Logo.
5. USB-Stick und MIDI-Geräte werden geprüft.
6. Songdateien werden geladen.
7. Die Setlist wird aufgebaut.
8. Der erste Song wird auf Seite 1 angezeigt.

### Fehlerfälle

- Kein USB-Stick: Hinweis „USB-Stick einstecken“.
- Keine Songdateien: Hinweis „Keine Songtexte gefunden“.
- MIDI nicht verfügbar: Anwendung bleibt über Tastatur bedienbar.
- Bildschirmauflösung nicht ermittelbar: Fehler protokollieren und kontrolliert behandeln.

### Entwicklungsmodus

- Start in einem normalen Windows-Fenster.
- Kein automatischer System-Shutdown.
- Escape beendet die Anwendung.
- Bedienung über Tastatur möglich.

---

## 12. Konfiguration

Die Anwendung verwendet eine lokale JSON-Konfigurationsdatei.

### Dateien

```text
config/config.example.json
config/config.json
```

Die Beispieldatei gehört ins Git-Repository.

Die lokale Konfigurationsdatei darf von Git ignoriert werden.

### Anforderungen

- Konfiguration beim Programmstart laden.
- Konfigurationswerte validieren.
- Verständliche Fehlermeldungen erzeugen.
- Keine hart codierten absoluten Dateipfade.
- Plattformabhängige Pfade über pathlib behandeln.
- Sinnvolle Standardwerte definieren.
- MIDI-Mapping konfigurierbar halten.

---

## 13. Logging

- Python-Standardbibliothek `logging` verwenden.
- Logausgabe über stdout und stderr.
- Integration mit systemd-Journal im Produktivbetrieb.
- Keine zusätzliche Datenbank.
- Keine verpflichtenden eigenen Logdateien.

### Zu protokollierende Ereignisse

- Programmstart.
- Version und Konfiguration.
- USB-Erkennung.
- Anzahl geladener Songs.
- Fehler beim Lesen von Songdateien.
- MIDI-Geräteerkennung.
- MIDI-Verbindungsfehler.
- Unerwartete Programmfehler.
- Programmende und Shutdown.

Normale MIDI-Ereignisse sollen nur im Debugmodus ausführlich protokolliert werden.

---

## 14. Entwicklungsregeln

### Allgemeine Regeln

1. Ausschließlich den beauftragten Meilenstein bearbeiten.
2. Keine ungefragten zusätzlichen Funktionen implementieren.
3. Keine eigenmächtigen Architekturänderungen.
4. Keine bestehenden Module ohne Grund umstrukturieren.
5. Keine unnötigen Abhängigkeiten hinzufügen.
6. Bestehende Funktionen nicht ohne Grund verändern.
7. Keine Platzhalter, die funktionierendes Verhalten vortäuschen.
8. Fehler verständlich behandeln.
9. Hardwarezugriffe von der Geschäftslogik trennen.
10. Keine absoluten Betriebssystempfade im Quellcode.

### Codequalität

- PEP 8 beachten.
- Typannotationen verwenden.
- Python-Standardbibliothek bevorzugen.
- Kleine, verständliche Funktionen schreiben.
- Klassen nur einsetzen, wenn sie sinnvoll sind.
- Keine überkomplizierten Design Patterns.
- Keine unnötigen Abstraktionsschichten.
- Verständliche Variablennamen verwenden.
- Keine globale Zustandsverwaltung ohne nachvollziehbaren Grund.

### Plattformunabhängigkeit

Die Kernlogik darf nicht direkt von Raspberry-Pi-Hardware abhängen.

Folgende Funktionen müssen unter Windows ohne Raspberry Pi testbar sein:

- Konfiguration
- Songverwaltung
- Sortierung
- Navigation
- Textlayout
- Schriftgrößenberechnung
- MIDI-Aktionszuordnung mit simulierten Eingaben

---

## 15. Teststrategie

### Testframework

pytest

### Anforderungen

- Neue Kernfunktionen benötigen passende Unit-Tests.
- Tests müssen unter Windows ausführbar sein.
- Hardwareabhängige Tests gesondert kennzeichnen.
- Kein Zugriff auf echte MIDI-Hardware für reguläre Unit-Tests erforderlich.
- Testfälle für Fehlerbedingungen implementieren.
- Tests dürfen keine produktiven Dateien verändern.
- Fehlgeschlagene Tests nicht entfernen oder überspringen, um die Testausführung erfolgreich erscheinen zu lassen.

### Testaufruf

```powershell
python -m pytest
```

### Vor Abschluss eines Meilensteins

- Alle verfügbaren automatisierten Tests ausführen.
- Ergebnisse dokumentieren.
- Bekannte Probleme auflisten.
- Nicht getestete Hardwarefunktionen ausdrücklich kennzeichnen.

---

## 16. Git-Regeln

### Verbindliche Vorgaben

- Keine automatischen Git-Commits ohne ausdrückliche Freigabe.
- Kein automatischer Git-Push.
- Keine Branch-Wechsel ohne Anweisung.
- Keine Git-Resets ohne Freigabe.
- Keine bestehenden Dateien ungefragt löschen.
- Keine Änderung an AGENTS.md ohne ausdrückliche Freigabe.

### Vor der Abnahme

Codex muss:

1. Geänderte Dateien auflisten.
2. Implementierte Funktionen zusammenfassen.
3. Testergebnisse dokumentieren.
4. Bekannte Probleme benennen.
5. Auf Abnahme warten.

### Commit-Konvention

Empfohlene Commit-Messages:

```text
M1: Initial project setup
M2: USB song loading
M3: Song rendering
M4: Navigation and font controls
M5: MIDI integration
M6: Raspberry Pi deployment
M7: Stability improvements
M8: Release 1.0
```

---

## 17. Entwicklungsmeilensteine

### M1 – Projektgrundlage und Windows-Simulator

Ziele:
- Projektstruktur überprüfen.
- Python-Projekt initialisieren.
- Konfiguration implementieren.
- Pygame-Fenster erzeugen.
- Entwicklungsmodus implementieren.
- Tastatursteuerung vorbereiten.
- Unit-Tests einrichten.

Abnahme:
- Anwendung startet unter Windows.
- Schwarzer Hintergrund mit weißem Beispieltext.
- Tastaturaktionen werden erkannt.
- Escape beendet die Anwendung.
- Tests erfolgreich.

### M2 – USB und Songverwaltung

Ziele:
- USB-Erkennung.
- TXT-Dateien laden.
- Numerische Sortierung.
- UTF-8-Verarbeitung.
- Setlist-Verwaltung.
- Fehlerbehandlung.

Abnahme:
- Mindestens zehn Test-Songs werden korrekt verarbeitet.
- Sortierung funktioniert.
- Fehlerhafte Dateien werden behandelt.

### M3 – Songtext-Renderer

Ziele:
- Automatischer Zeilenumbruch.
- Automatischer Seitenumbruch.
- Strophenformatierung.
- Anpassung an Bildschirmauflösung.
- Schriftgrößenabhängiges Layout.

Abnahme:
- Lange Songs werden vollständig dargestellt.
- Keine Textzeile wird abgeschnitten.

### M4 – Navigation und Schriftgröße

Ziele:
- Songwechsel.
- Seitenwechsel.
- Begrenzungen der Navigation.
- Schriftgrößenänderung.
- Neuberechnung der Seiten.

Abnahme:
- Navigation funktioniert zuverlässig.
- Schriftänderungen verursachen keine Layoutfehler.

### M5 – MIDI-Integration

Ziele:
- MIDI-Diagnosewerkzeug.
- MIDI-Controller erkennen.
- MIDI-Mapping implementieren.
- Tastenkombinationen erkennen.
- MIDI-Fehlerbehandlung.

Abnahme:
- Alle vier Controller-Tasten funktionieren.
- Schriftgrößenkombinationen funktionieren.
- Keine unbeabsichtigten Einzelaktionen bei Kombinationen.

### M6 – Raspberry-Pi-Integration

Ziele:
- Installation auf Raspberry Pi.
- HDMI-Ausgabe.
- systemd-Service.
- Autostart.
- Startbildschirm.
- Sicheres Herunterfahren.
- SSH-Wartung.

Abnahme:
- Gerät startet direkt in LyricsPi.
- Keine Desktop-Oberfläche erforderlich.
- Bedienung über MIDI funktioniert.

### M7 – Stabilität und Fehlertests

Ziele:
- Fehlerbehandlung verbessern.
- USB-Fehler testen.
- MIDI-Verbindungsfehler testen.
- Programmneustart nach Absturz.
- Langzeittest durchführen.
- Ressourcenverbrauch prüfen.

Abnahme:
- Keine ungefangenen Fehler in den vorgesehenen Tests.
- Alle bekannten Fehlerfälle werden kontrolliert behandelt.

### M8 – Release V1.0

Ziele:
- Installationsskript fertigstellen.
- Konfiguration dokumentieren.
- Bedienungsanleitung erstellen.
- Deployment dokumentieren.
- Versionskennzeichnung.
- Release-Tests durchführen.

Abnahme:
- Reproduzierbare Installation.
- Vollständige Dokumentation.
- Bühnenbetrieb erfolgreich getestet.

---

## 18. Codex-Arbeitsablauf

Codex muss bei jedem neuen Auftrag den folgenden Ablauf einhalten.

### Phase 1 – Analyse

1. AGENTS.md vollständig lesen.
2. Bestehende Projektstruktur prüfen.
3. Aktuellen Meilenstein identifizieren.
4. Vorhandenen Code berücksichtigen.
5. Kurzen Implementierungsplan erstellen.

### Phase 2 – Implementierung

1. Nur den beauftragten Umfang bearbeiten.
2. Bestehende Architektur beibehalten.
3. Neue Funktionen in den vorgesehenen Modulen implementieren.
4. Fehlerfälle berücksichtigen.
5. Unit-Tests ergänzen.

### Phase 3 – Verifikation

1. Automatisierte Tests ausführen.
2. Fehler analysieren.
3. Fehler beheben.
4. Tests erneut ausführen.
5. Ergebnisse dokumentieren.

### Phase 4 – Abschluss

Codex erstellt eine Zusammenfassung mit:

- Implementierten Funktionen.
- Geänderten Dateien.
- Durchgeführten Tests.
- Testergebnissen.
- Bekannten Einschränkungen.
- Offenen Punkten.

Danach wartet Codex auf die Abnahme.

Der nächste Meilenstein darf nicht eigenständig begonnen werden.

---

## 19. Nichtfunktionale Anforderungen

### Stabilität

- Die Anwendung muss über längere Auftritte stabil laufen.
- Ein fehlerhafter Song darf keinen Programmabsturz verursachen.
- MIDI-Ereignisse dürfen die Hauptschleife nicht blockieren.
- Ein fehlender Controller darf den Programmstart nicht verhindern.

### Performance

- Geringer CPU-Verbrauch.
- Geringer RAM-Verbrauch.
- Keine unnötigen Hintergrundprozesse.
- Keine permanente Abfrage des USB-Sticks.
- Keine aufwendigen Animationen.

### Bedienbarkeit

- Keine Maus erforderlich.
- Keine Tastatur im regulären Bühneneinsatz erforderlich.
- Klare und gut lesbare Darstellung.
- Unmittelbare Reaktion auf Eingaben.
- Keine störenden Systemmeldungen im Auftritt.

### Wartbarkeit

- Saubere Modultrennung.
- Dokumentierte Konfiguration.
- Reproduzierbare Installation.
- Updates über Git.
- Fehlerdiagnose über systemd-Journal.

### Sicherheit

- Anwendung möglichst ohne Root-Rechte ausführen.
- SSH-Zugang absichern.
- USB-Stick ausschließlich lesend verwenden.
- Shutdown ausschließlich über kontrollierte Systemberechtigung.
- Keine Internetverbindung für den Bühneneinsatz erforderlich.

---

## 20. Prioritäten bei Entscheidungen

Wenn mehrere technische Lösungen möglich sind, gelten folgende Prioritäten:

1. Stabilität auf der Bühne.
2. Einfache Bedienung.
3. Geringer Ressourcenverbrauch.
4. Verständlicher und wartbarer Code.
5. Plattformunabhängigkeit der Kernlogik.
6. Einfache Installation.
7. Erweiterbarkeit.

Bei Konflikten zwischen diesen Prioritäten muss Codex die Entscheidung begründen.

**Grundsatz:** LyricsPi soll ein kleines, zuverlässiges Bühnengerät werden und keine unnötig komplexe Softwareplattform.