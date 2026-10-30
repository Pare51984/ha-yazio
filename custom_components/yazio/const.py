"""Konstanten für die inoffizielle Yazio-Integration."""

from datetime import timedelta

DOMAIN = "yazio"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
# Option: show the fasting plan as a calendar (off by default).
CONF_FASTING_CALENDAR = "fasting_calendar"
# Option: polling interval in minutes.
CONF_SCAN_INTERVAL = "scan_interval"
SCAN_INTERVAL_CHOICES = [5, 15, 30]

SCAN_INTERVAL = timedelta(minutes=15)
# Streak and subscription change rarely.
EXTRA_INTERVAL = timedelta(hours=1)

# Die Yazio-API ist inoffiziell. Es gibt zwei bekannte Zugangsprofile:
# v15 mit dem älteren App-Client (genutzt von yazio-mcp und yazio-cli) und
# v22 mit dem aktuellen App-Client, der zusätzlich einen App-User-Agent verlangt.
# Die Integration probiert sie der Reihe nach und bleibt beim ersten, das klappt.
API_PROFILES = [
    {
        "name": "v15",
        "base_url": "https://yzapi.yazio.com/v15",
        "client_id": "1_4hiybetvfksgw40o0sog4s884kwc840wwso8go4k8c04goo4c",
        "client_secret": "6rok2m65xuskgkgogw40wkkk8sw0osg84s8cggsc4woos4s8o",
        "user_agent": None,
    },
    {
        "name": "v22",
        "base_url": "https://yzapi.yazio.com/v22",
        "client_id": "3_5rbw4kehpugw8ogsc8ck8oo4ogswgckcskc04gcg8kk8k48ssw",
        "client_secret": "25gdtt1hvdi8gwowoww4oo88sgsw0oo04o0og0kkgwwks8k0k",
        "user_agent": "YAZIO/26.30.1 (com.yazio.ios.YAZIO; build:2607271240; iOS 27.0.0) Ktor",
    },
]

MEALS = ("breakfast", "lunch", "dinner", "snack")
