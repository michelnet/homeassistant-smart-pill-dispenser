# Smart Pill Dispenser für Home Assistant

Experimentelle Custom Integration für **Quin A1310 / Artikel A1310-WHBL-1**,
verwendet mit **PillCalendar**. **ESPHome-Bluetooth-Proxys sind als BLE-Anbindung
implementiert. Ein lokaler Bluetooth-Adapter ist dafür nicht nötig.**

**Stand 0.1.1:** Verbindung und GATT-Dienste wurden durch eine Gerätediagnose
bestätigt. Der Spender bietet `FF00` mit Schreib-Characteristic `FF02` und
Notify-Characteristic `FF03`, aber keine Standard-Akku-/Firmwaredienste.

Die Integration sendet nun gezielt die aus der Android-App abgeleiteten
Firmware- und Akkuabfragen über `FF02` und empfängt Antworten auf `FF03`.
**Firmware- und Akkuabfrage wurden direkt am Gerät über BLE bestätigt: Firmware 2.0.0, Akku 95 %.**
Die erweiterte Statusabfrage über den ESPHome-Proxy muss noch in Home Assistant getestet werden. Alarmpläne und Ausgabe sind nicht implementiert.

## BLE-Funktionen

- Einrichtung, GATT-Erfassung und Verbindung über aktive ESPHome-Proxys.
- Gezielte Firmware-/Akkuabfragen nur beim beobachteten `FF00`-Profil.
- Verarbeitung aufgeteilter Antworten; Werte nur bei passenden Antwortpaketen.
- Fallback auf standardisierte Akku-/Firmwaredienste, falls vorhanden.
- Diagnose mit Abfragebytes, Antwortanzahl, Byteanzahl und Fehlerstatus.
- Aktualisierung alle fünf Minuten sowie manuell per Button.

Die BLE-Anfragen ändern nach dem bekannten App-Protokoll weder Einstellungen
noch Alarmpläne oder Uhrzeit. Lautstärke, Klingelton und Pillenausgabe bleiben
über BLE nicht implementiert. Fremde GATT-Dienste werden nicht beschrieben.

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
aber keine MAC-Adresse, Seriennummer oder Medikamentendaten. Sie hilft bei der Prüfung, ob und wie der Spender auf die Abfragen antwortet.
Die automatische Abfrage läuft alle fünf Minuten. Nach Aufwecken lässt sich
„Aktualisieren“ drücken. Während der Spender schläft oder die App verbunden
ist, kann die Verbindung fehlschlagen.

Wenn der Akku unbekannt bleibt, ist das nicht automatisch ein Verbindungsfehler:
Der Spender stellt möglicherweise nur herstellerspezifische GATT-Dienste bereit.
Der Sensor „BLE-Protokoll“ unterscheidet empfangene Werte, fehlende Antworten
und unerwartete Antwortformate. Nach einem erfolglosen Abfragezyklus bleiben
die betroffenen Werte unbekannt; alte Werte werden nicht als frisch ausgegeben.

## Direkt auf diesem Mac diagnostizieren

Der direkte Test auf dem Mac war erfolgreich. Nach Installation der
Entwicklungsabhängigkeiten kann das Werkzeug den Spender
über das lokale Bluetooth des Computers untersuchen, ohne laufendes Home Assistant:

```sh
.venv/bin/python scripts/ble_probe.py --query --output /tmp/a1310-diagnostics.json
```

Spender aufwecken, in Reichweite stellen, PillCalendar schließen und bei
Verbindungskonflikten die HA-Integration vorübergehend deaktivieren. macOS muss
dem ausführenden Programm Bluetooth-Zugriff erlauben. Ohne `--query` werden
nur Dienste erfasst. Bei mehreren Spendern kann `--address` das Gerät auswählen;
unter macOS ist das eine CoreBluetooth-UUID, keine HA-MAC-Adresse.

Mit `--capture` lassen sich zusätzlich bis zu 16 gekürzte rohe
Benachrichtigungen für die lokale Analyse aufzeichnen. Der normale HA-
Diagnoseexport enthält keine rohen Nutzdaten.

Das Werkzeug verwendet den lokalen Adapter. Es greift nicht eigenständig auf
den ESPHome-Proxy zu. Wenn lokal kein Bluetooth verfügbar ist, bleibt der
Diagnoseexport über Home Assistant der nutzbare Weg.

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

Tests nutzen simulierte Antworten und einen Regressionstest mit tatsächlich
aufgezeichneten Firmware-/Akkuantworten. Eine gesamte HA-/Proxy-Prüfung bleibt
zusätzlich nötig.
Die APK und dekompilierter Herstellercode sind nicht Teil des Repositorys.
