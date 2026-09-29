# Protokollnachweise

## Herkunft

Untersucht am 29.09.2026:

- Hersteller-Downloadseite: <https://downloadapp.qu-in.life/Pill-Calendar/>
- Vom Hersteller verlinkte Android-App:
  <https://play.google.com/store/apps/details?id=com.quin.pillcalendar>
- Statisch analysiertes Paket: PillCalendar **3.10.0**, Android-Versioncode **125**.
- APK SHA-256:
  `0fdf3a5b76d97dede776d2c28806b8b78e1090a00dc8103b131479fb92488e09`
- Bezugsseite des archivierten Pakets:
  <https://apkpure.net/pillcalendar/com.quin.pillcalendar/download/3.10.0>

Das Paket wurde nicht ausgeführt. Die folgende Beschreibung ist eine eigene
Zusammenfassung der relevanten Codepfade, kein veröffentlichtes Hersteller-SDK.
Die Hashprüfung identifiziert den analysierten Download; sie ist keine unabhängige
Prüfung der Hersteller-Signatur. Eine spätere direkte BLE-Aufzeichnung für Firmware/Akku liegt vor (siehe unten).

## BLE über ESPHome-Proxy

Der BLE-Pfad verwendet `bluetooth.async_ble_device_from_address(...,
connectable=True)` und `bleak_retry_connector.establish_connection`. Der
BLEDevice stammt aus HA und kann damit zu einem ESPHome-Proxy gehören. Es
wird kein eigener Scanner gestartet und kein lokaler Adapter vorausgesetzt.

Die vom Benutzer bereitgestellte Gerätediagnose bestätigt zwei Dienste:
GAP `1800` mit `2a00` sowie Herstellerdienst `ff00`. Darin liegen `ff01` (read),
`ff02` (write, write-without-response) und `ff03` (notify, CCCD `2902`).
Die anonymisierte Liste ist als `tests/fixtures/a1310_gatt.json` abgelegt.

Version 0.1.1 abonniert `ff03` und sendet über `ff02` ausschließlich
`23 47 06 00` (Firmware) sowie nach passender Antwort `23 47 08 00` (Akku).
Für das beobachtete Profil wird Write-with-response verwendet. Eine GATT-
Schreibbestätigung zählt nicht als Geräteantwort; erforderlich sind passende
Notifications im unten beschriebenen Format. Bei fehlender Firmwareantwort
wird keine weitere Anfrage gesendet. Warteschlange und Antwortzeit sind begrenzt.

