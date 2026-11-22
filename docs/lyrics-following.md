# Automatische Songtextverfolgung unter Windows

Der experimentelle Modus folgt dem gerade ausgewählten Song. Er markiert die zuletzt bestätigte Originalzeile grau und behält bei umgebrochenen Zeilen die Markierung für alle sichtbaren Teile bei. Strophenmarkierungen und Leerzeilen werden angezeigt und beim Textabgleich übersprungen.

## Installation

Im Projektverzeichnis mit Windows und Python 3.13 x64 ausführen.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[lyrics-following]'
.\.venv\Scripts\python.exe -c "from faster_whisper import download_model; print(download_model('small'))"
```

Der zweite Befehl lädt einmalig das mehrsprachige Small-Modell in den lokalen Cache. `model` unterstützt `tiny`, `base`, `small` und `medium`. Für ein anderes Modell den Namen im Download-Befehl und in der Konfiguration anpassen. LyricsPi verwendet beim Start ausschließlich einen lokalen Cache oder einen bereits vorhandenen CTranslate2-Modellordner mit vollständigen Modelldateien einschließlich `tokenizer.json`. Ein Ordnerpfad kann absolut oder relativ zum Projektverzeichnis sein. Die optionalen Bibliotheken sind PyAudioWPatch, faster-whisper und NumPy. [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Wiedergabegerät wählen

WASAPI-Loopback erfasst den Ton des gewählten Windows-Ausgabegeräts im Hintergrund. Die Wiedergabe über Lautsprecher, Kopfhörer oder HDMI läuft normal weiter. Lokale Player und Browser können dieselbe Ausgabe verwenden. Exklusive oder geschützte Wiedergabe kann von der Aufnahme ausgenommen sein. LyricsPi speichert Audiodaten nur während der Verarbeitung im Arbeitsspeicher. [Microsoft-Dokumentation zu WASAPI-Loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)

LyricsPi wandelt das aufgenommene 16-Bit-PCM mit NumPy in normalisiertes Mono-Audio mit 16 kHz und `float32` um. Whisper erhält das Array direkt. Damit entfällt die WAV-Decodierung über PyAV, die den Fehler `open() got an unexpected keyword argument 'metadata_errors'` auslösen konnte.

```powershell
.\.venv\Scripts\python.exe -m pyaudiowpatch
```

Die Liste erscheint auch im LyricsPi-Protokoll beim Start der Aufnahme. `audio_device: "default"` wählt beim Start das Windows-Standardgerät, sofern sein Loopback eindeutig zugeordnet werden kann. Für eine andere Ausgabe den vollständigen Namen samt `[Loopback]` oder den aktuellen Loopback-Index als Zeichenkette eintragen. Nach einem Gerätewechsel die Aufnahme über **F8** aus- und wieder einschalten. Die Nummerierung kann sich nach einem Wechsel ändern.

## Observe und Auto

`config/config.example.json` als Vorlage für `config/config.json` verwenden. `system.development_mode` muss für die Textverfolgung unter Windows aktiv sein. Für eine manuelle Abnahme kann die Anwendung mit deaktivierter Textverfolgung starten. Dann einen Song mit passender Textdatei auswählen und im Songfenster **F8** drücken. Mit `enabled: true` startet die Textverfolgung direkt.

```json
{
  "lyrics_following": {
    "enabled": false,
    "mode": "observe",
    "audio_source": "windows_loopback",
    "audio_device": "default",
    "language": "de",
    "model": "small",
    "beam_size": 5,
    "window_seconds": 6,
    "overlap_seconds": 2,
    "use_initial_prompt": false,
    "hotwords": "",
    "confidence_threshold": 0.75,
    "pause_duration_ms": 800,
    "prefer_pause": true,
    "min_turn_interval_ms": 5000,
    "highlight_current_line": true,
    "auto_page_turn": false
  }
}
```

```powershell
.\.venv\Scripts\python.exe -m lyricspi.main --config config/config.json
```

- **Observe** markiert die bestätigte Zeile und meldet mögliche Seitenwechsel im Terminal.
- **F9** wechselt bei laufender Textverfolgung zwischen Observe und Auto. Für Auto beim Start `mode: "auto"` und `auto_page_turn: true` setzen. Die Tastaturumschaltung gilt für die laufende Sitzung.
- **Auto** blättert vorwärts, sobald eine ausreichend bestätigte Zeile auf einer späteren Seite erkannt wird. Mit `prefer_pause: true` kann eine erkannte Audiopause den Wechsel beschleunigen. Bei laufender Musik wartet der Tracker kurz auf neue Hinweise. `pause_duration_ms` definiert die Mindestdauer des leisen Audioabschnitts und `min_turn_interval_ms` den Mindestabstand zu einem Wechsel oder manuellen Eingriff.
- **F8** schaltet die Textverfolgung aus oder wieder ein. Bei einem Aufnahme- oder Modellfehler bleibt die normale Song- und Seitennavigation verfügbar. Manuelle Navigation setzt den Tracker auf der gewählten Seite zurück. Alte Ergebnisse werden dabei verworfen.
- `language` akzeptiert `de` und `en`. Bei `highlight_current_line: false` kann Auto weiterblättern, während die Zeilenfarbe und der Hintergrund dem normalen Layout entsprechen.
- `beam_size` steuert die Anzahl der Suchpfade im Decoder. `window_seconds` legt die Fensterlänge fest (2–15 Sekunden). `overlap_seconds` muss kleiner als das Fenster sein.
- `use_initial_prompt` ist experimentell und standardmäßig aus. Aktiviert nutzt es bis zu drei Textzeilen ab der bestätigten Position, begrenzt auf 32 Wörter und 160 Zeichen. `hotwords` ist eine durch Kommas getrennte Liste besonderer Wörter oder kurzer Phrasen. Pro Fenster gelangen bis zu acht Einträge aus den relevanten Zeilen in den Hinweis. Ein leerer Wert schaltet die Funktion aus.

## Diagnose und Abnahme

1. Einen mehrseitigen Song mit passender Aufnahme auswählen. Aufnahme und Wiedergabe in Observe starten. Die graue Markierung mit der tatsächlich gesungenen Zeile vergleichen und im Terminal die vorgeschlagenen Seitenwechsel prüfen.
2. Die Wiedergabe pausieren. Die zuletzt sichtbare Markierung und die Seite sollten stehen bleiben. Nach dem Fortsetzen prüfen, ob neue eindeutige Zeilen wieder erkannt werden.
3. Auto mit **F9** einschalten und den Song über mehrere Seiten abspielen. Vorwärts und rückwärts manuell blättern und prüfen, ob Audio vom früheren Seitenstand verworfen wird. Am Songende bleibt derselbe Song ausgewählt.
4. Für Abweichungen Ausgabegerät, Modell, Songabschnitt, tatsächliche und markierte Zeile sowie Versatz festhalten. Bei wiederholten Refrains den Einzelfall mit dem entsprechenden Übergang aus der vorigen Strophe prüfen.

Das Terminal meldet verfügbare Geräte und Fehler. Im Entwicklungsmodus erscheinen Modell, Fensterzeiten, Transkriptionsdauer und erkannte Wörter mit Zeitstempeln und Whisper-Werten. Der Textabgleich meldet den besten Kandidaten, den Matching-Score, die bestätigte Position und Gründe für Ablehnungen wie mehrdeutige Refrains oder bereits verarbeitetes Audio. `Markierung` meldet die Zeit vom letzten zugeordneten Wort bis zur sichtbaren Hervorhebung. Der anwendungseigene Score von 0 bis 1 bewertet die Abdeckung der Referenzzeile mit ähnlichen Wörtern in passender Reihenfolge.

## Grenzen und Performance

Whisper arbeitet lokal auf der CPU mit zwei Inferenz-Threads. Mit den Standardwerten endet das erste Fenster nach sechs Sekunden. Weitere Fenster enden alle vier Sekunden. Bei langen gesungenen Zeilen kann der Abgleich Wörter aus dem vorigen Fenster ergänzen. Für Fortschritt müssen neue Wörter zeitlich zum aktuellen Abschnitt passen. Nahe, starke Treffer können direkt bestätigen. Schwächere Treffer benötigen zusätzliche Wörter am Fensterübergang oder eine passende Folgezeile. Größere Sprünge erfordern eine stark passende Phrase mit einem passenden unmittelbaren Vorlauf. Die maximale Länge der Decoderausgabe wächst mit der Fensterlänge und begrenzt den Aufwand bei Wiederholungsschleifen. Bei Rückstand verwirft LyricsPi ältere Audio- und Erkennungsergebnisse.

Begleitung, undeutlicher Gesang und andere gleichzeitig abgespielte Quellen können die Erkennung verschlechtern. Einzelwortzeilen liefern für diesen Prototyp zu wenig Evidenz. Identische Refrains benötigen eindeutigen Kontext. Bei einer über mehrere Seiten verteilten Originalzeile beziehen sich Treffer auf die gesamte Zeile. Ein Wechsel innerhalb dieser Zeile ist manuell möglich. Für Musik und Gesang sind hardwareabhängige Erkennungsqualität, CPU-Last und Ende-zu-Ende-Latenz im Abnahmelauf zu messen.

## Modellvergleich mit einer lokalen Audiodatei

Das Werkzeug akzeptiert eine lokale 16-Bit-PCM-WAV-Datei, den zugehörigen UTF-8-Text und eine JSON-Liste mit Zeitmarken. Jede Marke hat die Felder `line` (Dateizeile ab 1, einschließlich der Positionen von Leerzeilen und Markern), `start` und `end` (Sekunden ab Dateianfang). Das Werkzeug verwendet die Audiofenster, den PCM-Pfad und den Positionsabgleich des Simulators. `--config` übernimmt dessen Einstellungen. Mit `--debug` erscheinen Einzelzeiten und Treffer für jedes Fenster.

Treffer werden pro annotierter Zeilenposition gezählt. Die zeitliche Mitte des zugeordneten Wortsegments muss innerhalb der Marke liegen. Eine falsche bestätigte Zuordnung zählt als Fehlsprung. Die mittlere Verzögerung reicht vom markierten Zeilenbeginn bis zum Fensterende einschließlich tatsächlich gemessener Transkriptionszeit und gegebenenfalls aufgelaufenem Rückstand. Pygame, WASAPI und die Bildschirmaktualisierung werden im Dateitest umgangen.

### Reproduzierbare Testclips

Der Gesangstest verwendet die ersten 66 Sekunden der Aufnahme von *Auld Lang Syne* mit Frank C. Stanley (1910). Die englischen Untertitel liefern acht vorab markierte Zeilen. Zum Vergleich enthält der JFK-Sprachclip aus OpenAI Whisper vier zeitlich markierte Textstellen in 22 Sekunden. Die zweite Zeile erscheint später erneut. [UCSB Cylinder 4410](https://www.library.ucsb.edu/OBJID/Cylinder4410) · [Untertitel, feste Revision](https://commons.wikimedia.org/w/index.php?title=TimedText:Auld_Lang_Syne.ogg.en.srt&oldid=1217335773) · [OpenAI-Whisper-Testclip](https://github.com/openai/whisper/blob/v20240930/tests/jfk.flac)

```powershell
curl.exe --fail --location --output .venv/lf4-jfk.flac https://raw.githubusercontent.com/openai/whisper/v20240930/tests/jfk.flac
curl.exe --fail --location --output .venv/lf4-auld.mp3 https://cylinders.s3-us-west-2.amazonaws.com/4000/4410/cusb-cyl4410d.mp3
curl.exe --fail --location --output .venv/lf4-auld.srt "https://commons.wikimedia.org/w/index.php?title=TimedText:Auld_Lang_Syne.ogg.en.srt&oldid=1217335773&action=raw"
.\.venv\Scripts\python.exe -c "from faster_whisper import download_model; [download_model(model) for model in ('tiny', 'base', 'small')]"
@'
import json
import re
import wave
from pathlib import Path

