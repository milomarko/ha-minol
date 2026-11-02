"""Minol eMonitoring -> MQTT bridge for Home Assistant."""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import requests

from minol_client import HEAT_METER, HEATING_ROOMS, HOT_WATER, MinolClient

OPTIONS_PATH = "/data/options.json"
VERSION = "2.0.2"
DISCOVERY = "homeassistant/sensor/minol"
AVAIL_TOPIC = "minol/status"
DEVICE = {
    # Same identifiers/name as the 23Phantom08 add-on, so existing entity IDs stay.
    "identifiers": ["minol_account"],
    "name": "Minol",
    "manufacturer": "Minol",
    "model": "eMonitoring",
    "sw_version": VERSION,
}


def load_options() -> dict:
    with open(OPTIONS_PATH, encoding="utf-8") as f:
        opts = json.load(f)
    opts.setdefault("scan_interval_hours", 24)
    opts.setdefault("billing_start_month", 1)
    opts.setdefault("log_level", "info")
    return opts


opts = load_options()
logging.basicConfig(
    level=getattr(logging, str(opts["log_level"]).upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
# Keep third-party libraries quiet even in debug mode (they would log cookies).
for noisy in ("urllib3", "asyncio", "paho"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("minol")


# ---------- MQTT ----------

def mqtt_settings() -> dict:
    """Broker from the Supervisor (Mosquitto app) unless set in the options."""
    if opts.get("mqtt_host"):
        return {
            "host": opts["mqtt_host"],
            "port": opts.get("mqtt_port") or 1883,
            "username": opts.get("mqtt_user"),
            "password": opts.get("mqtt_password"),
        }
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.error("Kein MQTT-Broker gefunden. Bitte mqtt_host in der Konfiguration setzen.")
        sys.exit(1)
    r = requests.get(
        "http://supervisor/services/mqtt",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]


def connect_mqtt() -> mqtt.Client:
    s = mqtt_settings()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="minol-emonitoring")
    if s.get("username"):
        client.username_pw_set(s["username"], s.get("password"))
    client.will_set(AVAIL_TOPIC, "offline", retain=True)
    client.connect(s["host"], int(s["port"]), 60)
    client.loop_start()
    client.publish(AVAIL_TOPIC, "online", retain=True)
    log.info("Mit MQTT verbunden (%s:%s)", s["host"], s["port"])
    return client


class Publisher:
    def __init__(self, client: mqtt.Client):
        self.c = client

    def sensor(self, uid, name, state, unit=None, icon=None, device_class=None,
               state_class=None, attrs=None):
        config = {
            "name": name,
            "unique_id": f"minol_{uid}",
            "default_entity_id": f"sensor.minol_{uid}",
            "state_topic": f"minol/{uid}/state",
            "availability_topic": AVAIL_TOPIC,
            "device": DEVICE,
        }
        if unit:
            config["unit_of_measurement"] = unit
        if icon:
            config["icon"] = icon
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        if attrs is not None:
            config["json_attributes_topic"] = f"minol/{uid}/attributes"
        self.c.publish(f"{DISCOVERY}/{uid}/config", json.dumps(config), retain=True)
        self.c.publish(f"minol/{uid}/state", "" if state is None else str(state), retain=True)
        if attrs is not None:
            self.c.publish(f"minol/{uid}/attributes", json.dumps(attrs, ensure_ascii=False), retain=True)

    def remove(self, uid):
        for topic in (f"{DISCOVERY}/{uid}/config", f"minol/{uid}/state", f"minol/{uid}/attributes"):
            self.c.publish(topic, "", retain=True)


# ---------- periods ----------

def add_months(y: int, m: int, n: int) -> tuple:
    i = y * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def ym(t: tuple) -> str:
    return f"{t[0]}{t[1]:02d}"


def label(key: str) -> str:
    return f"{key[4:]}.{key[:4]}"


def periods(start_month: int, now: datetime) -> dict:
    cur_start = (now.year, start_month) if now.month >= start_month else (now.year - 1, start_month)
    last_start = add_months(*cur_start, -12)
    out = {}
    for key, s in (("current", cur_start), ("last", last_start)):
        e = add_months(*s, 11)
        text = str(s[0]) if start_month == 1 else f"{label(ym(s))}–{label(ym(e))}"
        out[key] = {"start": ym(s), "end": ym(e), "text": text}
    return out


# ---------- parsing ----------

def r1(v):
    return None if v is None else round(float(v), 1)


def parse(data: dict) -> dict:
    """Monthly values (non-REF chart rows) and per-room table of one portal view."""
    months = {}
    for e in data.get("chart") or []:
        key = e.get("categoryInt")
        m = months.setdefault(key, {"kwh": None, "ref": None, "rooms": {}})
        value = e.get("value")
        if e.get("keyFigure") == "REF":
            m["ref"] = value
        elif (e.get("anzValues") or 0) > 0 and value is not None:
            m["rooms"][e["keyFigure"]] = value
            m["kwh"] = (m["kwh"] or 0) + value

    rooms = {}
    for row in data.get("table") or []:
        name = row.get("raum") or "Unbekannt"
        r = rooms.setdefault(name, {"kwh": 0.0, "units": 0.0, "devices": []})
        r["kwh"] += row.get("consumptionBew") or 0
        r["units"] += row.get("consumption") or 0
        r["devices"].append(row.get("gerNr"))

    with_data = [k for k in sorted(months) if months[k]["kwh"] is not None]
    return {
        "months": months,
        "with_data": with_data,
        "rooms": rooms,
        "kwh": sum(r["kwh"] for r in rooms.values()),
        "units": sum(r["units"] for r in rooms.values()),
        "ref": sum(months[k]["ref"] or 0 for k in with_data),
    }


def month_list(p: dict) -> list:
    return [
        {"monat": label(k), "kwh": r1(p["months"][k]["kwh"]), "durchschnitt_kwh": r1(p["months"][k]["ref"])}
        for k in sorted(p["months"]) if p["months"][k]["kwh"] is not None
    ]


def slug(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


# ---------- sync ----------

def pick_heating_view(client: MinolClient, per: dict):
    """Heizkostenverteiler (HEIZUNG) by default, heat meters (HZKWH) as fallback."""
    data = client.read(HEATING_ROOMS, per["last"]["start"], per["current"]["end"])
    if data.get("table"):
        return HEATING_ROOMS
    if client.read(HEAT_METER, per["last"]["start"], per["current"]["end"]).get("table"):
        log.info("Wärmezähler erkannt, nutze HZKWH")
        return HEAT_METER
    return HEATING_ROOMS


def sync(pub: Publisher) -> None:
    client = MinolClient(opts["minol_email"], opts["minol_password"])
    client.login()

    now = datetime.now()
    per = periods(int(opts["billing_start_month"]), now)
    heat_view = pick_heating_view(client, per)

    heat = {k: parse(client.read(heat_view, v["start"], v["end"])) for k, v in per.items()}
    water = {k: parse(client.read(HOT_WATER, v["start"], v["end"])) for k, v in per.items()}
    # Hot water volume (m³) comes from the table's raw consumption.
    for p in water.values():
        p["m3"] = p["units"]

    all_heat_months = sorted(set(heat["last"]["with_data"]) | set(heat["current"]["with_data"]))
    data_month = label(all_heat_months[-1]) if all_heat_months else None

    # Heating per period
    for key, title, sc in (("current", "Aktuelle Periode", "total_increasing"), ("last", "Letzte Periode", "total")):
        p = heat[key]
        pub.sensor(
            f"heating_period_{key}", f"Heizung {title}", r1(p["kwh"]), "kWh", "mdi:radiator",
            "energy", sc,
            {
                "zeitraum": per[key]["text"],
                "monate_mit_daten": len(p["with_data"]),
                "datenstand": data_month,
                "einheiten": r1(p["units"]),
                "durchschnittsnutzer_kwh": r1(p["ref"]),
                "vergleich_durchschnitt_prozent": round(p["kwh"] / p["ref"] * 100) if p["ref"] else None,
                "raeume_kwh": {name: r1(r["kwh"]) for name, r in sorted(p["rooms"].items())},
                "monatswerte": month_list(p),
            },
        )

    # Hot water per period
    for key, title, sc in (("current", "Aktuelle Periode", "total_increasing"), ("last", "Letzte Periode", "total")):
        p = water[key]
        pub.sensor(
            f"hot_water_period_{key}", f"Warmwasser {title}", round(p["m3"], 2), "m³",
            "mdi:water-thermometer", "water", sc,
            {
                "zeitraum": per[key]["text"],
                "monate_mit_daten": len(p["with_data"]),
                "kwh": r1(p["kwh"]),
                "durchschnittsnutzer_kwh": r1(p["ref"]),
                "monatswerte": month_list(p),
            },
        )

    # Latest month with data, compared to the same month one year earlier
    months = {**heat["last"]["months"], **heat["current"]["months"]}
    if all_heat_months:
        last_key = all_heat_months[-1]
        prev_key = ym(add_months(int(last_key[:4]), int(last_key[4:]), -12))
        prev = months.get(prev_key, {})
        pub.sensor(
            "heating_last_month", "Heizung Letzter Monat", r1(months[last_key]["kwh"]), "kWh",
            "mdi:calendar-month", "energy", None,
            {
                "monat": label(last_key),
                "durchschnittsnutzer_kwh": r1(months[last_key]["ref"]),
                "vorjahresmonat": label(prev_key),
                "vorjahresmonat_kwh": r1(prev.get("kwh")),
            },
        )

    # Per room (current period, with previous period for comparison)
    for name in sorted(set(heat["current"]["rooms"]) | set(heat["last"]["rooms"])):
        cur = heat["current"]["rooms"].get(name, {"kwh": 0, "units": 0, "devices": []})
        last = heat["last"]["rooms"].get(name, {"kwh": 0, "units": 0, "devices": []})
        pub.sensor(
            f"heating_room_{slug(name)}", f"Heizung {name}", r1(cur["kwh"]), "kWh", "mdi:radiator",
            "energy", "total_increasing",
            {
                "raum": name,
                "zeitraum": per["current"]["text"],
                "einheiten": r1(cur["units"]),
                "letzte_periode_kwh": r1(last["kwh"]),
                "geraete": sorted(set(cur["devices"]) | set(last["devices"])),
                "monatswerte": [
                    {"monat": label(k), "kwh": r1(months[k]["rooms"].get(name))}
                    for k in all_heat_months
                ],
            },
        )

    pub.sensor("data_month", "Datenstand", data_month, icon="mdi:calendar-check",
               attrs={"letzte_abfrage": now.isoformat(timespec="seconds")})

    # Customer info (kept from the previous add-on)
    t = client.tenant
    address = " ".join(str(t.get(k) or "") for k in ("addrStreet", "addrHouseNum", "addrPostalCode", "addrCity")).split()
    pub.sensor(
        "customer_info", "Kundendaten", t.get("userNumber"), icon="mdi:account",
        attrs={
            "name": t.get("name"),
            "address": " ".join(address),
            "floor": t.get("geschossText"),
            "position": t.get("lageText"),
            "move_in_date": t.get("einzugMieter"),
            "property_number": str(t.get("lgnr") or "").strip(),
        },
    )

    # Cold water sensors of the old add-on are not used any more.
    for uid in ("cold_water_period_current", "cold_water_period_last"):
        pub.remove(uid)

    log.info(
        "Sync fertig: Heizung %s %s kWh, %s %s kWh, Datenstand %s",
        per["current"]["text"], r1(heat["current"]["kwh"]), per["last"]["text"], r1(heat["last"]["kwh"]), data_month,
    )


def main() -> None:
    if not opts.get("minol_email") or not opts.get("minol_password"):
        log.error("Bitte Minol-E-Mail und -Passwort in der Konfiguration eintragen.")
        sys.exit(1)
    pub = Publisher(connect_mqtt())
    interval = max(6, int(opts["scan_interval_hours"])) * 3600
    while True:
        try:
            sync(pub)
            wait = interval
        except Exception as e:  # noqa: BLE001
            log.error("Sync fehlgeschlagen: %s", e)
            wait = 3600  # retry in an hour
        time.sleep(wait)


if __name__ == "__main__":
    main()
