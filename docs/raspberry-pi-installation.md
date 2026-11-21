# LyricsPi auf dem Raspberry Pi 2 und 3 installieren

Der Installer akzeptiert Raspberry Pi 2 Model B (Revisionen 1.1, 1.2 und
1.3) sowie Raspberry Pi 3 Model B, B+ und A+. Pi 2 Rev. 1.1 verwendet einen
32-Bit-Cortex-A7. Die neueren Pi-2-Revisionen und der Pi 3 haben einen
Cortex-A53. Für alle Modelle ist **Raspberry Pi OS Lite 32 Bit
(`armhf`)** vorgesehen. Ein 64-Bit-Kernel auf einem Cortex-A53 wird
akzeptiert, wenn der Userspace 32 Bit ist. Für die Abnahme werden ein
HDMI-Monitor, ein USB-Stick und ein M-VAVE im USB-HID-Modus benötigt.
[Raspberry-Pi-Hardware](https://www.raspberrypi.com/documentation/computers/sbcs.html)

| Image | Python und Pygame aus der Distribution |
| --- | --- |
| Raspberry Pi OS Lite 32 Bit (Trixie, empfohlen) | Python 3.13, Pygame 2.6.1 |
| Raspberry Pi OS Legacy Lite 32 Bit (Bookworm) | Python 3.11, Pygame 2.1.2 |

Die Modell- und Paketwahl wurde mit simulierten Systemdaten und den
Paketinformationen geprüft. Die Installation und der Betrieb auf echter
Pi-2-Hardware stehen noch zur Abnahme aus. Das gilt auch für den
Bookworm-Pfad.
[Raspberry Pi OS Lite](https://www.raspberrypi.com/software/operating-systems/) · [Trixie-Paket](https://packages.debian.org/trixie/armhf/python3-pygame) · [Bookworm-Paket](https://packages.debian.org/bookworm/armhf/python3-pygame)

## 1. MicroSD und SSH vorbereiten

1. In Raspberry Pi Imager das Pi-Modell und **Raspberry Pi OS Lite (32-bit)**
   auswählen. Für Bookworm die Variante **Legacy Lite (32-bit)** auswählen.
   Die gewünschte MicroSD-Karte auswählen und das Image schreiben.
2. In der Betriebssystemanpassung Benutzer, Hostname und bei Bedarf WLAN
   festlegen. SSH mit Schlüsselauthentifizierung aktivieren und den öffentlichen
   Schlüssel des Wartungsrechners hinterlegen.
3. MicroSD einsetzen, HDMI-Monitor einschalten und den Pi starten. Per SSH
   anmelden. `wartung` und `lyricspi.local` durch die eigenen Werte ersetzen.
   Wenn mDNS fehlt, die IP-Adresse des Pi verwenden.

```bash
ssh wartung@lyricspi.local
tr -d '\000' </proc/device-tree/model; printf '\n'
uname -m
dpkg --print-architecture
getconf LONG_BIT
cat /etc/os-release
```

SSH im vertrauenswürdigen Wartungsnetz verwenden. Wenn SSH auf einem
bestehenden System nachträglich abgesichert wird, die Schlüsselanmeldung
zuerst in einem zweiten Terminal prüfen. Erst danach Passwortanmeldung
deaktivieren und die SSH-Konfiguration mit `sudo sshd -t` prüfen.
[Raspberry-Pi-Anleitung zur Ersteinrichtung](https://www.raspberrypi.com/documentation/computers/getting-started.html)

## 2. Projekt und Song-Stick vorbereiten

```bash
sudo apt-get update
sudo apt-get install git
git clone 'DEINE_GIT_URL' "$HOME/LyricsPi"
cd "$HOME/LyricsPi"
```

`DEINE_GIT_URL` durch die HTTPS- oder SSH-Clone-URL des Projekts ersetzen.
Der Checkout dient der Wartung. Der Dienst startet aus `/opt/lyricspi`.

Einen FAT32- oder exFAT-formatierten Stick verwenden und die nummerierten
UTF-8-TXT-Dateien in sein Wurzelverzeichnis kopieren. Der Stick kann
bei der Installation abgezogen bleiben.

## 3. Installieren und starten

```bash
sudo bash deploy/install.sh
```

Der Installer startet LyricsPi sofort und aktiviert den Autostart.
Wenn der Song-Stick erst danach eingesteckt wird, lädt ihn
`sudo systemctl restart lyricspi.service` oder ein Neustart des Pi.

Der Installer installiert fehlende Systempakete per APT. Er prüft die
System-Python-Version (mindestens 3.11) und verwendet `python3-pygame`
samt SDL2 aus derselben Distribution. LyricsPi wird offline in eine venv
mit Zugriff auf diese Systempakete installiert. Die Prüfung zeigt die
Pygame- und SDL-Version und kontrolliert, ob SDL KMSDRM anbietet.
Er prüft außerdem, ob die Laufzeitbibliotheken für EGL, GBM, DRM und
den von SDL verwendeten OpenGL-ES-Pfad geladen werden können. Die
Anwendung selbst verwendet weiterhin Pygame-Oberflächen.
Bookworm liefert DejaVu Sans Mono über `fonts-dejavu-core`. Auf Trixie
kommt sie aus `fonts-dejavu-mono`. Pygame findet die Schrift über
`fontconfig`. Der Windows-Entwicklungsmodus verwendet
weiterhin Python 3.13 und Pygame ab 2.6.1.
[Bookworm-setuptools](https://packages.debian.org/bookworm/armhf/python3-setuptools) · [Bookworm-Schriftpaket](https://packages.debian.org/bookworm/all/fonts-dejavu-core/filelist)

- [deploy/install.sh](../deploy/install.sh) installiert Anwendung, venv,
  Produktionskonfiguration, Systembenutzer, beide Dienste und
  Polkit-Regel. Vor einem Update sichert es eine vorhandene Installation
  und die von ihm verwendeten Systemdateien in `/opt/.lyricspi-backup.*`.
- [deploy/lyricspi.service](../deploy/lyricspi.service) startet LyricsPi als
  Systembenutzer `lyricspi` auf Konsole 7. Die Gruppen `video`, `render` und
  `input` erlauben DRM/Grafik und Linux-Eingabe. systemd stellt die Konsole
  bereit. Zwei feste Startbefehle wechseln auf Konsole 7 und deaktivieren
  dort das Ausblenden. Python und der Renderer laufen als `lyricspi`.
- [lyricspi-usb.service](../deploy/lyricspi-usb.service) sucht beim Start
  kurz nach einem USB-Massenspeicher mit FAT32 oder exFAT. Der Hilfsdienst
  schließt Systemlaufwerke und erkannte SD-Karten aus. Er prüft Geräte in
  alphabetischer Reihenfolge und Partitionen innerhalb eines Geräts
  numerisch. Der erste geeignete Datenträger wird unter
  `/media/lyricspi/USB` mit `ro,nosuid,nodev,noexec` eingehängt.
  Der Hilfsdienst hat ein Startlimit von zwölf Sekunden pro Aufruf.
  Fehlt der Stick oder schlägt der Mount fehl, zeigt LyricsPi
  `USB-Stick einstecken.`.
- `49-lyricspi-poweroff.rules` erlaubt dem Dienstkonto den regulären
  logind-Poweroff auch bei weiteren aktiven Sitzungen. Eine Berechtigung
  zum Übergehen von Shutdown-Inhibitoren wird dafür nicht erteilt.

Ein geeigneter und bereits schreibgeschützter Mount am Ziel kann
wiederverwendet werden. Andere vorhandene Mounts werden übersprungen.
Beim Stopp hängt der Helfer nur selbst erzeugte Mounts aus. USB-Kartenleser,
die sich lediglich als generischer USB-Massenspeicher melden, lassen sich
anhand dieser Angaben nicht von einem USB-Stick unterscheiden. Verwende
einen einzelnen Song-Stick.

Der Installer aktiviert den Autostart für den nächsten Boot. Ein unerwarteter
Absturz führt zu einem Neustart nach fünf Sekunden, mit höchstens drei
Starts in zwei Minuten. Für einen erneuten Start nach einem behobenen
Fehler kann der Zähler zurückgesetzt werden.

Bei jedem erfolgreichen Installationslauf kopiert der Installer beide
systemd-Units, lädt systemd neu und startet den Dienst neu. Bei einer
aktuellen Anwendung mit funktionsfähiger venv und vorhandenen Systempaketen
entfallen APT und die Python-Neuinstallation. Bei Anwendungsupdates werden
die vorhandene venv und die lokale JSON-Konfiguration übernommen.

```bash
sudo systemctl reset-failed lyricspi.service
sudo systemctl restart lyricspi.service
sudo journalctl -u lyricspi.service -u lyricspi-usb.service -f
```

Die lokale Konfiguration steht in `/opt/lyricspi/config/config.json` und
lässt sich mit `sudoedit` ändern. Die Erstinstallation setzt Vollbild,
Produktivmodus, USB-Quelle und Splashscreen. `system.splash_duration_ms`
ist standardmäßig 1500. Ein vorhandenes `assets/logo.png` wird angezeigt.
Ohne Grafik erscheint der Schriftzug „LyricsPi“. Ältere lokale
Konfigurationen bleiben beim Update erhalten. Prüfe die vier
Produktiveinstellungen anschließend bei Bedarf manuell.

## 4. HDMI, Stick und Controller abnehmen

1. Mit verbundenem HDMI-Monitor und Song-Stick neu starten. Prüfen, dass
   ohne Anmeldung erst das Logo oder der Schriftzug und dann der erste
   Song im Vollbild erscheinen. Im Journal müssen Modell, Python-Version,
   SDL-Treiber, Auflösung und Songanzahl nachvollziehbar sein.
2. `findmnt --mountpoint /media/lyricspi/USB -o SOURCE,TARGET,FSTYPE,OPTIONS`
   ausführen. Das Gerät und die Option `ro` prüfen. Songs numerisch
   sortiert und nur aus dem Wurzelverzeichnis erwarten.
3. In einem mehrseitigen Song die Fußtasten prüfen. A blättert zurück,
   B kurz beim Loslassen weiter. C wechselt zum vorherigen und D zum
   nächsten Song. Den Controller im Betrieb ab- und wieder anstecken.
4. Dienst stoppen, Stick abziehen und den Dienst starten. Statt eines
   Absturzes muss der Hinweis auf den fehlenden Stick erscheinen.
   Danach Stick einstecken und den Dienst neu starten.
5. Die logind-Berechtigung lässt sich zunächst ohne Herunterfahren prüfen.

```bash
sudo -u lyricspi busctl --system call org.freedesktop.login1 \
  /org/freedesktop/login1 org.freedesktop.login1.Manager CanPowerOff
```

Erwartet wird `s "yes"`. In einem Wartungsfenster gegebenenfalls laufende
Arbeiten sichern und **B mindestens 15 Sekunden** halten. Die Anzeige darf
vor dem regulären Herunterfahren keinen Seitenwechsel auslösen. Erst nach
dem vollständigen Halt die Stromversorgung trennen. Nach dem nächsten Boot
kann `journalctl -b -1 -u lyricspi.service` den vorherigen Start und
Shutdown zeigen, sofern das Journal frühere Boots speichert. Sendet der
Controller beim Halten nur kurze Tastaturimpulse, ist der Langdruck mit
diesem Gerät nicht verfügbar.
[logind-Methoden und Berechtigungen](https://freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html)

## 5. HDMI- und Eingabediagnose

```bash
sudo journalctl -b -u lyricspi.service -u lyricspi-usb.service
lsblk -o NAME,TRAN,FSTYPE,MOUNTPOINTS
ls -l /dev/dri /dev/input
id lyricspi
grep -H . /sys/class/drm/card*-*/status
sudo fgconsole
```

### `EGL not initialized` unter Raspberry Pi OS Lite

Die Standard-Unit verwendet die auf dem Raspberry Pi 3 mit Raspberry Pi
OS Lite 13 (Trixie) bestätigte EGL-/GLES-Konfiguration.

```ini
[Service]
Environment=SDL_VIDEODRIVER=kmsdrm
Environment=SDL_VIDEO_EGL_DRIVER=libEGL.so.1
Environment=SDL_VIDEO_GL_DRIVER=libGLESv2.so.2
```

Die Werte gelten nur für den LyricsPi-Dienst. Bei einer Neuinstallation
oder beim Aktualisieren mit `sudo bash deploy/install.sh` übernimmt der
Installer die Unit nach `/etc/systemd/system/lyricspi.service`, führt
`systemctl daemon-reload` aus und startet den Dienst neu. Mit
`systemctl cat lyricspi.service` lassen sich die installierte Unit und
eventuelle lokale Drop-ins prüfen.

Die Meldung bei `pygame.display.set_mode()` bedeutet, dass der gewählte
SDL-Treiber den Ausgabemodus nicht öffnen konnte. Eine zuvor erkannte
Auflösung und ein in SDL gelisteter KMSDRM-Treiber bestätigen weder die
EGL-/GBM-Initialisierung noch den Zugriff auf den passenden DRM-Master.
SDL2 initialisiert GBM und EGL beim Erzeugen des KMSDRM-Fensters.
[SDL2-Quellcode für KMSDRM](https://github.com/libsdl-org/SDL/blob/release-2.32.4/src/video/kmsdrm/SDL_kmsdrmvideo.c)

Den korrigierten Installationsstand übernehmen und den effektiven Dienst
anzeigen. Der Installer nimmt die Diagnose automatisch mit auf.

```bash
cd "$HOME/LyricsPi"
sudo bash deploy/install.sh
systemctl cat lyricspi.service
apt-cache policy python3-pygame libsdl2-2.0-0 libsdl2-classic libsdl2-compat \
  libegl1 libegl-mesa0 libgles2 libgbm1 libdrm2 libgl1-mesa-dri
```

Für einen Test mit demselben Dienstkonto, den Gruppen `video`, `render`
und `input` sowie derselben Konsole 7 den normalen Dienst stoppen und einen
temporären Drop-in unter `/run` anlegen.

```bash
sudo systemctl stop lyricspi.service
sudo install -d /run/systemd/system/lyricspi.service.d
sudoedit /run/systemd/system/lyricspi.service.d/98-lyricspi-graphics-diagnostic.conf
```

Inhalt des temporären Drop-ins

```ini
[Service]
Restart=no
Environment=EGL_LOG_LEVEL=debug
ExecStart=
ExecStart=/opt/lyricspi/.venv/bin/python /opt/lyricspi/tools/graphics_diagnostic.py --seconds 10
```

```bash
sudo systemctl daemon-reload
sudo systemctl reset-failed lyricspi.service
sudo systemctl start lyricspi.service
sudo journalctl -b -u lyricspi.service -n 150 --no-pager
```

Das Programm protokolliert SDL-Treiber, Python-/Pygame-Pfad, Paketversionen,
Grafikumgebung und Bibliotheken. Es prüft die aktive VT, die Geräte unter
`/dev/dri` einschließlich `card0` und `renderD128` sowie den DRM-Master
beim kurzzeitigen Öffnen der Karten. Danach versucht es, ein Testbild
anzuzeigen. Dieser Zugriffstest ist eine Momentaufnahme. Maßgeblich für
die Abnahme ist das sichtbare Bild am HDMI-Monitor. `EGL_LOG_LEVEL=debug`
schreibt Mesa-Diagnosen ins Journal. [Mesa-EGL-Dokumentation](https://docs.mesa3d.org/egl.html)

- **Bibliothek fehlt** – Mit `apt-cache policy` Paketquellen und
  Paketversionen prüfen. Der Installer richtet die benötigten Pakete über APT ein.
- **Gerät fehlt oder Zugriff verweigert** – DRM-Connectoren und die effektive
  Dienstkonfiguration prüfen. Die Ausgabe unter dem Dienstkonto zählt.
- **Gerät lässt sich öffnen, DRM-Master fehlt** – Laufende Grafikprozesse
  prüfen, etwa mit `sudo fuser -v /dev/dri/card*`, falls `fuser` verfügbar ist.
  Das Erzwingen eines Starts ohne DRM-Master ermöglicht keine direkte Ausgabe.
  [SDL2-Dokumentation zum DRM-Master](https://wiki.libsdl.org/SDL2/SDL_HINT_KMSDRM_REQUIRE_DRM_MASTER)
- **HDMI liegt auf einer anderen Karte** – In der temporären `ExecStart`-Zeile
  `--card N` ergänzen und den Test wiederholen. `N` ist die Nummer der
  Karte mit dem tatsächlich verbundenen HDMI-Connector. Eine dauerhafte
  Kartenauswahl erst übernehmen, wenn genau dieser Test ein HDMI-Bild zeigt.

Nach dem Test nur diesen temporären Drop-in entfernen und wieder zur
normalen Anwendung wechseln.

```bash
sudo systemctl stop lyricspi.service
sudo rm /run/systemd/system/lyricspi.service.d/98-lyricspi-graphics-diagnostic.conf
sudo systemctl daemon-reload
sudo systemctl reset-failed lyricspi.service
sudo systemctl start lyricspi.service
```

### KMS-Kartenauswahl und schlanke Alternative

Bei fehlender Anzeige zuerst HDMI-Eingang, Kabel und
`dtoverlay=vc4-kms-v3d` in `/boot/firmware/config.txt` prüfen. Aufschluss
geben die DRM-Connectoren mit Status `connected` und deren Datei `modes`.
Für den Pi 2 und den Pi 3 gilt derselbe DRM/KMS-Pfad. Maßgeblich sind der
tatsächlich verbundene Connector und seine Auflösung.
Wenn SDL die falsche DRM-Karte verwendet, kann über
`sudo systemctl edit lyricspi.service` eine Einstellung auf Basis der
ermittelten Kartennummer gesetzt werden. Für den Connector an `card1`
lautet sie beispielsweise wie folgt.

```ini
[Service]
Environment=SDL_KMSDRM_DEVICE_INDEX=1
```

Anschließend `sudo systemctl restart lyricspi.service` ausführen. Falls
der Monitor keine verwertbare EDID liefert, kann ein vom Monitor
unterstützter Modus als `video=HDMI-A-1:1280x720@60` in der einzigen Zeile
von `/boot/firmware/cmdline.txt` erprobt werden. Die passende Auflösung
und den Connector aus der Diagnose übernehmen. Die Bootdatei vorher
sichern. Bei Ausblenden am Textterminal kann dort auch `consoleblank=0`
gesetzt werden. Eine automatische Abschaltung im Monitor-Menü muss bei
Bedarf am Monitor deaktiviert werden.
[Raspberry-Pi-KMS-Diagnose](https://pip.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-004341-WP/Troubleshooting-KMS-HDMI-output.pdf) · [SDL-Kartenauswahl](https://wiki.libsdl.org/SDL2/SDL_HINT_KMSDRM_DEVICE_INDEX)

Wenn KMS auf Kernel-Ebene funktioniert, SDL aber kein KMS-Fenster
erzeugen kann, ist ein einzelner Xorg-Server mit `xinit` ein
separater Testpfad. An einer lokalen Textkonsole als Wartungsbenutzer
anmelden, den Dienst stoppen und Xorg nur bei Bedarf installieren. Erst
ein sichtbares Testbild auf dem Ziel-Pi qualifiziert diesen Backend
für eine spätere Umstellung. Der Produktionsdienst verwendet KMSDRM.

```bash
sudo systemctl stop lyricspi.service
sudo apt-get install --no-install-recommends xserver-xorg xinit xserver-xorg-input-libinput
startx /opt/lyricspi/.venv/bin/python /opt/lyricspi/tools/graphics_diagnostic.py \
  --driver x11 --seconds 10 -- :0
cp /opt/lyricspi/config/config.example.json "$HOME/lyricspi-x11.json"
# In der Kopie display.fullscreen auf true setzen.
cd /opt/lyricspi
SDL_VIDEODRIVER=x11 startx /opt/lyricspi/.venv/bin/python \
  -m lyricspi.main --config "$HOME/lyricspi-x11.json" -- :0
```

Diese Diagnose verwendet die Demo-Songs und den Entwicklungsmodus mit
Escape zum Beenden. Der Autostart und Poweroff werden mit dem regulären
Dienst geprüft.

Bei einem Abbruch des Installers zuerst die ausgegebenen Werte für Modell,
Kernel, `armhf`, 32-Bit-Userspace und Debian-Codename prüfen. Bei
Paketfehlern zeigt `apt-cache policy python3 python3-pygame libsdl2-2.0-0 python3-setuptools`
die verfügbaren Versionen. Verwende die Paketquellen des installierten
Images. Bei einer fehlgeschlagenen SDL-Prüfung zeigt der Installer die
angebotenen Videotreiber. Für Fehler erst nach Dienststart das Journal und
die DRM-Connector-Diagnose oben verwenden.

## 6. Aktualisieren oder zurückbauen

Ein Update außerhalb eines Auftritts aus dem separaten Checkout starten.
Der Installer sichert eine von LyricsPi erzeugte frühere UUID-Mount-Unit
und ersetzt sie durch den USB-Hilfsdienst. Nach dem automatischen Neustart
HDMI, Eingabe und USB erneut prüfen.

```bash
cd "$HOME/LyricsPi"
git pull --ff-only
sudo bash deploy/install.sh
sudo systemctl status lyricspi.service
```

Zum Rückbau zuerst stoppen und deaktivieren. Die Befehle entfernen die
installierten Units und die Polkit-Regel. Anwendung und Konfiguration
werden zur Aufbewahrung umbenannt. Eventuell angelegte eigene Service-
Overrides separat mit `systemctl cat lyricspi.service` prüfen.

```bash
sudo systemctl disable --now lyricspi.service
sudo systemctl stop lyricspi-usb.service
sudo rm /etc/systemd/system/lyricspi.service \
  /etc/systemd/system/lyricspi-usb.service \
  /etc/polkit-1/rules.d/49-lyricspi-poweroff.rules
sudo systemctl daemon-reload
sudo mv /opt/lyricspi "/opt/lyricspi.uninstalled.$(date +%Y%m%d-%H%M%S)"
sudo userdel lyricspi
sudo rmdir /media/lyricspi/USB /media/lyricspi
sudo chvt 1
```

Der Installer bearbeitet die SSH-Konfiguration und Bootdateien nicht.
Manuelle HDMI- oder Overlay-Änderungen können anhand der vorherigen
Sicherungen zurückgebaut werden. Gemeinsam genutzte APT-Pakete bleiben
installiert.

## 7. Optionaler Schutz der MicroSD-Karte

Nach vollständig geprüfter Installation kann in `sudo raspi-config` unter
**Performance Options → Overlay File System** ein schreibgeschütztes
Root-Dateisystem mit RAM-Overlay aktiviert werden. Das reduziert
Schreibzugriffe auf die MicroSD. Schreibzugriffe im Overlay belegen RAM.
Konfigurationsänderungen, Git-Updates und persistente Journaldaten gehen
bei Neustart verloren, solange sie nur im Overlay liegen. Für Updates
und dauerhafte Änderungen das Overlay zuerst deaktivieren und neu starten,
die Änderungen durchführen und testen und erst danach wieder aktivieren.
Der zusätzliche Schreibschutz für die Bootpartition ist separat wählbar.
[Raspberry-Pi-Overlay-Dokumentation](https://www.raspberrypi.com/documentation/computers/configuration.html)

## License

LyricsPi is licensed under the MIT License.
See [LICENSE](LICENSE) for details.
