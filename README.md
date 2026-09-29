# Smart Pill Dispenser für Home Assistant

Experimentelle Custom Integration für **Quin A1310 / Artikel A1310-WHBL-1**,
verwendet mit der Hersteller-App **PillCalendar**.

**Stand 0.1.0: aus der Android-App abgeleitet, noch nicht an einem echten
A1310-WHBL-1 getestet.** Das ist eine erste Implementierung zur Geräteprüfung,
keine bestätigte vollständige Unterstützung des Spenders.

## Funktionen

| Funktion | Stand |
| --- | --- |
| Einrichtung über die Home-Assistant-Oberfläche | Implementiert, Verbindung wird geprüft |
| Erkennung von Bluetooth-Namen `A1310*` | Aus dem Namensfilter der App abgeleitet |
| Akkustand, Firmware, Zeitpunkt der letzten Aktualisierung | Implementiert |
| Lautstärke 0–3, Klingelton A/B/C/eigener Ton | Implementiert, mit Rücklesen; Entitäten standardmäßig deaktiviert |
| Manuell aktualisieren | Implementiert |
| Alarmpläne, Medikamentenliste, Entnahme-/Einnahmehistorie | Noch nicht unterstützt |
| Pillenausgabe, Fingerabdrücke, Firmware-Update | Nicht implementiert |

Die Integration setzt beim Verbinden weder Uhrzeit noch Alarmpläne. Sie benötigt
kein App-Konto und verwendet keine Hersteller-Cloud. Eine Geräteantwort belegt
keine Medikamenteneinnahme.

## Voraussetzungen

- Home Assistant **2026.9 oder neuer**, unter Linux (HA OS oder Container).
- Ein **lokaler Bluetooth-Adapter mit Bluetooth Classic / BR/EDR** und BlueZ.
- Zugriff von Home Assistant auf den System-D-Bus. Bei Home Assistant Container
  muss der D-Bus-Socket eingebunden sein; siehe die
  [offizielle Bluetooth-Anleitung](https://www.home-assistant.io/integrations/bluetooth/).
- Der Spender muss wach und in Reichweite sein; PillCalendar auf dem iPhone
  während der Prüfung vollständig schließen.

**Ein ESPHome-Bluetooth-Proxy alleine reicht für diese Implementierung nicht.**
Die untersuchte Android-App entdeckt Geräte per BLE, überträgt Daten aber über
Bluetooth Classic SPP/RFCOMM. Der iPhone-Transport wurde nicht untersucht.
Die bloße Sichtbarkeit in Home Assistants BLE-Geräteliste bestätigt deshalb
noch keine nutzbare SPP-Verbindung.

## Installation

### Manuell

1. Den Ordner `custom_components/smart_pill_dispenser` nach
   `/config/custom_components/smart_pill_dispenser` kopieren.
2. Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Smart Pill
   Dispenser** öffnen oder den entdeckten A1310 auswählen.
4. Die Bluetooth-MAC-Adresse des Spenders und den lokalen Adapter (normalerweise
   `hci0`) eintragen. Die MAC-Adresse findet sich in der Bluetooth-Erkennung von
   Home Assistant; eine iOS-CoreBluetooth-UUID ist keine MAC-Adresse.
5. Spender aufwecken und Einrichtung abschließen. Der Eintrag wird erst erzeugt,
   wenn alle vorgesehenen Statusantworten erfolgreich gelesen wurden.

### HACS

Nach Veröffentlichung dieses Repository-Stands kann
`https://github.com/michelnet/homeassistant-smart-pill-dispenser` als
benutzerdefiniertes Repository vom Typ **Integration** hinzugefügt werden.
Das Projekt ist nicht in der offiziellen HACS-Liste enthalten.

## Erster Test mit iPhone

1. Bestehende Einstellungen weiterhin in PillCalendar verwalten.
2. PillCalendar vollständig schließen, Spender aufwecken und Integration hinzufügen.
3. Akku und Firmware mit der App vergleichen. Zum erneuten Öffnen der App die
   Home-Assistant-Integration bei Bedarf vorübergehend deaktivieren.
4. Bei Verbindungsproblemen: Gerät erneut aufwecken und „Aktualisieren“ drücken.
   Nach fünf Minuten erfolgt auch eine automatische Abfrage. Im Schlafzustand
   können die Sensoren als nicht verfügbar erscheinen.
5. Diagnose über **Geräte & Dienste → Smart Pill Dispenser → Diagnose
   herunterladen** abrufen. Sie enthält keine MAC-Adresse, Seriennummer oder
   Medikamentendaten.

Lautstärke und Klingelton erst nach erfolgreichem Lesetest über die jeweiligen
deaktivierten Entitäten einschalten. Änderungen werden nur nach passendem
Rücklesen als erfolgreich übernommen. Bei einem Fehler kann der Schreibbefehl
bereits angekommen sein: zuerst aktualisieren, dann den Zustand prüfen.

Falls keine Verbindung entsteht, siehe [Geräteprüfung](docs/TESTING.md). Benötigt
werden dann der sichtbare Bluetooth-Name, der Adaptertyp und die konkrete
Fehlermeldung. Eine Android-Aufzeichnung ist nicht Voraussetzung.

## Technische Grundlage und Grenzen

Die Befehle stammen aus der statischen Analyse von PillCalendar Android
3.10.0, Paket `com.quin.pillcalendar`. Es wurden keine Befehle anhand üblicher
BLE-UUIDs geraten. BlueZ ermittelt den RFCOMM-Kanal über das SPP-Profil.

- [Protokoll, Quellen und offene Fragen](docs/PROTOCOL.md)
- [Tests und Geräteprüfung](docs/TESTING.md)
- [Hersteller-Downloadseite](https://downloadapp.qu-in.life/Pill-Calendar/)

Die automatisierten Tests verwenden simulierte Antworten. Insbesondere die
SPP-Erreichbarkeit, Antwortlängen und Firmwarevarianten müssen am tatsächlichen
Gerät bestätigt werden. Die Integration übernimmt derzeit keine Überwachung
der Medikamentenausgabe.

## Entwicklung

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
```

Die APK und dekompilierter Herstellercode sind nicht Teil des Repositorys.