import av

root = Path(".venv")
rate = 16000

def read_pcm(name):
    resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
    with av.open(str(root / name)) as source:
        parts = [sample.to_ndarray().tobytes() for frame in source.decode(audio=0)
                 for sample in resampler.resample(frame)]
        parts.extend(sample.to_ndarray().tobytes() for sample in resampler.resample(None))
    return b"".join(parts)

def write_wav(name, pcm):
    with wave.open(str(root / name), "wb") as target:
        target.setparams((1, 2, rate, 0, "NONE", ""))
        target.writeframes(pcm)

def seconds(stamp):
    hours, minutes, sec, millis = map(int, re.split("[:,]", stamp))
    return hours * 3600 + minutes * 60 + sec + millis / 1000

write_wav("lf4-auld.wav", read_pcm("lf4-auld.mp3")[:66 * rate * 2])
srt = (root / "lf4-auld.srt").read_text(encoding="utf-8-sig")
lyrics, cues = [], []
for entry in re.split(r"\n\s*\n", srt.strip())[:8]:
    _, timing, *text = entry.splitlines()
    start, end = map(seconds, timing.split(" --> "))
    lyrics.append(" ".join(text))
    cues.append({"line": len(lyrics), "start": start, "end": end})
assert len(cues) == 8
(root / "lf4-auld.txt").write_text("\n".join(lyrics), encoding="utf-8")
(root / "lf4-auld-cues.json").write_text(json.dumps(cues), encoding="utf-8")

