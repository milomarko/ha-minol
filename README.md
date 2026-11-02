# Minol eMonitoring für Home Assistant

Home-Assistant-App, die Heizungs- und Warmwasserverbrauch aus dem
Minol-Mieterportal liest (auch für Heizkostenverteiler) und per MQTT als
Sensoren bereitstellt.

> **Inoffizielles Projekt.** Nicht mit der Minol Messtechnik W. Lehmann GmbH & Co. KG
> verbunden, nicht von ihr unterstützt oder geprüft. „Minol“ ist eine Marke ihres
> Inhabers und wird hier nur genannt, um zu beschreiben, mit welchem Portal die App
> funktioniert. Die App nutzt ausschließlich die eigenen Zugangsdaten der Nutzerin
> bzw. des Nutzers und liest nur deren eigene Verbrauchsdaten, einmal pro Abfrage-
> intervall. Nutzung auf eigene Verantwortung (siehe [LICENSE](LICENSE)).

## Installation

[![Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmilomarko%2Fha-minol)

Oder: Einstellungen → Apps → App-Store → ⋮ → Repositories →
`https://github.com/milomarko/ha-minol`

Details: [minol/DOCS.md](minol/DOCS.md)

Basiert auf dem Login-Ablauf von
[23Phantom08/ha_addons](https://github.com/23Phantom08/ha_addons) (MIT).
