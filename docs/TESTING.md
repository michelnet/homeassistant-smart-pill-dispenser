# Tests und Geräteprüfung

## Automatische Prüfungen

Tests laufen mit Home Assistant 2026.9.4 und Python 3.14. Die echte HA-API wird
verwendet; Hardware, Proxy-Verbindungsaufbau und Funkantworten werden simuliert.
BLE-Tests prüfen insbesondere:

- Auswahl eines connectable BLEDevice aus Home Assistants Bluetooth-Routing.
- Weitergabe dieses Proxy-Geräts an Bleak statt Aufbau einer lokalen Verbindung.
- GATT-Erfassung auch ohne standardisierte Akku-/Firmwaredienste.
- Im regulären Polling ausschließlich Firmware-/Akkuanfragen auf dem FF00-Profil;
  keine Einstellungsbefehle oder Zugriffe auf fremde Schreib-Characteristics.
- Wiedergabe realer A1310-Antworten inklusive Transportnachrichten 0101/02b600.
- Fehler bei passiven/unerreichbaren Proxys und Freigabe des Verbindungsplatzes
  bei Fehlern und Abbruch.

SPP-Tests nutzen lokale Socketpaare für die Verarbeitung fragmentierter und
zusammengefasster Antworten und das Rücklesen von Einstellungsänderungen.
HA-Tests prüfen Einrichtung, Dubletten, Fehlerzustände, Wiederherstellung und
Diagnosen.

Ab 0.2.0 prüfen zusätzliche Tests die vollständige Sechs-Platz-Kodierung,
Deaktivierung ungenutzter Plätze, Eingabeprüfung vor Verbindungsaufbau,
Übertragung über HA-Proxy-Routing, Abbruch ohne Wiederholung und Freigabe des
Proxy-Platzes. HA-Tests prüfen persistente Fehlerzustände, manuelle Einnahmen,
Aktionen und tatsächliche Entitätsregistrierung einschließlich Reload.

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

## Direkter Gerätetest auf dem Mac

Mit `scripts/ble_probe.py --query --capture` wurden Firmware **2.0.0** und
Akku **95 %** empfangen. Die Transportmeldungen wurden von den eigentlichen
Geräteantworten getrennt. Die nachgestellten Tests enthalten diese Aufzeichnung.

Der Benutzer hat anschließend korrekte Firmware und angezeigten Akku auch in
Home Assistant über den ESPHome-Proxy bestätigt.

Ein einzelner Alarm aus der Alarmprogrammierung ab 0.2.0 wurde am 29.09.2026
über lokales BLE bestätigt: vollständiger Plan mit ausschließlich 20:53 Uhr,
Übertragung um 20:51:10–20:51:11 Europe/Zurich, Firmware 2.0.0, Akku 88 %.
Der Benutzer bestätigte anschließend, dass der Alarm funktioniert.

**Noch offen:** mehrere Alarmzeiten, Deaktivierung bestehender Alarme,
tägliche Wiederholung, Alarmtransfer über HA/Proxy und andere Firmwarevarianten.
Automatische Einnahmeerkennung und sofortige Ausgabe sind nicht implementiert,
da dafür kein Protokollnachweis vorliegt.

## Neue Alarmfunktion am Gerät prüfen

Die automatischen Entwicklungstests ändern keine realen Alarmzeiten. Für die Prüfung
einen **leeren Spender** verwenden: Ein Alarm kann die Ausgabe auslösen.

1. Bestehende Zeiten notieren; `set_schedule` ersetzt den kompletten Geräteplan.
2. Eine künftige tägliche Zeit über die HA-Aktion übertragen. Der Status muss
   „Gesendet, am Gerät unbestätigt“ lauten, niemals „vom Gerät bestätigt“.
3. Alarm und Gerätebewegung zum vorgesehenen Zeitpunkt direkt beobachten.
4. Mit `times: []` alle Plätze deaktivieren und prüfen, dass alte Alarme entfallen.
5. Den gewünschten vollständigen Plan wiederherstellen.

Ein in PillCalendar angezeigter Plan allein ist keine unabhängige Bestätigung:
Die App führt ihre eigene Planverwaltung. Entscheidend ist das Geräteverhalten.
Der erfolgreiche Einzelalarmtest bestätigt noch nicht das Ausbleiben deaktivierter
Alarme oder die tatsächliche Ausgabe; beides wurde nicht separat protokolliert.

## Untersuchung automatischer Entnahmeereignisse

`scripts/ble_probe.py --query --listen 60 --read-state` untersucht sowohl
Notifications als auch den lesbaren FF01-Wert. Eine echte 60-Sekunden-Messung
mit bestätigter Behälterentnahme ergab nur Transport- und Lademeldungen.
Eine zweite Messung mit FF01-Abfragen ergab 57 leere Leseantworten und nur
Transportmeldungen. Bei einer Wiederholung mit bereits aktivem Alarm bestätigte
der Benutzer die Entnahme und das Ende des Alarms: In 120 Sekunden kamen nur
zwei Transportmeldungen; alle 114 FF01-Leseantworten waren leer. Die Verbindung
blieb bestehen. Details und Aussagegrenzen stehen in `PROTOCOL.md`.

Nach dem Hinweis, dass die Verbindung zuvor zu spät aufgebaut worden war,
folgte eine 300-Sekunden-Aufzeichnung mit ausdrücklich bestätigtem Alarmbeginn
erst nach Verbindungsaufbau. Auch hier wurden nur die zwei Transportmeldungen
empfangen; alle 284 FF01-Leseantworten waren leer. Es gab keine Abbrüche oder
verlorenen Samples. Ein automatischer Entnahmezeitpunkt ist damit weiterhin
nicht durch das beobachtete BLE-Protokoll gestützt.

Die sieben zusätzlichen Werkzeugtests prüfen das Erhalten unbekannter Pakete,
begrenzte Rohdatenmengen, Verbindungsabbruch, Cleanup nach Abbruch sowie
FF01-Lesezugriff, dessen Fehlerpfad und weiterlaufende Abfragen nach der ersten
Minute bei längeren Aufzeichnungen. Das Werkzeug löst keine Ausgabe aus
und interpretiert keine Nachricht als Einnahme.

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
