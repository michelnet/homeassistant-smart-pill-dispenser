# Smart Pill Dispenser für Home Assistant

Experimentelle Custom Integration für **Quin A1310 / Artikel A1310-WHBL-1**,
verwendet mit **PillCalendar**. **ESPHome-Bluetooth-Proxys sind als BLE-Anbindung
implementiert. Ein lokaler Bluetooth-Adapter ist dafür nicht nötig.**

**Stand 0.1.0: Die BLE-Verbindung und Geräteanalyse sind implementiert; die
herstellerspezifische Steuerung über BLE ist noch offen.** Es liegt noch kein
Test an einem echten A1310-WHBL-1 vor. Die Integration ist deshalb derzeit eine
Grundlage zur Geräteprüfung, keine vollständige Steuerung des Pillenspenders.

## Was über deinen BLE-Proxy funktioniert

- Einrichtung über die Home-Assistant-Oberfläche; Erkennung von Namen `A1310*`.
- Verbindung über Home Assistants Bluetooth-Routing und aktive ESPHome-Proxys.
- Erfassung der angebotenen GATT-Dienste, Characteristics und Eigenschaften.
- Akku/Firmware **nur falls** der Spender die entsprechenden standardisierten
  Bluetooth-Dienste bereitstellt. Andernfalls bleiben diese Werte unbekannt.
- Sensoren für Anzahl der BLE-Dienste, Protokollstatus und letzte Aktualisierung.
- Manuelle Aktualisierung und Diagnoseexport für die weitere Protokollanalyse.

Über BLE werden aktuell keine herstellerspezifischen Schreibbefehle gesendet.
Alarmpläne, Lautstärke, Klingeltöne, Pillenausgabe und Einnahmehistorie sind über
BLE noch nicht verfügbar. Eine erfolgreiche GATT-Verbindung bestätigt nicht,
welche dieser Funktionen sich später umsetzen lassen.

## Einrichtung mit ESPHome-Proxy und iPhone

Voraussetzung: **Home Assistant 2026.9 oder neuer** und ein bereits über die
ESPHome-Integration eingebundener Bluetooth-Proxy mit aktiven Verbindungen.

Die relevante ESPHome-Konfiguration lautet:

```yaml
esp32_ble_tracker:

bluetooth_proxy:
  active: true
```

Das ist ein Ausschnitt zur Ergänzung der vorhandenen ESPHome-Konfiguration,
keine vollständige Firmware. Die native ESPHome-API muss bereits eingerichtet
sein. Siehe [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy/).
Der Proxy muss in Reichweite des Spenders einen freien Verbindungsplatz haben.

1. `custom_components/smart_pill_dispenser` nach
   `/config/custom_components/smart_pill_dispenser` kopieren.
2. Home Assistant neu starten.
3. PillCalendar auf dem iPhone vollständig schließen und den Spender aufwecken.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Smart Pill
   Dispenser** öffnen oder den entdeckten A1310 auswählen.
5. Bluetooth-Adresse aus der HA-Geräteerkennung verwenden und **BLE / ESPHome
   proxy** auswählen. Es wird kein `hci0`-Adapter benötigt.
6. Nach erfolgreicher Einrichtung **Diagnose herunterladen** beim
   Integrationseintrag auswählen.

Die Diagnose enthält die Service-/Characteristic-UUIDs und Eigenschaften,
aber keine MAC-Adresse, Seriennummer oder Medikamentendaten. **Diese Datei ist
der nächste benötigte Schritt, um das BLE-Profil deines Geräts zu untersuchen.**
Die automatische Abfrage läuft alle fünf Minuten. Nach Aufwecken lässt sich
„Aktualisieren“ drücken. Während der Spender schläft oder die App verbunden
ist, kann die Verbindung fehlschlagen.

Wenn der Akku unbekannt bleibt, ist das nicht automatisch ein Verbindungsfehler:
Der Spender stellt möglicherweise nur herstellerspezifische GATT-Dienste bereit.
Der Sensor „BLE-Protokoll“ zeigt bis zur Implementierung eines bestätigten
Geräteprofils „Geräteprofil noch zu bestätigen“.

## HACS

Nach Veröffentlichung dieses Repository-Stands kann
`https://github.com/michelnet/homeassistant-smart-pill-dispenser` als
benutzerdefiniertes Repository vom Typ **Integration** hinzugefügt werden.
Das Projekt ist nicht in der offiziellen HACS-Liste enthalten. Die Dateien sind
hier lokal erstellt; damit ist noch keine Veröffentlichung erfolgt.

## Optionaler Bluetooth-Classic-Pfad

Zusätzlich existiert ein experimenteller **lokaler SPP/RFCOMM-Pfad**. Dafür wird
unter Linux ein lokaler Classic-Adapter benötigt; dieser Pfad funktioniert nicht
über einen ESPHome-Proxy. Er ist für deine Proxy-Einrichtung nicht erforderlich.

Dieser Code basiert auf statischer Analyse der Android-App PillCalendar 3.10.0.
Er implementiert Akku, Firmware, Lautstärke und Klingelton. Die beiden
Einstellungs-Entitäten sind standardmäßig deaktiviert. Änderungen werden
zurückgelesen, nicht optimistisch als erfolgreich angezeigt.

Auch dieser Pfad ist noch nicht am Gerät bestätigt. Die SPP-Befehle liefern
**keinen Nachweis**, dass dieselben Bytes über BLE funktionieren. Deshalb werden
keine UART-UUIDs geraten und keine SPP-Befehle an beliebige GATT-Characteristics
gesendet. Die Integration benötigt kein App-Konto und keine Hersteller-Cloud.

## Dokumentation und Entwicklung

- [Protokollnachweise und offene Fragen](docs/PROTOCOL.md)
- [Tests und Geräteprüfung](docs/TESTING.md)
- [Hersteller-Downloadseite](https://downloadapp.qu-in.life/Pill-Calendar/)

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
```

Tests nutzen simulierte Geräteantworten und ersetzen keine Prüfung am Spender.
Die APK und dekompilierter Herstellercode sind nicht Teil des Repositorys.