original = read_pcm("lf4-jfk.flac")
phrases = [
    (0, 2.85, 2.0, "And so, my fellow Americans"),
    (3.01, 7.50, 5.2, "Ask not what your country can do for you"),
    (7.50, 10.9, 10.5, "Ask what you can do for your country"),
    (3.01, 7.50, 17.0, "Ask not what your country can do for you"),
]
pcm = bytearray(22 * rate * 2)
cues = []
for number, (start, end, at, _) in enumerate(phrases, 1):
    begin = round(start * rate) * 2
    part = original[begin:begin + round((end - start) * rate) * 2]
    offset = round(at * rate) * 2
    pcm[offset:offset + len(part)] = part
    cues.append({"line": number, "start": at, "end": round(at + end - start, 2)})
write_wav("lf4-test.wav", pcm)
(root / "lf4-test.txt").write_text("\n".join(text for _, _, _, text in phrases), encoding="utf-8")
(root / "lf4-cues.json").write_text(json.dumps(cues), encoding="utf-8")
(root / "lf4-config.json").write_text(json.dumps({"lyrics_following": {"language": "en"}}), encoding="utf-8")
'@ | .\.venv\Scripts\python.exe -
.\.venv\Scripts\python.exe tools/lyrics_benchmark.py .venv/lf4-auld.wav .venv/lf4-auld.txt .venv/lf4-auld-cues.json --config .venv/lf4-config.json --debug
.\.venv\Scripts\python.exe tools/lyrics_benchmark.py .venv/lf4-test.wav .venv/lf4-test.txt .venv/lf4-cues.json --config .venv/lf4-config.json --debug
```

### Messwerte

Windows, Intel Core i7-13700H, Python 3.13, faster-whisper 1.2.1, CPU mit INT8 und zwei Inferenz-Threads. Beam 5, 6 Sekunden Fenster und 2 Sekunden Überlappung. Prompt und Hotwords waren bei den Vergleichsläufen aus.

**Gesprochene Referenz mit wiederholter Zeile** (fünf Fenster pro Modell)

| Modell | Zeilentreffer | Fehlsprünge | Verzögerung Ø | Zeit/Fenster Ø |
|---|---:|---:|---:|---:|
| tiny | 4/4 (100 %) | 0 | 4,73 s | 0,41 s |
| base | 4/4 (100 %) | 0 | 5,24 s | 0,90 s |
| small | 4/4 (100 %) | 0 | 6,97 s | 2,65 s |

Alle drei Modelle bestätigten auch die wiederholte Zeile an ihrer späteren Position. Tiny ließ in den mittleren Fenstern Wörter aus. Der Abgleich ordnete die Phrase weiterhin richtig zu.

**Historische Gesangsaufnahme** (16 Fenster pro Modell)

| Modell | Zeilentreffer | Fehlsprünge | Verzögerung Ø | Zeit/Fenster Ø |
|---|---:|---:|---:|---:|
| tiny | 0/8 | 0 | – | 0,49 s |
| base | 1/8 | 0 | 6,86 s | 1,09 s |
| small | 1/8 | 0 | 9,33 s | 3,15 s |

Base und Small bestätigten jeweils dieselbe Zeile. Whisper ließ in vielen Fenstern mehrere gesungene Wörter aus oder ersetzte sie. Der Tracker hielt dann die Position. Die geringe Zahl bestätigter Zeilen erklärt mit, warum in diesem Test kein Fehlsprung gezählt wurde. Diese beiden Aufnahmen liefern einen Ausgangspunkt für weitere Messungen mit aktuellen Musikproduktionen. Die Live-Latenz über WASAPI ist separat zu prüfen.
