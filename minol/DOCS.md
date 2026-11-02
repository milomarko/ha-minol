# Minol eMonitoring

Holt deine Verbrauchswerte aus dem Minol-Mieterportal (eMonitoring) und legt sie
als Sensoren in Home Assistant an.

**Inoffiziell:** nicht mit Minol verbunden oder von Minol unterstützt. Die App
nutzt nur deine eigenen Zugangsdaten und liest nur deine eigenen Daten.

## Einrichtung

1. Mosquitto-App installieren und starten (MQTT-Integration muss eingerichtet sein).
2. Minol-E-Mail und -Passwort eintragen.
3. `billing_start_month`: Monat, in dem dein Abrechnungszeitraum beginnt
   (1 = Kalenderjahr).
4. App starten. Die Anmeldung bei Minol dauert etwa eine Minute.

Minol überträgt die Monatswerte bis zum 7. des Folgemonats. Eine Abfrage alle
24 Stunden reicht.

## Sensoren

| Sensor | Inhalt |
|---|---|
| Heizung Aktuelle / Letzte Periode | kWh im Abrechnungszeitraum, Monatswerte, Räume, Vergleich mit dem Durchschnittsnutzer |
| Heizung Letzter Monat | kWh im neuesten Monat mit Daten und im selben Monat des Vorjahres |
| Heizung <Raum> | kWh je Raum in der aktuellen Periode, Vorperiode, Monatswerte |
| Warmwasser Aktuelle / Letzte Periode | m³ (und kWh) im Abrechnungszeitraum |
| Datenstand | neuester Monat mit Daten |
| Kundendaten | Nutzernummer, Adresse, Einzugsdatum |

`mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` sind nur nötig, wenn du
einen anderen MQTT-Broker als die Mosquitto-App nutzt.