Am 29.09.2026 wurde die direkte BLE-Abfrage auf dem Mac am echten A1310
bestätigt. Auf `FF03` kamen zunächst `01 01` und `02 b6 00`: zusätzliche
Transportnachrichten, die nicht in den `&G`-Antwortparser gehören. Die gleichen
Nachrichten sind auch in der [Phomemo-Implementierung desselben Herstellers](https://github.com/jeffrafter/phomemo/blob/main/README.md)
beobachtet. Ihre Behandlung als Transportmeldungen wird durch die anschließend
korrekt gelesenen Geräteantworten gestützt; die genaue Bedeutung des zweiten
Pakets ist nicht unabhängig bestätigt (vermutlich Größeninformation).

Nach Trennung dieser Meldungen wurden folgende Antworten empfangen:

| Anfrage | Tatsächliche Antwort | Auswertung |
| --- | --- | --- |
| `23 47 06 00` | `26 47 06 02 00 00` | Firmware 2.0.0 |
| `23 47 08 00` | `26 47 08 01 9c 5f` | Akku 95 % (drittes Nutzdatenbyte) |

Die anonymisierte Aufzeichnung liegt in `tests/fixtures/a1310_ble_capture.json`.
Sie wird als Regressionstest abgespielt, inklusive Transportmeldungen.
Nur eigenständige Transportmeldungen **zwischen** Anwendungsframes werden
übersprungen, nicht identische Bytes innerhalb fragmentierter Firmwarewerte.

Die Statusabfragen sind auf diesem Gerät lokal bestätigt. Anschließend hat der
Benutzer auch korrekte Firmware und angezeigten Akku in HA über den ESPHome-Proxy
bestätigt. Reguläres Polling sendet weiterhin nur Statusabfragen. Ab 0.2.0 kann
die explizite Aktion `set_schedule` zusätzlich Uhrzeit und Alarmplan schreiben.
Diagnosen enthalten Anzahl/Byteanzahl und Anzahl der Transportmeldungen,
Abfragebytes, validierte Werte und Fehlercodes. `ff01` wird nicht interpretiert.

Referenzen: [ESPHome Proxy](https://esphome.io/components/bluetooth_proxy/),
[Bleak API](https://bleak.readthedocs.io/en/latest/api/client.html).

## Optionaler SPP-Transport

`PillBoxName.BOX_NAME_A1310` enthält `A1310`. Der Gerätemanager `e8.c`
scannt BLE-Namen und filtert auf die Modellnamen. `PillBox.createConnector`
erzeugt `g8.c`; `f8.b.run` verbindet über
`createInsecureRfcommSocketToServiceRecord` mit der UUID
`00001101-0000-1000-8000-00805f9b34fb` (Serial Port Profile).
`g8.c$b` schreibt die Befehlsbytes unverändert in den Socket.

In Home Assistant wird dafür ein kurzlebiges BlueZ-Clientprofil registriert.
`Device1.ConnectProfile` führt die Verbindung aus; `Profile1.NewConnection`
liefert den verbundenen Dateideskriptor. So wird kein RFCOMM-Kanal geraten.
Alle Sitzungen dieser Integration sind serialisiert, da BlueZ SPP als ein
gemeinsames Profil verwaltet. Ein fremder SPP-Client kann einen Profilkonflikt
verursachen. Es wird kein fremdes Profil entfernt.

Referenzen:

- [BlueZ Profile API](https://bluez.readthedocs.io/en/latest/profile-api/)
- [BlueZ Device API](https://bluez.readthedocs.io/en/latest/device-api/)
- [Home Assistant Bluetooth APIs](https://developers.home-assistant.io/docs/core/bluetooth/api/)

## Implementierte Befehle

Quelle: `com.quin.bluetoothlib.device.A1310Box` und die Konstanten / der Parser
in `e8.f`. Hexadezimale Darstellung; Antwortlängen ohne den dreibytigen Header.

| Zweck | Anfrage | Antwortheader | Nutzdaten |
| --- | --- | --- | --- |
| Seriennummer | `23 47 04 00` | `26 47 04` | 15 Bytes Text |
| Firmware | `23 47 06 00` | `26 47 06` | 3 Versionsbytes |
| Akku | `23 47 08 00` | `26 47 08` | 3 Bytes, Prozentwert im dritten Byte |
| Lautstärke lesen | `23 47 0a 00` | `26 47 0a` | 1 Byte, Bereich 0–3 |
| Aktuellen Ton lesen | `23 47 0d 00` | `26 47 0d` | 1 Byte, Bereich 0–3 |
| Lautstärke setzen | `23 53 0d VV` | Rücklesen mit `G 0a` | `VV` = 0–3 |
| Ton setzen | `23 53 0f TT` | `26 53 0f`, danach Rücklesen mit `G 0d` | `TT` = 0–3 |

Die App übersetzt ihre Lautstärke-UI-Werte 1–4 in Wire-Werte 0–3. Hier werden
bewusst die Wire-Werte angezeigt; ob Stufe 0 stumm bedeutet, ist nicht bestätigt.
Ton 0/1/2 entspricht A/B/C, Ton 3 dem bereits gespeicherten eigenen Ton.

Die App wartet 50 ms vor jedem Senden. Die Integration übernimmt diesen Abstand.
Serial- und Firmwareabfrage erfolgen vor den anderen Abfragen. Akkuwerte außerhalb
0–100 sowie Lautstärke/Ton außerhalb 0–3 führen zu einem Fehler.

Bekannte spontane Lade-/Batterieereignisse werden beim Lesen konsumiert, aber
nicht als dauerhafter Zustand dargestellt: es gibt bisher keine gesicherte
Abfrage für einen vollständigen aktuellen Ladestatus.

## Alarmprogrammierung ab 0.2.0

Zusätzliche statische Nachweise aus derselben APK:

- `g9.c.c`: vor dem Alarmtransfer `syncBoxTime(true, true)`; für A1310 wird die
  Liste mit `TimeSetupModel.createEmptyTimeSetupModel()` auf sechs Plätze gefüllt.
- `A1310Box.setBoxAlarmClock`: Plätze ab 1, Aufruf `e8.f.d(slot, false, model)`.
- `e8.f.d`: der zweite Parameter `false` erzwingt tägliche Wiederholung `01`.
- `e8.f.a(true)` und `e8.f.b()` liefern Uhrzeitformat und lokale Uhrzeit.

| Zweck | Bytes |
| --- | --- |
| Uhrzeitformat wie im App-Aufruf | `23 53 02 00` |
| Geräteuhr | `23 53 01 YY MM DD hh mm ss` (Jahr minus 2000) |
| Täglicher aktiver Alarm | `23 53 03 SLOT 01 01 YY MM DD hh mm 00` |
| Deaktivierter Alarm | `23 53 03 SLOT 00 01 01 01 01 01 01 00` |

Slots 1–6 werden vollständig geschrieben. Aktive Zeiten sind chronologisch
sortiert. Nicht verwendete Plätze werden entsprechend dem App-Encoder deaktiviert.
Datum/Uhrzeit stammen aus der HA-Zeitzone. Vor jeder Übertragung werden Firmware
und Akku abgefragt, anschließend erfolgen einmalige Schreibvorgänge mit GATT-
Bestätigung und mindestens 50 ms Abstand. Es gibt keine automatischen Retries
von Schreibbefehlen und keinen automatischen Transfer beim Start oder Polling.

**Diese Alarmbefehle sind noch nicht am echten Gerät bestätigt.** Der App-Parser
`e8.f.c` verarbeitet keine Bestätigung zu `&S01`, `&S02` oder `&S03`, und die
A1310-Schnittstelle enthält keine Alarmabfrage. GATT-Schreiberfolg wird daher
als `sent_unverified` angezeigt. Ein Fehler oder Abbruch lässt den tatsächlichen
Geräteplan unklar; der Zustand wird über Neustarts hinweg gespeichert.

## Einnahme und sofortige Ausgabe

Die vollständige `A1310Box`-/`PillBox`-Methodenliste und der Antwortparser liefern
keinen belegten Einnahme-/Entnahmestatus und keinen Sofortausgabebefehl. Die App
enthält dagegen `AppMainApi.settingTakeMedicineType` sowie
`UserTakeMedicineConfigBean.isManualMarking` für ihre Einnahmeverwaltung.
Das beweist nicht, dass die Firmware keine weiteren Befehle kennt; es liefert
aber keine Grundlage für deren Implementierung.

Der Benutzer bestätigt für die iPhone-App: keine Schaltfläche zur Sofortausgabe;
Ausgabe erfolgt am Gerät oder nach Zeitplan. Die geplante Ausgabe wird deshalb
über die Alarmprogrammierung abgedeckt, ohne einen Sofortbefehl zu erfinden.

Die HA-Funktion `record_intake` speichert deshalb ausschließlich manuelle Angaben
lokal und löst ein entsprechend gekennzeichnetes Ereignis aus. Es werden keine
BLE-Ereignisse als Einnahme interpretiert. Für eine sofortige Ausgabe bleibt ein
belegter Gerätebefehl erforderlich. Geplante Ausgabe bleibt ein Geräteablauf,
der durch die Alarmzeiten gesteuert wird, kein von HA beobachteter Erfolg.

## Bewusste Grenzen

- Unbekannte Antwortheader brechen die Sitzung ab. Ohne verlässliche Länge lässt
  sich ein Byte-Strom nicht sicher durch Suche nach einem weiteren Header zerlegen.
- Fingerabdrucklisten, Firmwaredaten und andere variable Nachrichten werden nicht
  angefordert und nicht interpretiert.
- Ausbleibende Schreibbestätigungen führen nicht zu einem automatischen erneuten
  Schreiben. Eine Änderung kann am Gerät schon angekommen sein.
- Die Zuordnung zum A1310 stammt aus dem BLE-Namen bzw. der manuellen Auswahl.
  Das Protokoll besitzt hier keine ausgelesene Modellkennung.
- Abweichende Firmware und Schlafverhalten sind nur begrenzt untersucht.
- Der Alarmplan ist aus dem App-Code abgeleitet; Gerätewirkung und Verhalten
  nach Zeitumstellungen sind noch zu prüfen. Wochentags- und Einmalalarme werden
  nicht angeboten, da A1310Box im untersuchten Pfad tägliche Wiederholung erzwingt.

Die meisten Tests verwenden synthetische, aus der App abgeleitete Bytefolgen.
Der BLE-Regressionstest verwendet zusätzlich die oben dokumentierte echte
Aufzeichnung. Für SPP liegen weiterhin keine Hardwareaufzeichnungen vor.
