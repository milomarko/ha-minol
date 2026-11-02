# Changelog

## 2.0.1
- Login wartet nicht mehr auf „networkidle“, das langsame Portal führte sonst oft zum Timeout im ersten Versuch.

## 2.0.0
- Heizkostenverteiler werden richtig gelesen (HEIZUNG/100EH statt HZKWH/100KWH).
- Neu: Verbrauch je Raum, letzter Monat mit Vorjahresvergleich, Datenstand.
- Monatswerte und Vergleich mit dem Durchschnittsnutzer als Attribute.
- Abrechnungszeitraum frei wählbar (Kalenderjahr als Standard).
- MQTT-Zugang kommt automatisch vom Mosquitto-App.
- Keine Cookies oder HTML-Seiten mehr in Logs oder Dateien.
- Login mit bis zu 3 Versuchen, nach Fehler neuer Versuch nach 1 Stunde.
