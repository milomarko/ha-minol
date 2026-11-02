"""Client for the Minol eMonitoring portal (webservices.minol.com).

Login runs through Minol's Azure B2C page in a headless browser (Playwright).
The session cookies are then reused for the portal's JSON API.

Login flow adapted from 23Phantom08/ha_addons (MIT License).
"""

import json
import logging
import time

import requests
from playwright.sync_api import sync_playwright

log = logging.getLogger("minol.client")

BASE_URL = "https://webservices.minol.com"
APP = "/minol.com~kundenportal~em~web"
MONITORING_URL = f"{BASE_URL}{APP}/resources/monitoring/index.html?isMieter=true&redirect2=true"
B2C_HOST = "minolauth.b2clogin.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

# Portal views: consType + dlgKey.
# Heizkostenverteiler (units, converted to kWh by Minol) use HEIZUNG/100EH.
# Heat meters would use HZKWH/100KWH instead.
HEATING = ("HEIZUNG", "100EH")
HEATING_ROOMS = ("HEIZUNG", "100EHRAUM")
HOT_WATER = ("WARMWASSER", "200")
HEAT_METER = ("HZKWH", "100KWH")


class MinolError(Exception):
    pass


class MinolClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.user_num = None
        self.tenant = {}

    # ---------- login ----------

    def login(self, attempts: int = 3) -> None:
        last = None
        for i in range(1, attempts + 1):
            try:
                self._login_once()
                self._load_tenant()
                log.info("Login bei Minol erfolgreich")
                return
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("Login-Versuch %s/%s fehlgeschlagen: %s", i, attempts, e)
                if i < attempts:
                    time.sleep(30 * i)
        raise MinolError(f"Login fehlgeschlagen: {last}")

    def _login_once(self) -> None:
        self.session.cookies.clear()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                page.set_default_timeout(90_000)
                # The portal is slow and keeps connections open, so don't wait
                # for "networkidle"; wait for the redirect to the login page.
                page.goto(MONITORING_URL, wait_until="domcontentloaded")

                if B2C_HOST not in page.url:
                    try:
                        page.wait_for_url(f"**/{B2C_HOST}/**", timeout=60_000)
                    except Exception:  # noqa: BLE001
                        pass
                page.wait_for_load_state("domcontentloaded")

                if B2C_HOST in page.url:
                    page.locator(
                        'input#signInName, input[name="signInName"], input[type="email"]'
                    ).first.fill(self.email)
                    page.locator(
                        'input#password, input[name="password"], input[type="password"]'
                    ).first.fill(self.password)
                    page.locator('button#next, button[type="submit"]').first.click()

                    page.wait_for_url(f"{BASE_URL}/**", timeout=60_000)
                    # A wrong password keeps the browser on the B2C page.
                    if B2C_HOST in page.url:
                        raise MinolError("Minol hat den Login abgelehnt (E-Mail/Passwort?)")
                    page.goto(MONITORING_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(3_000)

                cookies = context.cookies()
            finally:
                browser.close()

        for c in cookies:
            self.session.cookies.set(
                c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/")
            )
        if not any(c["name"] == "MYSAPSSO2" for c in cookies):
            raise MinolError("Kein Portal-Cookie erhalten")

    def _headers(self) -> dict:
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=UTF-8",
            "Referer": f"{BASE_URL}{APP}/resources/monitoring/index.html?isMieter=true",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _load_tenant(self) -> None:
        r = self.session.get(f"{BASE_URL}{APP}/rest/EMData/getUserTenants", headers=self._headers(), timeout=60)
        r.raise_for_status()
        if "json" not in r.headers.get("Content-Type", ""):
            raise MinolError("Portal-Sitzung ungültig")
        tenants = r.json()
        if not tenants:
            raise MinolError("Keine Nutzeinheit im Minol-Konto gefunden")
        self.tenant = tenants[0]
        self.user_num = self.tenant.get("userNumber")

    # ---------- data ----------

    def read(self, view: tuple, start: str, end: str) -> dict:
        """Read one portal view for months start..end (YYYYMM)."""
        cons_type, dlg_key = view
        payload = {
            "userNum": self.user_num,
            "layer": "NE",
            "scale": "CALMONTH",
            "chartRefUnit": "ABS",
            "refObject": "DIN_AVG",
            "consType": cons_type,
            "dashBoardKey": "PE",
            "timelineStart": start,
            "timelineStartTxt": f"{start[4:]}.{start[:4]}",
            "timelineEnd": end,
            "timelineEndTxt": f"{end[4:]}.{end[:4]}",
            "valuesInKWH": True,
            "dlgKey": dlg_key,
        }
        r = self.session.post(
            f"{BASE_URL}{APP}/rest/EMData/readData",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        log.debug("%s/%s %s-%s: %s Tabellenzeilen, %s Diagrammwerte",
                  cons_type, dlg_key, start, end, len(data.get("table") or []), len(data.get("chart") or []))
        return data
