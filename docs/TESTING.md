# Test und Inbetriebnahme

## Automatische Prüfungen

Die Tests verwenden Home Assistant 2026.9.4 und Python 3.14. Die Radioverbindung
wird simuliert. Byte-Stream-Tests nutzen echte lokale Socketpaare und prüfen
Fragmentierung, mehrere Nachrichten pro Lesezugriff, Abbruch und Rücklesen nach
Schreibbefehlen. Home-Assistant-Tests prüfen unter anderem Einrichtung,
Dubletten, Fehlerzustände, Wiederherstellung und datensparsame Diagnosen.

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
```

## Was am Gerät noch zu prüfen ist

1. Home-Assistant-Version und lokalen Adaptertyp festhalten.
2. Spender aufwecken; PillCalendar auf dem iPhone vollständig schließen.
3. In Home Assistant prüfen, ob ein Name beginnend mit `A1310` angezeigt wird.
4. Einrichtung mit der zugehörigen MAC-Adresse und `hci0` bzw. dem tatsächlich
   verwendeten lokalen Adapter versuchen.
5. Seriennummern-/Firmware-/Akkuantworten sowie Lautstärke und Ton müssen alle
   dem beschriebenen Format entsprechen. Die Integration erzeugt sonst keinen
   Eintrag und zeigt einen Verbindungsfehler.
6. Nach erfolgreicher Einrichtung Akku/Firmware mit der App vergleichen. Noch
   nicht bestätigen lässt sich allein dadurch die Eignung als Einnahmeüberwachung.
7. Schlafenlassen und erneutes Aufwecken testen: Sensoren sollen bei fehlender
   Antwort nicht verfügbar werden und nach erfolgreicher Abfrage zurückkehren.
8. Erst anschließend die deaktivierten Lautstärke-/Ton-Entitäten aktivieren und
   eine bewusst gewählte Änderung samt Rücklesen vergleichen.

## Verbindungsfehler

- **Nur ESPHome-Proxy vorhanden:** Die aktuelle Implementierung braucht einen
  lokalen Classic-Adapter; ein BLE-Proxy transportiert kein RFCOMM.
- **`UnknownObject` bei ConnectProfile:** Die Geräteadresse ist auf diesem
  lokalen BlueZ-Adapter noch nicht bekannt oder der Adaptername ist falsch.
  Die lokale Bluetooth-Erkennung muss den wachen Spender zuerst sehen.
- **`NotAvailable` / `Failed`:** Gerät schläft, ist anderweitig verbunden oder
  bietet auf dieser Firmware kein nutzbares SPP an. Der Fehler allein beweist
  keine bestimmte Ursache.
- **`AlreadyExists` bei RegisterProfile:** Ein anderer Dienst kann SPP bereits
  registriert haben. Die Integration entfernt keine fremden Profile.
- **Kein System-D-Bus / Berechtigungsfehler:** BlueZ-Zugriff der HA-Installation
  gemäß offizieller Bluetooth-Anleitung prüfen.
- **Protokollfehler:** Antwortformat dieser Firmware weicht möglicherweise von
  der analysierten App ab. Keine Alarm-/Ausgabebefehle ausprobieren.

Für die nächste Untersuchung genügen zunächst HA-Version, Adaptertyp,
Bluetooth-Name, Firmware (falls bekannt) und Fehlermeldung. Mit einem iPhone
können zusätzlich sichtbare GATT-Dienste untersucht werden, falls SPP nicht
funktioniert. Erst anhand der tatsächlichen UUIDs und Eigenschaften wird ein
alternativer BLE-Transport entworfen.

Diagnosen lassen MAC-Adresse und Seriennummer weg. Allgemeine HA-Protokolle
können diese Kennungen trotzdem enthalten; vor öffentlichem Teilen prüfen.
