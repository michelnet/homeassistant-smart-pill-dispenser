# Tests und Geräteprüfung

## Automatische Prüfungen

Tests laufen mit Home Assistant 2026.9.4 und Python 3.14. Die echte HA-API wird
verwendet; Hardware, Proxy-Verbindungsaufbau und Funkantworten werden simuliert.
BLE-Tests prüfen insbesondere:

- Auswahl eines connectable BLEDevice aus Home Assistants Bluetooth-Routing.
- Weitergabe dieses Proxy-Geräts an Bleak statt Aufbau einer lokalen Verbindung.
- GATT-Erfassung auch ohne standardisierte Akku-/Firmwaredienste.
- Ausschließlich Lesen erlaubter Standard-Characteristics, keine Vendor-Writes.
- Fehler bei passiven/unerreichbaren Proxys und Freigabe des Verbindungsplatzes
  bei Fehlern und Abbruch.

SPP-Tests nutzen lokale Socketpaare für die Verarbeitung fragmentierter und
zusammengefasster Antworten und das Rücklesen von Einstellungsänderungen.
HA-Tests prüfen Einrichtung, Dubletten, Fehlerzustände, Wiederherstellung und
Diagnosen.

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
```

## Nächster Schritt am echten BLE-Gerät

1. Aktiven ESPHome-Bluetooth-Proxy in HA einbinden, Spender daneben aufwecken.
2. PillCalendar auf dem iPhone vollständig schließen.
3. Integration mit Transport **BLE / ESPHome proxy** einrichten.
4. Bei Erfolg: die Integrationseintrags-Diagnose herunterladen und zur Analyse
   bereitstellen. Sie listet tatsächlich entdeckte UUIDs und Eigenschaften auf.
5. Eventuelle Standard-Akku-/Firmwarewerte mit PillCalendar vergleichen.
6. Schlafenlassen, Aufwecken und „Aktualisieren“ ausprobieren.

**Offen:** Proprietäre BLE-Service-/Characteristic-Zuordnung, Framing, mögliche
Initialisierung/Authentifizierung und die Bestätigung von Antworten. Eine
GATT-Liste allein kann diese Fragen noch nicht vollständig klären. Falls nötig,
folgt danach ein gezielter Abgleich mit der iPhone-Kommunikation oder zusätzlichen
Herstellerinformationen.

## BLE-Fehler

- **Kein aktiver Proxy erreicht das Gerät:** `bluetooth_proxy.active: true`,
  Erreichbarkeit, ESPHome-API und freien Verbindungsplatz prüfen. Die Adresse
  muss die MAC-Adresse aus HA sein, keine iOS-CoreBluetooth-UUID.
- **Verbindung fehlgeschlagen:** Gerät aufwecken und die iPhone-App schließen;
  Proxy in die Nähe stellen. Eine sichtbare BLE-Werbung allein garantiert noch
  keine funktionierende GATT-Verbindung.
- **Akku/Firmware unbekannt, BLE-Dienste vorhanden:** Das Gerät bietet womöglich
  nur proprietäre Dienste. Diagnose exportieren; es werden keine Werte erfunden.
- **Gerät schläft:** Vor der manuellen Aktualisierung am Gerät aufwecken.

## Optionaler lokaler SPP-Pfad

Nur für Linux mit lokalem Classic-Adapter. Bei `UnknownObject` ist die Adresse
auf dem gewählten BlueZ-Adapter noch nicht bekannt oder der Adaptername ist
falsch. `NotAvailable`/`Failed` kann auf Schlafzustand, eine andere Verbindung
oder fehlendes SPP hinweisen. `AlreadyExists` bei RegisterProfile kann einen
Konflikt mit einem anderen SPP-Client bedeuten; fremde Profile werden nicht
entfernt. D-Bus-Zugriff gemäß offizieller HA-Bluetooth-Anleitung prüfen.

Allgemeine HA-Protokolle können Gerätekennungen enthalten; vor öffentlichem
Teilen prüfen. Der integrationseigene Diagnoseexport enthält keine MAC-Adresse
oder Seriennummer.
