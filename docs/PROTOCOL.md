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

Die Statusabfragen sind damit auf diesem Gerät lokal bestätigt. Das komplette
HA-/ESPHome-Proxy-Zusammenspiel mit der neuen Abfragelogik ist noch zu prüfen.
Es werden keine Initialisierungs-, Alarm-, Uhrzeit- oder Ausgabebefehle gesendet.
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

## Bewusste Grenzen

- Unbekannte Antwortheader brechen die Sitzung ab. Ohne verlässliche Länge lässt
  sich ein Byte-Strom nicht sicher durch Suche nach einem weiteren Header zerlegen.
- Fingerabdrucklisten, Firmwaredaten und andere variable Nachrichten werden nicht
  angefordert und nicht interpretiert.
- Ausbleibende Schreibbestätigungen führen nicht zu einem automatischen erneuten
  Schreiben. Eine Änderung kann am Gerät schon angekommen sein.
- Die Zuordnung zum A1310 stammt aus dem BLE-Namen bzw. der manuellen Auswahl.
  Das Protokoll besitzt hier keine ausgelesene Modellkennung.
- iOS-GATT-UUIDs, abweichende Firmware, Schlafverhalten und die Antwort des eigenen
  Geräts sind noch offen. Falls dieses Gerät SPP nicht anbietet, ist die Entschlüsselung des proprietären
  BLE-Profils erforderlich; der vorhandene BLE-Pfad erfasst hierfür die Dienste.
- Die in der App ebenfalls vorhandene Alarmprogrammierung wird nicht genutzt,
  solange Slotanzahl, Datumssemantik und Auswirkungen am Gerät unbestätigt sind.

Die meisten Tests verwenden synthetische, aus der App abgeleitete Bytefolgen.
Der BLE-Regressionstest verwendet zusätzlich die oben dokumentierte echte
Aufzeichnung. Für SPP liegen weiterhin keine Hardwareaufzeichnungen vor.
