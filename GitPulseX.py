
#!/usr/bin/env python3
"""
GitHub Multi-Repository Release & Stats Collector

Sammelt Statistiken über ALLE Repositories eines GitHub-Benutzers.

Neu in dieser Version:
- Dialoge mit reinem SCHWARZEM Hintergrund und weißer Schrift
- Benutzerverwaltung über github_users.json (mehrere Benutzer möglich)
- Token-Abfrage beim Start (optional, wird NICHT gespeichert)
- Speicherort wird gemerkt (Skript-Ordner / Downloads-Ordner) – in JSON änderbar
- Follower-Detail-Abfrage standardmäßig AUS (Rate-Limit-Schutz)
- Klare Meldung bei GitHub Rate-Limit
"""
import requests
from datetime import datetime, timezone
from pathlib import Path
from platformdirs import user_data_path
import json
import argparse
import sys
import re
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple

# PyQt5 Importe
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDateEdit, QComboBox, QTextEdit, QScrollArea,
    QWidget, QFrame, QMainWindow, QMessageBox, QProgressBar
)
from PyQt5.QtCore import (
    Qt, QTimer, QDate, pyqtSignal, QUrl, QRect, QSize, QMetaObject,
    Q_ARG, QEvent, QThread, pyqtSignal as _pyqt_signal
)

from PyQt5.QtGui import (
    QPalette, QColor, QPixmap, QFontMetrics, QDesktopServices, QIcon, QFont
)

# ============================================================
# Konfiguration
# ============================================================

# App-Metadaten
APP_NAME = "GitPulseX"
APP_AUTHOR = "BinhDiez"
APP_VERSION = "2.0"
APP_WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"

# GitHub-Repo für Info-Dialog und Release-Check
APP_GITHUB_OWNER = "BinhDiez"
APP_GITHUB_REPO  = "GitPulseX"
APP_GITHUB_URL   = f"https://github.com/{APP_GITHUB_OWNER}/{APP_GITHUB_REPO}"
APP_LICENSE      = "MIT"

# Verzeichnis-Konstanten
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_FILE = "GitHub_all_repos_stats.txt"
DEFAULT_CONFIG_FILE = "github_stats_config.json"
USERS_FILE = "github_users.json"
TOKENS_FILE = "github_tokens.json"
LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "app.log"
STATISTICS_DIR_NAME = "statistics"
SETTINGS_DIR_NAME = "settings"
ASSETS_DIR_NAME = "assets"

# Logging-Konfiguration (Dev-Modus)
LOG_LEVEL_DEFAULT = logging.INFO
LOG_MAX_BYTES = 1_000_000     # 1 MB
LOG_BACKUP_COUNT = 5

# Globales Logger-Objekt
logger = logging.getLogger(APP_NAME)

### ============================================================
### KONFIGURATIONSKLASSE
### ============================================================

class Config:
    """Verwaltet Konfiguration aus Datei und Befehlszeile"""

    # Whitelist der Keys, die in die JSON geschrieben/gelesen werden.
    # Beim Laden werden unbekannte Keys mit Warnung ignoriert
    # Neue Felder: einfach in PERSISTED_KEYS eintragen → überall verfügbar

    PERSISTED_KEYS = (
        "output_file",
        "save_location",
        "include_page_views",
        "include_traffic",
        "include_clones",
        "include_contributors",
        "include_forks",
        "include_stars",
        "include_watchers",
        "show_dialog",
        "skip_forks",
        "skip_archived",
        "skip_private",
        "only_with_releases",
        "repo_filter",
        "include_followers",
        "followers_detail",
        # "verbose" ist NICHT mehr persistiert – nur noch CLI-Shortcut
        "log_level",           # NEU: DEBUG / INFO / WARNING / ERROR
    )

    def __init__(self):
        self.owner = ""                # wird durch UserManager gesetzt
        self.token = ""
        self.output_file = DEFAULT_OUTPUT_FILE
        self.include_page_views = True
        self.include_traffic = True
        self.include_clones = True
        self.include_contributors = True
        self.include_forks = True
        self.include_stars = True
        self.include_watchers = True
        self.verbose = False
        self.show_dialog = True
        self.skip_forks = True
        self.skip_archived = True
        self.skip_private = False
        self.only_with_releases = False
        self.repo_filter = ""
        self.include_followers = True
        self.followers_detail = False    # Standard: AUS (Rate-Limit-Schutz)
        # Speicherort-Merker: "script", "downloads" oder "" (=immer fragen)
        self.save_location = ""
        # Log-Level: DEBUG, INFO, WARNING, ERROR
        self.log_level = "INFO"

    def load_from_file(self, config_file: str = None):
        if config_file is None:
            config_path = APP_PATHS["settings"] / DEFAULT_CONFIG_FILE
        else:
            config_path = Path(config_file)
            if not config_path.is_absolute():
                config_path = APP_PATHS["settings"] / config_path
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                unknown = []
                for key, value in data.items():
                    # owner wird NICHT aus config geladen (UserManager zuständig)
                    if key == "owner":
                        continue
                    if key not in self.PERSISTED_KEYS:
                        unknown.append(key)
                        continue
                    # output_file: nur Basisnamen laden (ohne Datum/Owner)
                    if key == "output_file" and isinstance(value, str):
                        value = strip_dynamic_parts_from_filename(value)
                    # save_location: alter Wert "script" → "statistics"
                    if key == "save_location" and value == "script":
                        value = "statistics"
                        logger.debug(
                            f"Config: save_location 'script' → 'statistics' "
                            f"(Rückwärtskompatibilität)"
                        )
                    # Typ prüfen
                    current = getattr(self, key)
                    if current is not None and not isinstance(value, type(current)):
                        # Typ-Konflikt vermeiden
                        if isinstance(current, bool) and not isinstance(value, bool):
                            # JSON: 0/1 akzeptieren
                            value = bool(value)
                        elif isinstance(current, str) and isinstance(value, (int, float)):
                            value = str(value)
                    setattr(self, key, value)
                    logger.debug(f"  Config: {key} = {value!r}")

                if self.verbose:
                    print(f"Konfiguration geladen von: {config_path}")
                    if unknown:
                        print(f"  ⚠️  Unbekannte Keys ignoriert: "
                              f"{', '.join(unknown)}")
                logger.debug(f"Config fertig geladen aus {config_path.name}")
            except Exception:
                print(f"Warnung: Konfigurationsdatei konnte nicht geladen werden")
                logger.exception(f"Warnung: Konfigurationsdatei konnte nicht geladen werden")

    def save_to_file(self, config_file: str = None):
        """Speichert die aktuelle Konfiguration als JSON (ohne owner und token)."""
        if config_file is None:
            config_path = APP_PATHS["settings"] / DEFAULT_CONFIG_FILE
        else:
            config_path = Path(config_file)
            if not config_path.is_absolute():
                config_path = APP_PATHS["settings"] / config_path

        data = {}
        for key in self.PERSISTED_KEYS:
            if key == "output_file":
                # Basisnamen normalisieren: mehrfache _owner_YYYY-MM-DD
                # werden zuverlässig entfernt (siehe Fix A).
                raw_name = Path(self.output_file).name
                base_name = strip_dynamic_parts_from_filename(raw_name)
                # Doppelte Absicherung: Endung erhalten
                if not base_name.lower().endswith(".txt"):
                    base_name = "GitHub_all_repos_stats.txt"
                data[key] = base_name
                # Sicherstellen, dass self.output_file auch im Objekt
                # den Basisnamen trägt (für nächste Runden in main()).
                self.output_file = base_name
            else:
                data[key] = getattr(self, key, None)

        try:
            logger.debug(f"Config speichern nach {config_path.name}:")
            for k, v in data.items():
                logger.debug(f"  {k} = {v!r}")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if self.verbose:
                print(f"💾 Konfiguration gespeichert: {config_path}")
        except Exception:
            print(f"⚠️  Konfiguration konnte nicht gespeichert werden")
            logger.exception(f"⚠️  Konfiguration konnte nicht gespeichert werden")

    def parse_args(self):
        parser = argparse.ArgumentParser(
            description="Sammelt GitHub Statistiken für ALLE Repositories eines Benutzers"
        )
        parser.add_argument("-o", "--owner", default=self.owner,
                            help="GitHub Benutzername (wird durch UserManager verwaltet)")
        parser.add_argument("-t", "--token", default=self.token,
                            help="GitHub Personal Access Token")
        parser.add_argument("-f", "--output", default=self.output_file,
                            help=f"Output Datei (default: {self.output_file})")
        parser.add_argument("--log-level", default=None,
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            help="Log-Level (Standard: INFO)")

        # --- Boolean-Flags: default=None, damit JSON-Werte erhalten bleiben ---
        parser.add_argument("--no-page-views", action="store_false",
                            dest="include_page_views", default=None,
                            help="Seitenaufrufe nicht abfragen")
        parser.add_argument("--no-traffic", action="store_false",
                            dest="include_traffic", default=None,
                            help="Traffic-Daten nicht abfragen")
        parser.add_argument("--no-clones", action="store_false",
                            dest="include_clones", default=None,
                            help="Clone-Daten nicht abfragen")
        parser.add_argument("--no-dialog", action="store_false",
                            dest="show_dialog", default=None,
                            help="Keinen Dialog anzeigen (nur Datei)")
        parser.add_argument("--include-forks", action="store_false",
                            dest="skip_forks", default=None,
                            help="Geforkte Repos einschließen")
        parser.add_argument("--include-archived", action="store_false",
                            dest="skip_archived", default=None,
                            help="Archivierte Repos einschließen")
        parser.add_argument("--include-private", action="store_true",
                            dest="skip_private", default=None,
                            help="Private Repos einschließen")
        parser.add_argument("--only-with-releases", action="store_true",
                            dest="only_with_releases", default=None,
                            help="Nur Repos mit Releases anzeigen")
        parser.add_argument("--filter", default=None,
                            dest="repo_filter",
                            help="Regex-Filter für Repo-Namen")
        parser.add_argument("-v", "--verbose", action="store_true",
                            default=None,
                            help="Ausführliche Ausgabe")

        parser.add_argument("--no-followers", action="store_false",
                            dest="include_followers", default=None,
                            help="Follower nicht abfragen")
        parser.add_argument("--followers-detail", action="store_true",
                            dest="followers_detail", default=None,
                            help="Detail-Abfrage pro Follower (langsam)")
        parser.add_argument("--no-followers-detail", action="store_false",
                            dest="followers_detail", default=None,
                            help="Detail-Abfrage pro Follower deaktivieren")

        args = parser.parse_args()

        # --- Alle Werte nur übernehmen, wenn sie von CLI gesetzt wurden ---
        # Strings: nur wenn nicht None / nicht leer
        if args.owner:
            self.owner = args.owner
        if args.token:
            self.token = args.token
        if args.output:
            self.output_file = args.output
        if args.repo_filter is not None:
            self.repo_filter = args.repo_filter

        # Booleans: nur wenn der User den Schalter explizit gesetzt hat
        if args.include_page_views is not None:
            self.include_page_views = args.include_page_views
        if args.include_traffic is not None:
            self.include_traffic = args.include_traffic
        if args.include_clones is not None:
            self.include_clones = args.include_clones
        if args.show_dialog is not None:
            self.show_dialog = args.show_dialog
        if args.skip_forks is not None:
            self.skip_forks = args.skip_forks
        if args.skip_archived is not None:
            self.skip_archived = args.skip_archived
        if args.skip_private is not None:
            self.skip_private = args.skip_private
        if args.only_with_releases is not None:
            self.only_with_releases = args.only_with_releases
        if args.verbose is not None:
            self.verbose = args.verbose
        if args.include_followers is not None:
            self.include_followers = args.include_followers
        if args.followers_detail is not None:
            self.followers_detail = args.followers_detail

### ============================================================
### HILFSFUNKTIONEN
### ============================================================


# ============================================================
# APP VERSINSPRÜFUNG
# ============================================================

def check_latest_release(current_version: str = APP_VERSION,
                         timeout: int = 5) -> Optional[dict]:
    """
    Fragt das GitHub-Repo nach dem neuesten Release.

    Rückgabe (dict) oder None bei Fehler:
        {
            "tag":          "v2.1.0",
            "name":         "Release 2.1.0",
            "url":          "https://github.com/.../releases/tag/v2.1.0",
            "published_at": "2026-09-15T12:00:00Z",
            "body":         "...",
            "is_newer":     True,
        }
    """
    url = f"https://api.github.com/repos/{APP_GITHUB_OWNER}/{APP_GITHUB_REPO}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_NAME}-release-check",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 404:
            logger.debug("Release-Check: Repo hat noch keine Releases")
            return None
        if response.status_code != 200:
            logger.debug(f"Release-Check: HTTP {response.status_code}")
            return None
        data = response.json()

        tag = data.get("tag_name", "").strip()
        if not tag:
            return None

        # Versions-Vergleich: aus Tag sowas wie "v2.1.0" → "2.1.0"
        latest_clean = tag.lstrip("vV").strip()
        is_newer = _version_is_newer(latest_clean, current_version)

        return {
            "tag":          tag,
            "name":         data.get("name", tag),
            "url":          data.get("html_url", APP_GITHUB_URL),
            "published_at": data.get("published_at", ""),
            "body":         (data.get("body", "") or "").strip(),
            "is_newer":     is_newer,
        }
    except Exception as e:
        logger.debug(f"Release-Check fehlgeschlagen: {e}")
        return None

def _version_is_newer(latest: str, current: str) -> bool:
    """
    Vergleicht zwei Versionsstrings der Form 'X.Y' oder 'X.Y.Z'.
    Rückgabe: True wenn latest > current.
    """
    def _parse(v):
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        # Auf 3 Stellen normalisieren
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    try:
        return _parse(latest) > _parse(current)
    except Exception:
        return False

# ============================================================
# Zentrale Pfad-Verwaltung (Dev- und Bundle-Modus)
# ============================================================

def get_app_paths() -> dict:
    """
    Liefert alle App-Pfade, abhängig von Dev- oder Bundle-Modus.

    Dev-Modus (nicht gefroren):
        base = SCRIPT_DIR  →  alles im Projektordner
    Bundle-Modus (PyInstaller, sys.frozen=True):
        base = ~/Library/Application Support/GitPulseX  (macOS)
             = %APPDATA%\\GitPulseX                     (Windows)
             = ~/.local/share/GitPulseX                 (Linux)

    Rückgabe (dict):
        base        : Basis-Verzeichnis
        logs        : Log-Verzeichnis        (<base>/logs)
        settings    : Konfigurationsordner   (<base>/settings)
        statistics  : Bericht-Ordner         (<base>/statistics)
        assets      : Icon-/Bildordner
        is_frozen   : True im Bundle, sonst False
    """
    is_frozen = getattr(sys, "frozen", False)

    # Override per Umgebungsvariable (für Tests und Nutzer-Präferenz)
    env_data_dir = os.environ.get("GITPULSEX_DATA_DIR", "").strip()
    if env_data_dir:
        base = Path(env_data_dir).expanduser().resolve()
        # Assets bleiben im Script-Ordner (bzw. _MEIPASS)
        if is_frozen:
            assets_dir = Path(getattr(sys, "_MEIPASS", SCRIPT_DIR)) / ASSETS_DIR_NAME
        else:
            assets_dir = SCRIPT_DIR / ASSETS_DIR_NAME
    elif is_frozen:
        # --- Bundle-Modus ---
        base = Path(user_data_path(APP_NAME, APP_AUTHOR))
        assets_dir = Path(getattr(sys, "_MEIPASS", SCRIPT_DIR)) / ASSETS_DIR_NAME
    else:
        # --- Dev-Modus ---
        base = SCRIPT_DIR
        assets_dir = SCRIPT_DIR / ASSETS_DIR_NAME

    paths = {
        "base":       base,
        "logs":       base / LOG_DIR_NAME,
        "settings":   base / SETTINGS_DIR_NAME,
        "statistics": base / STATISTICS_DIR_NAME,
        "assets":     assets_dir,
        "is_frozen":  is_frozen,
    }

    # Ordner anlegen (idempotent – kein Fehler wenn schon vorhanden)
    for key in ("logs", "settings", "statistics", "assets"):
        try:
            paths[key].mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"⚠️  Ordner '{paths[key]}' konnte nicht angelegt werden: {e}")

    return paths

# Modul-weite Pfad-Instanz (beim Import berechnet)
APP_PATHS = get_app_paths()

def migrate_legacy_files():
    """
    Verschiebt Dateien aus dem SCRIPT_DIR in die neuen Unterordner
    (settings/, logs/, statistics/), wenn sie dort noch nicht liegen.

    Wird beim Start einmal aufgerufen. Idempotent — mehrfacher Aufruf
    ist unschädlich.
    """
    if APP_PATHS["is_frozen"]:
        # Im Bundle-Modus gibt es keine "alten" Dateien im Script-Ordner
        # (bzw. das Skript läuft aus einem temporären Verzeichnis).
        # Deshalb nichts migrieren.
        return

    # Welche Dateien wohin?
    migrations = [
        (SCRIPT_DIR / DEFAULT_CONFIG_FILE,  APP_PATHS["settings"] / DEFAULT_CONFIG_FILE),
        (SCRIPT_DIR / USERS_FILE,           APP_PATHS["settings"] / USERS_FILE),
        (SCRIPT_DIR / TOKENS_FILE,          APP_PATHS["settings"] / TOKENS_FILE),
    ]

    for old_path, new_path in migrations:
        if not old_path.exists():
            continue
        if new_path.exists():
            # Ziel existiert schon → alte Datei nicht überschreiben,
            # aber als .bak umbenennen, damit nichts verloren geht.
            bak = old_path.with_suffix(old_path.suffix + ".bak")
            try:
                old_path.rename(bak)
                print(f"ℹ️  Alte Datei gesichert: {bak.name}")
            except Exception as e:
                print(f"⚠️  Konnte {old_path.name} nicht sichern: {e}")
            continue

        try:
            old_path.rename(new_path)
            print(f"📦 Migriert: {old_path.name} → {new_path.parent.name}/")
        except Exception as e:
            print(f"⚠️  Migration fehlgeschlagen für {old_path.name}: {e}")

    # Logs: schon in logs/? Dann alte app.log aus SCRIPT_DIR entfernen
    old_log = SCRIPT_DIR / LOG_FILE_NAME
    new_log = APP_PATHS["logs"] / LOG_FILE_NAME
    if old_log.exists() and old_log != new_log:
        try:
            # Wenn bereits eine neue Logdatei existiert: alte umbenennen
            if new_log.exists():
                bak = old_log.with_suffix(".log.bak")
                old_log.rename(bak)
                print(f"ℹ️  Alte Logdatei gesichert: {bak.name}")
            else:
                old_log.rename(new_log)
                print(f"📦 Migriert: {old_log.name} → {new_log.parent.name}/")
        except Exception as e:
            print(f"⚠️  Logdatei-Migration fehlgeschlagen: {e}")

    # Assets (PNG-Dateien) in assets/ verschieben
    asset_files = ["BinhDiez.png", "GitPulseX.png"]
    for asset_name in asset_files:
        old_path = SCRIPT_DIR / asset_name
        new_path = APP_PATHS["assets"] / asset_name

        if not old_path.exists():
            continue
        if new_path.exists():
            # Schon da → alte Datei entfernen (Duplikat)
            try:
                old_path.unlink()
                print(f"🗑️  Duplikat entfernt: {asset_name}")
            except Exception as e:
                print(f"⚠️  Konnte {asset_name} nicht entfernen: {e}")
            continue

        try:
            old_path.rename(new_path)
            print(f"📦 Migriert: {asset_name} → assets/")
        except Exception as e:
            print(f"⚠️  Migration fehlgeschlagen für {asset_name}: {e}")

def get_downloads_dir() -> Path:
    """Ermittelt den Downloads-Ordner plattformunabhängig."""
    import platform
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            )
            path, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            p = Path(path)
            if p.exists():
                return p
        except Exception:
            pass
        return home / "Downloads"

    elif system == "Darwin":  # macOS
        return home / "Downloads"

    else:  # Linux & andere
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg:
            p = Path(xdg)
            if p.exists():
                return p
        user_dirs = home / ".config" / "user-dirs.dirs"
        if user_dirs.exists():
            try:
                with open(user_dirs, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("XDG_DOWNLOAD_DIR"):
                            val = line.split("=", 1)[1].strip().strip('"')
                            val = val.replace("$HOME", str(home))
                            p = Path(val)
                            if p.exists():
                                return p
            except Exception:
                pass
        p = home / "Downloads"
        if p.exists():
            return p
        return home

def build_output_filename(config_owner: str, base_output: str) -> str:
    """
    Erzeugt einen Dateinamen mit Benutzer + Datum, damit mehrere
    Läufe sich nicht gegenseitig überschreiben.

    Beispiel:
      base_output  = "GitHub_all_repos_stats.txt"
      config_owner = "BinhDiez"
      Ergebnis     = "GitHub_all_repos_stats_BinhDiez_2026-09-18.txt"
    """
    base = Path(base_output)
    stem = base.stem or "GitHub_all_repos_stats"
    suffix = base.suffix if base.suffix else ".txt"
    stamp = datetime.now().strftime("%Y-%m-%d")
    # Benutzernamen für Dateinamen absichern (nur erlaubte Zeichen)
    safe_owner = re.sub(r"[^A-Za-z0-9_\-]", "_", config_owner or "user")
    return f"{stem}_{safe_owner}_{stamp}{suffix}"

def strip_dynamic_parts_from_filename(name: str) -> str:
    """
    Entfernt den Datums- und Benutzernamen-Teil aus einem Dateinamen,
    damit er mehrfach verwendet werden kann.

    Beispiele:
      "GitHub_all_repos_stats_BinhDiez_2026-09-18.txt"
        → "GitHub_all_repos_stats.txt"
      "GitHub_all_repos_stats_BinhDiez_2026-09-18_BinhDiez_2026-09-19.txt"
        → "GitHub_all_repos_stats.txt"
      "GitHub_BinhDiez.txt"
        → "GitHub_BinhDiez.txt"  (kein Datum → unverändert)
    """
    p = Path(name)
    stem = p.stem
    suffix = p.suffix or ".txt"

    # Endungen _<owner>_<YYYY-MM-DD> SO OFT wie nötig entfernen
    # Der -Teil [A-Za-z0-9_.\-]+ ist non-greedy und matcht alles,
    # was kein "_<4-stellige-Zahl>-<2>-<2>" ist.
    prev = None
    while prev != stem:
        prev = stem
        # _<owner>_<YYYY-MM-DD> am Ende entfernen
        stem = re.sub(
            r"_[A-Za-z0-9_.\-]+_\d{4}-\d{2}-\d{2}$",
            "",
            stem
        )

    # Falls alles entfernt wurde, Default-Basisname verwenden
    if not stem or stem in ("_", "-"):
        stem = "GitHub_all_repos_stats"

    return f"{stem}{suffix}"

def parse_iso_safe(s: str) -> Optional[datetime]:
    """
    Parst einen ISO-8601-Zeitstempel robust. Liefert None bei Fehler.

    Unterstützt:
      - "2024-03-15T12:34:56Z"
      - "2024-03-15T12:34:56+00:00"
      - "2024-03-15T12:34:56.789Z"
      - "2024-03-15T12:34:56"  (ohne Zeitzone → UTC angenommen)
      - "2024-03-15"           (nur Datum)
    """
    if not s:
        return None
    if not isinstance(s, str):
        return None

    s = s.strip()
    if not s:
        return None

    # "Z" → "+00:00" (Python 3.11+ versteht Z nicht immer)
    candidate = s.replace("Z", "+00:00")

    # Versuch 1: fromisoformat direkt
    try:
        dt = datetime.fromisoformat(candidate)
        # Falls naive datetime → UTC annehmen
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Versuch 2: mit Datumsformaten
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue

    # Alle Versuche gescheitert
    return None

def open_directory(path: Path):
    """Öffnet ein Verzeichnis im Dateimanager."""
    import subprocess
    import platform
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))
        elif system == "Darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
    except Exception as e:
        print(f"⚠️  Verzeichnis konnte nicht geöffnet werden: {e}")

def classify_platform(asset_name: str) -> str:
    """
    Klassifiziert ein Release-Asset nach Plattform anhand des Dateinamens.

    Rückgabe: einer von
      'windows', 'mac_intel', 'mac_arm', 'linux', 'android', 'bsd', 'other'
    """
    name = asset_name.lower()

    # --- Windows ---
    if any(x in name for x in ["windows", "win32", "win64", "win-", "_win", ".exe", ".msi"]):
        return "windows"

    # --- macOS ARM (Apple Silicon) — VOR Intel prüfen, weil "arm64" auch "arm" enthält ---
    if any(x in name for x in ["darwin-arm", "darwin_arm", "macos-arm",
                               "apple-silicon", "apple_silicon",
                               "m1-", "_m1", "-m1.", "m2-", "_m2",
                               "aarch64-mac", "arm64-mac"]):
        return "mac_arm"

    # --- macOS Intel ---
    if any(x in name for x in ["darwin-x64", "darwin_amd64", "macos-x64",
                               "macos_intel", "macos-intel",
                               "intel-mac", "x86_64-mac", "amd64-mac"]):
        return "mac_intel"

    # --- Linux ---
    if any(x in name for x in ["linux", "ubuntu", "debian", "fedora",
                               "rhel", "centos", "alpine", "appimage",
                               ".deb", ".rpm", ".snap", ".flatpak"]):
        return "linux"

    # --- Android ---
    if any(x in name for x in ["android", ".apk", "aab"]):
        return "android"

    # --- BSD ---
    if any(x in name for x in ["freebsd", "openbsd", "netbsd"]):
        return "bsd"

    # --- Ältere Heuristik als Fallback ---
    if "win" in name:
        return "windows"
    if "mac" in name or "darwin" in name:
        if any(x in name for x in ["arm", "silicon", "m1", "m2", "m3"]):
            return "mac_arm"
        return "mac_intel"

    return "other"

def build_report_preview(full_text: str, max_lines: int = 80) -> str:
    """
    Kürzt den vollständigen Bericht auf eine Vorschau mit den
    wichtigsten Abschnitten (Header + Gesamtübersicht + Ranking).

    Beibehalten werden:
      - Kopfzeilen (bis zur ersten Leerzeile nach "Repos:")
      - Abschnitt "GESAMTÜBERSICHT"
      - Abschnitt "REPOSITORY-RANKING" (Top 10)
    """
    lines = full_text.splitlines()
    if not lines:
        return full_text

    preview: List[str] = []

    # ===== 1. Kopfbereich: bis zur ersten Leerzeile nach "Repos:" =====
    for i, line in enumerate(lines[:15]):
        preview.append(line)
        if line.startswith("Repos:"):
            # leerzeile mitnehmen
            if i + 1 < len(lines) and not lines[i + 1].strip():
                preview.append("")
            break

    preview.append("")
    preview.append("")

    # ===== 2. GESAMTÜBERSICHT =====
    def extract_section(start_marker: str, end_markers: List[str],
                        max_lines: int = 40) -> List[str]:
        """Extrahiert einen Abschnitt zwischen start_marker und end_marker."""
        result: List[str] = []
        inside = False
        for line in lines:
            if not inside:
                if line.startswith(start_marker):
                    inside = True
                    result.append(line)
                continue
            # Ende?
            if any(line.startswith(em) for em in end_markers):
                break
            result.append(line)
            if len(result) >= max_lines:
                result.append("    … (gekürzt)")
                break
        return result

    # GESAMTÜBERSICHT
    overview = extract_section(
        "🌍 GESAMTÜBERSICHT",
        ["🏆 REPOSITORY-RANKING", "📋 DETAILS", "📈 Ende"],
        max_lines=40
    )
    if overview:
        preview.extend(overview)
        preview.append("")
        preview.append("")

    # REPOSITORY-RANKING (Top 10, dann "…")
    ranking = extract_section(
        "🏆 REPOSITORY-RANKING",
        ["💻 SPRACH-VERTEILUNG", "📋 DETAILS", "📈 Ende"],
        max_lines=18
    )
    if ranking:
        preview.extend(ranking)
        preview.append("")
        preview.append("")

    # Kürzen auf max_lines
    if len(preview) > max_lines:
        preview = preview[:max_lines]
        preview.append("")

    # Fußzeile
    preview.append("=" * 78)
    preview.append("  ℹ️  Dies ist eine VORSCHAU.")
    preview.append("      Der vollständige Bericht enthält:")
    preview.append("        • Alle Repositories im Detail")
    preview.append("        • Release-Listen mit Downloadzahlen")
    preview.append("        • Plattform-Verteilung")
    preview.append("        • Follower-Analyse (falls aktiviert)")
    preview.append("      → Button 'Bericht öffnen' zeigt den kompletten Inhalt.")
    preview.append("=" * 78)

    return "\n".join(preview)

# ============================================================
# Logging
# ============================================================

def setup_logging(log_dir: Optional[Path] = None,
                  level: int = LOG_LEVEL_DEFAULT) -> Path:
    """
    Initialisiert das Logging-System.

    Schreibt in <log_dir>/app.log und auf die Konsole.
    Rotiert bei 1 MB, behält 5 Backups.

    Rückgabe: Pfad zur Logdatei.
    """
    # Log-Verzeichnis
    if log_dir is None:
        log_dir = APP_PATHS["logs"]
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / LOG_FILE_NAME

    # Logger konfigurieren
    logger.setLevel(level)
    # Doppelte Handler vermeiden (falls setup_logging 2x aufgerufen wird)
    if logger.handlers:
        logger.handlers.clear()

    # ---------- Format ----------
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    # ---------- RotatingFileHandler ----------
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # Wenn Logdatei nicht geschrieben werden kann, weiter ohne Datei
        print(f"⚠️  Logdatei konnte nicht angelegt werden: {e}")

    # ---------- StreamHandler (Konsole) ----------
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    # Auf der Konsole dezenteres Format
    console_fmt = logging.Formatter("%(levelname)-7s: %(message)s")
    stream_handler.setFormatter(console_fmt)
    logger.addHandler(stream_handler)

    # Logger nicht an Root weiterreichen (sonst Doppelausgabe)
    logger.propagate = False

    logger.info("=" * 60)
    logger.info(f"{APP_NAME} v{APP_VERSION} gestartet")
    logger.info(f"Logdatei: {log_file}")
    logger.info("=" * 60)

    return log_file

def get_log_file_path(log_dir: Optional[Path] = None) -> Path:
    """Gibt den Pfad zur aktuellen Logdatei zurück (ohne sie anzulegen)."""
    if log_dir is None:
        log_dir = APP_PATHS["logs"]
    return Path(log_dir) / LOG_FILE_NAME

def log_level_from_str(level_str: str) -> int:
    """Wandelt 'DEBUG'/'INFO'/'WARNING'/'ERROR' in logging-Konstante um."""
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(str(level_str).upper(), logging.INFO)

def install_excepthook():
    """
    Installiert einen globalen Exception-Hook, der unbehandelte
    Exceptions ins Log schreibt (mit Traceback).
    """
    def _hook(exc_type, exc_value, exc_tb):
        # KeyboardInterrupt normal behandeln
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Unbehandelte Exception – Anwendung wird beendet",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        # Optional: Original-Hook auch aufrufen (stderr)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook

def safe_slot(func):
    """
    Decorator für Qt-Slots: Fängt Exceptions ab und loggt sie.
    Verwendung:
        @safe_slot
        def on_button_clicked(self, checked=False):
            ...
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception(f"Exception im Qt-Slot '{func.__name__}'")
            # Optional: Fehlerdialog anzeigen
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(
                    None,
                    "Unerwarteter Fehler",
                    f"Ein unerwarteter Fehler ist aufgetreten:\n\n"
                    f"{func.__name__}\n\n"
                    f"Details siehe Logdatei."
                )
            except Exception:
                pass
    return wrapper

def apply_log_level(config: "Config", verbose_override: bool = False) -> None:
    """
    Setzt den Logger-Level anhand der Konfiguration.

    Priorität:
      1. verbose_override (CLI -v) → DEBUG
      2. config.log_level (JSON / Settings) → entsprechender Level
      3. Fallback: LOG_LEVEL_DEFAULT (INFO)
    """
    if verbose_override:
        effective = logging.DEBUG
        source = "CLI --verbose (überschreibt config.log_level)"
    else:
        effective = log_level_from_str(config.log_level)
        source = f"config.log_level={config.log_level!r}"

    logger.setLevel(effective)
    for handler in logger.handlers:
        handler.setLevel(effective)

    logger.info(f"Log-Level angewendet: {logging.getLevelName(effective)} "
                f"(Quelle: {source})")
    logger.debug(f"  Logger-Level: {logging.getLevelName(logger.level)}")
    for i, h in enumerate(logger.handlers):
        logger.debug(f"  Handler {i}: {type(h).__name__} → "
                     f"{logging.getLevelName(h.level)}")

# ============================================================
# Avatar-Verwaltung
# ============================================================

_APP_AVATAR_PIXMAP = None   # globaler QPixmap oder None
_APP_AVATAR_USER = ""       # zugehöriger Username

def fetch_github_avatar(username: str, token: str = "") -> Optional[QPixmap]:
    """
    Lädt das Avatar-Bild eines GitHub-Benutzers.

    Rückgabe: QPixmap oder None (bei Fehler / nicht gefunden)
    """
    if not username:
        return None

    # 1. Avatar-URL abrufen
    url = f"https://api.github.com/users/{username}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-stats-collector"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        avatar_url = data.get("avatar_url", "")
        if not avatar_url:
            return None
    except Exception:
        return None

    # 2. Avatar-Bild herunterladen
    try:
        # Optional: gewünschte Größe per Query-Parameter
        # GitHub liefert das Bild in der Standard-Größe (460×460).
        # Für unser Icon (72×72) reicht das locker.
        img_resp = requests.get(avatar_url, timeout=10)
        if img_resp.status_code != 200:
            return None

        pix = QPixmap()
        ok = pix.loadFromData(img_resp.content)
        if not ok or pix.isNull():
            return None
        return pix
    except Exception:
        return None

def set_app_avatar(username: str, token: str = "") -> bool:
    """
    Setzt das globale App-Avatar-Bild auf das Bild von 'username'.
    Rückgabe: True wenn erfolgreich, sonst False.
    """
    global _APP_AVATAR_PIXMAP, _APP_AVATAR_USER

    if username == _APP_AVATAR_USER and _APP_AVATAR_PIXMAP is not None:
        # schon geladen → nichts tun
        return True

    pix = fetch_github_avatar(username, token)
    if pix is not None:
        _APP_AVATAR_PIXMAP = pix
        _APP_AVATAR_USER = username
        return True
    else:
        _APP_AVATAR_PIXMAP = None
        _APP_AVATAR_USER = ""
        return False

def clear_app_avatar():
    """Setzt das Avatar zurück (z. B. wenn User wechselt)."""
    global _APP_AVATAR_PIXMAP, _APP_AVATAR_USER
    _APP_AVATAR_PIXMAP = None
    _APP_AVATAR_USER = ""


### ============================================================
### LANGUAGE-Klasse
### ============================================================

class Language:
    """Einfache Sprachverwaltung für den Dialog"""
    def __init__(self):
        self.current_lang = "de"
        self.translations = {
            "de": {
                "btn_ok": "OK",
                "btn_cancel": "Abbrechen",
                "app_title_format": "{}",
            }
        }

    def tr(self, key, *args):
        translations = self.translations.get(self.current_lang, {})
        text = translations.get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text


### ============================================================
### UNIVERSALDIALOG KLasse (Hintergrund / WEISSE Schrift)
### ============================================================

class myUniversalDialog(QDialog):
    """Eigene MessageBox mit Logo, App-Icon, gestylten Buttons und Sprachausgabe"""

    closed = pyqtSignal()

    ACCEPT_ACTIONS = {
        'yes', 'ok', 'accept', 'no',
        'open', 'openfile', 'openfolder',
        'print', 'save', 'continue', 'clean',
        'retry', 'apply', 'install',
        'exit', 'restart','statistics',
        'downloads', 'script', 'no_token', 'switch_user',
        'keep_token', 'delete_token',
        'open_folder', 'settings','Info',
    }

    REJECT_ACTIONS = {
        'cancel', 'close', 'abort', 'reject'
    }

    def __init__(self, parent=None, title="", message="", buttons=None,
                 icon_type="", voice_message="", default_button="",
                 text_alignment=Qt.AlignCenter, input_fields=None,
                 selectable_text=False, show_copy_button=False,
                 action_callbacks=None,
                 field_changed_callbacks=None):

        if parent is Ellipsis:
            parent = None

        super().__init__(parent)

        if parent and hasattr(parent, 'lang'):
            self.lang = parent.lang
        else:
            self.lang = Language()

        self.parent_widget = parent
        self.message = message
        self.voice_message = voice_message or message
        self.buttons = buttons or [(self.lang.tr('btn_ok'), "primary", "accept")]
        self.icon_type = icon_type
        self.result_value = None
        self.default_button = default_button
        self.text_alignment = text_alignment
        self.button_widgets = []
        self.input_fields = input_fields or []
        self.input_widgets = {}
        self.input_values = {}
        self.selectable_text = selectable_text
        self.show_copy_button = show_copy_button
        self.msg_label = None
        self.msg_edit = None
        self.action_callbacks = action_callbacks or {}
        self.field_changed_callbacks = field_changed_callbacks or {}

        if parent and hasattr(parent, 'main_window'):
            self.main_window = parent.main_window
        else:
            self.main_window = self._find_main_window(parent)

        self.voice_enabled = self._get_voice_enabled()

        self.init_button_style()
        self.init_ui(title, message, buttons, icon_type)
        self._apply_ultimate_dark_mode()

        if hasattr(self, 'default_button_widget') and self.default_button_widget:
            QTimer.singleShot(50, self.default_button_widget.setFocus)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

    def init_ui(self, title, message, buttons, icon_type):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        max_dialog_height = int(screen_geometry.height() * 0.8)
        max_dialog_width = int(screen_geometry.width() * 0.85)

        self.setWindowTitle(f"{title} — {APP_NAME}")
        self.setMinimumSize(800, 450)
        self.setMaximumSize(max_dialog_width, max_dialog_height)
        self.setSizeGripEnabled(True)
        self.setFocusPolicy(Qt.StrongFocus)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 15)

        # ---------- Titelzeile ----------
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 5, 20, 5)
        header_layout.setSpacing(15)

        # ---------- Icon links ----------
        icon_path = APP_PATHS["assets"] / "GitPulseX.png"
        if icon_path.exists():
            left_icon = QLabel()
            pix = QPixmap(str(icon_path))
            if not pix.isNull():
                left_icon.setPixmap(
                    pix.scaled(48, 48, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
                )
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(20)

        ICON_SIZE = 72  # Icongröße (größer als vorher)

        # ---------- Stretch links (außen) ----------
        header_layout.addStretch(1)

        # ---------- Icon links: GitHub-Avatar oder BinhDiez.png ----------
        left_icon = QLabel()
        left_icon.setFixedSize(ICON_SIZE, ICON_SIZE)
        left_icon.setAlignment(Qt.AlignCenter)
        left_icon.setStyleSheet("background-color: transparent;")

        # Priorität 1: globaler Avatar (aktuell ausgewählter GitHub-User)
        if _APP_AVATAR_PIXMAP is not None and not _APP_AVATAR_PIXMAP.isNull():
            left_icon.setPixmap(
                _APP_AVATAR_PIXMAP.scaled(
                    ICON_SIZE, ICON_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
        else:
            # Priorität 2: BinhDiez.png im Script-Ordner
            left_icon_path = APP_PATHS["assets"] / "BinhDiez.png"
            if left_icon_path.exists():
                pix = QPixmap(str(left_icon_path))
                if not pix.isNull():
                    left_icon.setPixmap(
                        pix.scaled(ICON_SIZE, ICON_SIZE,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                    )
        header_layout.addWidget(left_icon, 0, Qt.AlignVCenter)

        # ---------- Stretch links (innen) ----------
        header_layout.addStretch(1)

        # ---------- Titel mittig ----------
        title_label = QLabel(f"{title}")
        title_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 22px;
                font-weight: bold;
                padding: 5px;
                background-color: transparent;
            }
            """)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label, 0, Qt.AlignVCenter)

        # ---------- Stretch rechts (innen) ----------
        header_layout.addStretch(1)

        # ---------- Icon rechts: GitPulseX.png ----------
        right_icon_path = APP_PATHS["assets"] / "GitPulseX.png"
        right_icon = QLabel()
        right_icon.setFixedSize(ICON_SIZE, ICON_SIZE)
        right_icon.setAlignment(Qt.AlignCenter)
        right_icon.setStyleSheet("background-color: transparent;")
        if right_icon_path.exists():
            pix2 = QPixmap(str(right_icon_path))
            if not pix2.isNull():
                right_icon.setPixmap(
                    pix2.scaled(ICON_SIZE, ICON_SIZE,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
                )
        header_layout.addWidget(right_icon, 0, Qt.AlignVCenter)

        # ---------- Stretch rechts (außen) ----------
        header_layout.addStretch(1)

        main_layout.addWidget(header)


        # ---------- Scroll-Bereich (enthält Icon, Text, Inputs) ----------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(80)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical { background: #0A0A0A; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444444; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #666666; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        msg_container = QWidget()
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(15, 2, 15, 2)
        msg_layout.setSpacing(4)

        # ---------- Icon (optional) ----------
        if icon_type and icon_type != "":
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_texts = {
                "warning": "⚠️", "error": "❌", "question": "❓",
                "info": "ℹ️", "success": "✅"
            }
            icon_colors = {
                "warning": "#FF9800", "error": "#F44336", "question": "#2196F3",
                "info": "#2196F3", "success": "#4CAF50"
            }
            icon_label.setText(icon_texts.get(icon_type, "ℹ️"))
            icon_label.setStyleSheet(f"""
                font-size: 48px;
                background-color: transparent;
                color: {icon_colors.get(icon_type, "#FFFFFF")};
            """)
            msg_layout.addWidget(icon_label)

        # ---------- Inhalt: QTextEdit ODER QLabel ----------
        # Entscheide zuerst, ob HTML oder Plain-Text gerendert wird.
        html_tags = ("<br", "<p ", "<p>", "<b>", "<i>", "<span",
                     "<div", "<ul", "<ol", "<li", "<table")
        has_html_tags = any(tag in message for tag in html_tags)
        has_newlines = ("\n" in message)

        # Nur HTML rendern, wenn es WIRKLICH HTML ist (kurz + Tags).
        # Mehrzeiliger Text wird IMMER als Plain-Text behandelt
        # (wichtig für den Report mit Monospace-Spalten!).
        use_html = has_html_tags and not has_newlines and ("<a " in message or "<b>" in message)

        if self.selectable_text or self.show_copy_button:
            # ---------- Große Ansicht mit Auswahl + Kopieren ----------
            msg_container_widget = QWidget()
            msg_container_layout = QVBoxLayout(msg_container_widget)
            msg_container_layout.setContentsMargins(0, 0, 0, 0)
            msg_container_layout.setSpacing(5)

            if self.selectable_text:
                self.msg_edit = QTextEdit()

                if use_html:
                    fixed_message = self._fix_html_links(message)
                    self.msg_edit.setHtml(fixed_message)
                else:
                    # Plain-Text: Zeilenumbrüche bleiben erhalten.
                    self.msg_edit.setPlainText(message)

                self.msg_edit.setReadOnly(True)
                self.msg_edit.setObjectName("messageEdit")
                self.msg_edit.setFrameStyle(QFrame.NoFrame)
                self.msg_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.msg_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.msg_edit.setMinimumHeight(400)
                self.msg_edit.setLineWrapMode(QTextEdit.NoWrap)
                self.msg_edit.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
                )
                # Monospace-Schrift erzwingen (Menlo auf macOS)
                mono_font = QFont("Menlo", 11)
                mono_font.setStyleHint(QFont.Monospace)
                mono_font.setFixedPitch(True)
                self.msg_edit.setFont(mono_font)
                try:
                    self.msg_edit.setTabStopWidth(
                        4 * QFontMetrics(mono_font).width(" ")
                    )
                except Exception:
                    pass
                self.msg_edit.setStyleSheet("""
                    QTextEdit#messageEdit {
                        background-color: #000000;
                        color: #FFFFFF;
                        border: 1px solid #333333;
                        border-radius: 4px;
                        padding: 10px;
                        font-size: 12px;
                        font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
                        selection-background-color: #1565C0;
                        selection-color: #FFFFFF;
                    }
                """)
                msg_container_layout.addWidget(self.msg_edit)
            else:
                # Nur Kopier-Button, aber kein editierbarer Bereich
                if use_html:
                    fixed_message = self._fix_html_links(message)
                else:
                    fixed_message = message
                self.msg_label = QLabel(fixed_message)
                self.msg_label.setWordWrap(True)
                self.msg_label.setObjectName("messageLabel")
                self.msg_label.setTextFormat(
                    Qt.RichText if use_html else Qt.PlainText
                )
                self.msg_label.setOpenExternalLinks(use_html)
                self.msg_label.setStyleSheet("""
                    QLabel#messageLabel {
                        font-size: 16px;
                        padding: 15px;
                        color: #FFFFFF;
                        background-color: transparent;
                    }
                """)
                msg_container_layout.addWidget(self.msg_label)

            # ---------- Kopieren-Button ----------
            if self.show_copy_button:
                copy_btn = QPushButton("📋 Text kopieren")
                copy_btn.setObjectName("copyButton")
                copy_btn.setStyleSheet("""
                    QPushButton#copyButton {
                        background-color: #1565C0;
                        color: white;
                        border-radius: 4px;
                        padding: 5px 15px;
                        font-size: 12px;
                        max-width: 150px;
                    }
                    QPushButton#copyButton:hover { background-color: #0d47a1; }
                    QPushButton#copyButton:pressed { background-color: #0a3b8a; }
                """)
                copy_btn.clicked.connect(self._copy_text_to_clipboard)
                button_row = QHBoxLayout()
                button_row.addStretch()
                button_row.addWidget(copy_btn)
                msg_container_layout.addLayout(button_row)

            msg_layout.addWidget(msg_container_widget)
        else:
            # ---------- Einfacher Text (QLabel) ----------
            if use_html:
                fixed_message = self._fix_html_links(message)
            else:
                fixed_message = message
            self.msg_label = QLabel(fixed_message)
            self.msg_label.setWordWrap(True)
            self.msg_label.setObjectName("messageLabel")
            self.msg_label.setTextFormat(
                Qt.RichText if use_html else Qt.PlainText
            )
            self.msg_label.setOpenExternalLinks(use_html)
            self.msg_label.setStyleSheet("""
                QLabel#messageLabel {
                    font-size: 16px;
                    padding: 15px;
                    color: #FFFFFF;
                    background-color: transparent;
                }
            """)
            if self.text_alignment == Qt.AlignLeft:
                self.msg_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.msg_label.setIndent(5)
            else:
                self.msg_label.setAlignment(Qt.AlignCenter)
            msg_layout.addWidget(self.msg_label)

        # ---------- Input-Felder ----------
        if self.input_fields:
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet("background-color: #333333; margin: 10px 0px;")
            msg_layout.addWidget(separator)
            for field_config in self.input_fields:
                field_widget = self._create_input_field(field_config)
                msg_layout.addWidget(field_widget)

        scroll_area.setWidget(msg_container)
        main_layout.addWidget(scroll_area)

        # ---------- Buttonleiste ----------
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setSpacing(15)
        button_layout.setContentsMargins(10, 10, 10, 10)

        self.default_button_widget = None
        self.button_widgets = []

        button_defs = buttons if buttons is not None else self.buttons
        max_button_width = 0
        for button_def in button_defs:
            if len(button_def) >= 3:
                text = button_def[0]
                temp_btn = QPushButton(text)
                font = temp_btn.font()
                metrics = QFontMetrics(font)
                text_width = metrics.horizontalAdvance(text)
                padding = 50
                width = text_width + padding
                max_button_width = max(max_button_width, width)
        max_button_width = min(max_button_width, 400)
        max_button_width = max(max_button_width, 100)

        for i, button_def in enumerate(button_defs):
            if len(button_def) == 3:
                text, style_type, action = button_def
            elif len(button_def) == 4:
                text, style_type, action, min_width = button_def
            else:
                continue

            btn = QPushButton(text)
            btn.setProperty("action", action)
            self.button_widgets.append(btn)

            is_default = (self.default_button == action or
                          (i == 0 and not self.default_button))
            self.style_button(btn, style_type, (max_button_width, 40), is_default)
            # Wenn für diese Aktion ein Callback definiert ist, nutze den
            # (z. B. um einen Sub-Dialog zu öffnen, ohne den Dialog zu schließen)
            if action in self.action_callbacks:
                cb = self.action_callbacks[action]
                btn.clicked.connect(
                    lambda checked=False, fn=cb: fn()
                )
            else:
                btn.clicked.connect(
                    lambda checked, r=action: self.handle_button(r)
                )
            btn.setFocusPolicy(Qt.StrongFocus)
            button_layout.addWidget(btn)

            if is_default:
                self.default_button_widget = btn

        button_layout.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(button_widget)
        self.setLayout(main_layout)
        self.adjustSize()

    def init_button_style(self):
        self.button_styles = {
            'primary': {'bg': "#1565C0", 'hover': "#0d47a1"},
            'success': {'bg': "#2E7D32", 'hover': "#1B5E20"},
            'danger': {'bg': "#C62828", 'hover': "#8E0000"},
            'warning': {'bg': "#FF8a65", 'hover': "#F57C00"},
            'dark': {'bg': "#4a4a4a", 'hover': "#333333"}
        }

    def style_button(self, button, style_type, custom_size=None, is_default=False, min_width=None):
        style = self.button_styles.get(style_type, self.button_styles['primary'])
        focus_border = "3px solid #FFFFFF"
        focus_padding = "3px" if is_default else "1px"

        style_sheet = f"""
        QPushButton {{
            font-weight: bold;
            color: white;
            background-color: {style['bg']};
            border-radius: 10px;
            padding: 8px 16px;
            min-height: 20px;
            border: none;
            margin: 3px;
            font-size: 14px;
        }}
        QPushButton:hover {{ background-color: {style['hover']}; }}
        QPushButton:focus {{
            border: {focus_border};
            border-radius: 10px;
            background-color: {style['hover']};
            padding: {focus_padding};
        }}
        QPushButton:pressed {{
            background-color: {style['hover']};
            padding-top: 9px;
            padding-left: 9px;
        }}
        """
        button.setStyleSheet(style_sheet)
        if custom_size:
            button.setFixedWidth(custom_size[0])
            button.setFixedHeight(custom_size[1])
        else:
            font = button.font()
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(button.text())
            padding = 60
            width = max(100, min(text_width + padding, 500))
            button.setFixedWidth(width)
            button.setFixedHeight(40)

    def _create_input_field(self, field_config):
        field_type = field_config.get('type', 'text')
        label_text = field_config.get('label', '')
        field_name = field_config.get('name', f"field_{len(self.input_widgets)}")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(2)

        if label_text:
            label = QLabel(label_text)
            label.setStyleSheet(
                "font-weight: bold; margin-top: 2px; margin-bottom: 0px; "
                "font-size: 14px; "
                "color: #FFFFFF; background-color: transparent;"
            )
            layout.addWidget(label)

        if field_type == 'text':
            widget = QLineEdit()
            widget.setMinimumHeight(36)
            widget.setText(str(field_config.get('default', '')))
            placeholder = field_config.get('placeholder', '')
            if placeholder:
                widget.setPlaceholderText(placeholder)
            widget.setStyleSheet("""
                QLineEdit {
                    background-color: #1A1A1A;
                    color: #FFFFFF;
                    border: 2px solid #4FC3F7;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 16px;
                    min-height: 24px;
                }
                QLineEdit:focus {
                    border: 2px solid #FFFFFF;
                }
            """)
            layout.addWidget(widget)

        elif field_type == 'number':
            widget = QSpinBox()
            widget.setMinimum(field_config.get('min', -999999))
            widget.setMaximum(field_config.get('max', 999999))
            widget.setValue(int(field_config.get('default', 0)))
            layout.addWidget(widget)
        elif field_type == 'date':
            widget = QDateEdit()
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd.MM.yyyy")
            default = field_config.get('default', QDate.currentDate())
            if isinstance(default, str):
                default = QDate.fromString(default, "dd.MM.yyyy")
            widget.setDate(default)
            layout.addWidget(widget)
        elif field_type == 'combobox':
            widget = QComboBox()
            widget.setMinimumHeight(36)
            items = field_config.get('items', [])
            widget.addItems(items)
            default = field_config.get('default', None)
            if default is not None and default in items:
                widget.setCurrentText(default)
            elif items:
                widget.setCurrentIndex(0)
            widget.setStyleSheet("""
                QComboBox {
                    background-color: #1A1A1A;
                    color: #FFFFFF;
                    border: 2px solid #4FC3F7;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 16px;
                    min-height: 24px;
                }
                QComboBox:hover {
                    border: 2px solid #1565C0;
                    background-color: #222222;
                }
                QComboBox:focus {
                    border: 2px solid #4FC3F7;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 30px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 6px solid transparent;
                    border-right: 6px solid transparent;
                    border-top: 8px solid #FFFFFF;
                    width: 0;
                    height: 0;
                    margin-right: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: #1A1A1A;
                    color: #FFFFFF;
                    selection-background-color: #1565C0;
                    selection-color: #FFFFFF;
                    border: 1px solid #4FC3F7;
                    padding: 4px;
                }
            """)
            layout.addWidget(widget)
        else:
            widget = QLineEdit()

        self.input_widgets[field_name] = widget

        # ---- NEU: Callback bei Feldänderung verbinden ----
        cb = self.field_changed_callbacks.get(field_name)
        if cb:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(
                    lambda _text, _cb=cb, _w=widget: _cb(_w.text())
                )
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(
                    lambda _text, _cb=cb, _w=widget: _cb(_w.currentText())
                )
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(
                    lambda _val, _cb=cb, _w=widget: _cb(_w.value())
                )

        return container

    def _apply_ultimate_dark_mode(self):
        self._force_dark_palette()
        self._apply_high_priority_stylesheet()
        self._apply_dark_theme_recursive(self)
        self._ensure_critical_widgets_visible()
        self.setAttribute(Qt.WA_StyledBackground, True)

    def _force_dark_palette(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(0, 0, 0))
        dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Base, QColor(10, 10, 10))
        dark_palette.setColor(QPalette.AlternateBase, QColor(15, 15, 15))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
        dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Button, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Link, QColor(79, 195, 247))
        dark_palette.setColor(QPalette.LinkVisited, QColor(79, 195, 247))
        dark_palette.setColor(QPalette.Highlight, QColor(21, 101, 192))
        dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(dark_palette)

    def _apply_high_priority_stylesheet(self):
        self.setStyleSheet("""
            QDialog, QDialog * { background-color: #000000; color: #FFFFFF; }
            QLabel, QLabel * { color: #FFFFFF !important; background-color: transparent; font-size: 16px; }
            QLineEdit, QSpinBox, QDateEdit, QComboBox {
                background-color: #0A0A0A; color: #FFFFFF !important;
                border: 1px solid #333333; border-radius: 4px; padding: 5px;
                selection-background-color: #1565C0; selection-color: #FFFFFF; font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {
                border: 2px solid #1565C0;
            }
            QComboBox QAbstractItemView {
                background-color: #0A0A0A; color: #FFFFFF !important;
                selection-background-color: #1565C0; selection-color: #FFFFFF;
            }
            QTextEdit {
                background-color: #000000; color: #FFFFFF !important;
                border: 1px solid #333333; border-radius: 4px; padding: 5px;
                font-size: 14px;
            }
            QScrollArea, QScrollArea * { background-color: transparent; }
            QScrollBar:vertical { background: #0A0A0A; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background: #444444; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #666666; }
            QFrame, QFrame * { background-color: transparent; }
            * { color: #FFFFFF; }
        """)

    def _apply_dark_theme_recursive(self, widget):
        for child in widget.findChildren(QWidget):
            child.setPalette(self.palette())
            self._apply_dark_theme_recursive(child)

    def _ensure_critical_widgets_visible(self):
        for widget in self.input_widgets.values():
            if isinstance(widget, (QLineEdit, QSpinBox, QDateEdit, QComboBox)):
                widget.setStyleSheet(widget.styleSheet() + """
                    QLineEdit, QSpinBox, QDateEdit, QComboBox {
                        color: #FFFFFF !important;
                        background-color: #0A0A0A;
                        font-size: 16px;
                    }
                """)
        for button in self.button_widgets:
            button.setStyleSheet(button.styleSheet() + " QPushButton { color: #FFFFFF !important; }")

    @safe_slot
    def _copy_text_to_clipboard(self, _checked=False):
        """
        Kopiert den Text in die Zwischenablage.
        Bei sehr großem Text (> 50.000 Zeichen): Nachfrage + Busy-Dialog.
        """
        # Text-Ermittlung
        if self.msg_edit is not None:
            text_to_copy = self.msg_edit.toPlainText()
        elif self.msg_label is not None:
            text_to_copy = self.msg_label.text()
        else:
            text_to_copy = self.message

        if not text_to_copy:
            return

        total_len = len(text_to_copy)
        LARGE_THRESHOLD = 50000       # ab hier nachfragen
        PREVIEW_LEN = 5000            # Vorschau-Kopierlänge

        # ---------- Großer Text: Nachfrage ----------
        if total_len > LARGE_THRESHOLD:
            dialog = myUniversalDialog(
                self,
                "Sehr großer Text",
                f"Der Text hat <b>{total_len:,}</b> Zeichen.<br><br>"
                f"Das Kopieren des <b>gesamten</b> Textes kann ein paar "
                f"Sekunden dauern und die App kurz einfrieren.<br><br>"
                f"Möchtest du:<br>"
                f"&nbsp;&nbsp;• <b>Alles kopieren</b> ({total_len:,} Zeichen)<br>"
                f"&nbsp;&nbsp;• <b>Nur Anfang kopieren</b> "
                f"({PREVIEW_LEN:,} Zeichen)<br>"
                f"&nbsp;&nbsp;• <b>Abbrechen</b>",
                buttons=[
                    ("Alles kopieren", "warning", "all"),
                    ("Nur Anfang", "success", "preview"),
                    ("Abbrechen", "danger", "cancel"),
                ],
                icon_type="warning",
                text_alignment=Qt.AlignLeft,
            )
            dialog.exec_()
            result = dialog.result_value

            if result == "cancel" or result is None:
                return
            elif result == "preview":
                text_to_copy = text_to_copy[:PREVIEW_LEN]
                suffix = (f"\n\n… (gekürzt; Original: {total_len:,} Zeichen)"
                          f"\nVollständiger Bericht in der Datei.")
                text_to_copy += suffix
            # else: 'all' → ganze Länge verwenden

        # ---------- Kopieren mit Busy-Dialog bei großem Text ----------
        def do_copy():
            QApplication.clipboard().setText(text_to_copy)

        try:
            if len(text_to_copy) > 30000:
                # Busy-Dialog während des Kopierens
                busy = BusyDialog(self, "Kopiere Text in Zwischenablage")
                busy.show()
                QApplication.processEvents()
                try:
                    do_copy()
                finally:
                    busy.accept()
            else:
                do_copy()

            # Erfolgs-Feedback
            copied_len = len(text_to_copy)
            print(f"📋 {copied_len:,} Zeichen in die Zwischenablage kopiert.")
            self._show_copy_feedback(copied_len)

        except Exception as e:
            print(f"❌ Kopieren fehlgeschlagen: {e}")

    def _show_copy_feedback(self, length: int):
        """
        Zeigt ein dezentes Erfolgs-Feedback in der Statuszeile
        oder als temporären Hinweis.
        """
        # Wir nutzen den Titelbereich temporär als Info
        try:
            # Button-Text kurz ändern
            for btn in self.button_widgets:
                if btn.property("action") == "copy":
                    return
        except Exception:
            pass

        # Alternativ: Statuszeilen-Feedback
        # Da unser Dialog keine Statuszeile hat, nutzen wir
        # eine temporäre Änderung des Fenstertitels
        original_title = self.windowTitle()
        self.setWindowTitle(f"✅ {length:,} Zeichen kopiert — {original_title}")
        QTimer.singleShot(2500, lambda: self.setWindowTitle(original_title))

    def _fix_html_links(self, html_text):
        if not html_text or not ("<a " in html_text):
            return html_text

        def fix_link(match):
            full_tag = match.group(0)
            if 'href=' in full_tag:
                full_tag = re.sub(r'style="[^"]*"', '', full_tag)
                full_tag = full_tag.replace('>', ' style="color:#4FC3F7; text-decoration:underline;">')
                return full_tag
            else:
                content_match = re.search(r'<a[^>]*>(.*?)</a>', full_tag, re.DOTALL)
                if content_match:
                    link_text = content_match.group(1).strip()
                    if link_text and ('http' in link_text or 'www' in link_text):
                        return f'<a href="{link_text}" style="color:#4FC3F7; text-decoration:underline;">{link_text}</a>'
                return full_tag

        pattern = r'<a[^>]*>(.*?)</a>'
        return re.sub(pattern, fix_link, html_text, flags=re.DOTALL)

    def _handle_link_click(self, link):
        if link and link.toString():
            url = link.toString()
            if url.startswith("http") or url.startswith("https"):
                QDesktopServices.openUrl(QUrl(url))
            elif url.startswith("file:"):
                QDesktopServices.openUrl(QUrl(url))

    def _find_main_window(self, widget):
        if widget is None:
            return None
        current = widget
        while current is not None:
            if isinstance(current, QMainWindow) and hasattr(current, 'voice_enabled'):
                return current
            if hasattr(current, 'voice_enabled') and hasattr(current, 'page_changed'):
                return current
            try:
                parent = current.parent()
                if parent == current:
                    break
                current = parent
            except:
                break
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if isinstance(widget, QMainWindow) and hasattr(widget, 'voice_enabled'):
                    return widget
        return None

    def _get_voice_enabled(self):
        if self.main_window and hasattr(self.main_window, 'voice_enabled'):
            return self.main_window.voice_enabled
        return False

    def handle_button(self, action):
        if action in self.ACCEPT_ACTIONS and self.input_fields:
            collected_values = {}
            for name, widget in self.input_widgets.items():
                if isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QDateEdit):
                    value = widget.date().toString("dd.MM.yyyy")
                elif isinstance(widget, QComboBox):
                    value = widget.currentText()
                else:
                    value = None
                collected_values[name] = value
            self.input_values = collected_values

        self.result_value = action
        if action in self.REJECT_ACTIONS:
            self.reject()
        elif action in self.ACCEPT_ACTIONS:
            self.accept()
        else:
            self.accept()

    def get_input_values(self):
        return self.input_values

    def get_input_value(self, field_name):
        return self.input_values.get(field_name)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjust_dialog_height()
        self._position_dialog_top()  # NEU: Dialog oben platzieren
        if self.input_fields:
            QTimer.singleShot(100, self._select_all_text_in_first_input)
            QTimer.singleShot(150, self._scroll_to_input_fields)
            QTimer.singleShot(250, self._scroll_to_input_fields)

    def _scroll_to_input_fields(self):
        """
        Scrollt die Scroll-Area:
          • Bei <= 2 Input-Feldern: ans Ende (Eingabefeld soll sichtbar sein)
          • Bei > 2 Input-Feldern: an den Anfang (Settings-Übersicht)
        """
        scroll_area = self.findChild(QScrollArea)
        if not scroll_area:
            return
        scrollbar = scroll_area.verticalScrollBar()
        if not scrollbar:
            return

        if len(self.input_fields) > 2:
            # Settings-Dialog: oben starten
            scrollbar.setValue(0)
        else:
            # Ein-/Zwei-Feld-Dialog: Eingabefeld sichtbar machen
            scrollbar.setValue(scrollbar.maximum())

    def _select_all_text_in_first_input(self):
        if self.input_widgets:
            first_widget = list(self.input_widgets.values())[0]
            if isinstance(first_widget, QLineEdit):
                first_widget.setFocus()
                first_widget.selectAll()
            elif isinstance(first_widget, QSpinBox):
                first_widget.setFocus()
                first_widget.selectAll()
            elif isinstance(first_widget, QDateEdit):
                first_widget.setFocus()
                first_widget.lineEdit().selectAll()

    def exec_(self):
        result = super().exec_()
        if result == QDialog.Accepted and self.result_value in self.REJECT_ACTIONS:
            return QDialog.Rejected
        return result

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            self.closed.emit()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            current_focused = self.focusWidget()
            if isinstance(current_focused, (QLineEdit, QSpinBox, QDateEdit)):
                if len(self.input_widgets) > 1:
                    input_widgets_list = list(self.input_widgets.values())
                    if current_focused in input_widgets_list:
                        current_index = input_widgets_list.index(current_focused)
                        if current_index == len(input_widgets_list) - 1:
                            if self.default_button_widget:
                                self.default_button_widget.click()
                            elif self.button_widgets:
                                self.button_widgets[0].click()
                        else:
                            next_widget = input_widgets_list[current_index + 1]
                            next_widget.setFocus()
                else:
                    if self.default_button_widget:
                        self.default_button_widget.click()
                    elif self.button_widgets:
                        self.button_widgets[0].click()
            elif current_focused in self.button_widgets:
                current_focused.click()
            elif self.default_button_widget:
                self.default_button_widget.click()
            elif self.button_widgets:
                self.button_widgets[0].click()
        else:
            super().keyPressEvent(event)

    # def adjust_dialog_height(self):
    #     """Berechnet die Dialoghöhe inkl. Input-Feldern dynamisch."""
    #     # Text-Höhe bestimmen (kurz gemessen)
    #     temp_label = QLabel(self.message)
    #     temp_label.setWordWrap(True)
    #     temp_label.setTextFormat(Qt.RichText)
    #     available_width = max(self.width() - 80, 300)
    #     temp_label.resize(available_width, 10000)
    #     text_height = temp_label.heightForWidth(available_width)
    #     temp_label.deleteLater()

    #     # Feste Bereiche
    #     header_height = 55       # Titelzeile
    #     icon_height = 55 if self.icon_type and self.icon_type != "" else 0
    #     button_height = 65       # Buttonleiste

    #     # Container-Inhalt
    #     if self.selectable_text or self.show_copy_button:
    #         content_height = 400  # QTextEdit
    #     else:
    #         content_height = text_height + 20  # Label

    #     # Input-Felder: pro Feld 80px (Label + Feld + Abstand)
    #     input_fields_height = len(self.input_fields) * 80
    #     if self.input_fields:
    #         content_height += 40  # Separator + Abstand
    #         content_height += input_fields_height

    #     scroll_padding = 30  # Padding der Scroll-Area

    #     total_height = (
    #         header_height
    #         + icon_height
    #         + content_height
    #         + scroll_padding
    #         + button_height
    #     )

    #     screen = QApplication.primaryScreen().availableGeometry()
    #     min_height = 500
    #     max_height = int(screen.height() * 0.9)
    #     final_height = max(min_height, min(int(total_height), max_height))
    #     self.setMinimumHeight(final_height)
    #     self.setFixedHeight(final_height)

    def adjust_dialog_height(self):
        """
        Berechnet die Dialoghöhe dynamisch anhand des Inhalts.
        Kurze Dialoge werden klein, lange bekommen bis zu 80 % Bildschirmhöhe.
        """
        # ---------- Text-Höhe ----------
        temp_label = QLabel(self.message)
        temp_label.setWordWrap(True)
        temp_label.setTextFormat(Qt.RichText if "<" in self.message else Qt.PlainText)
        available_width = max(self.width() - 80, 300)
        temp_label.resize(available_width, 10000)
        text_height = temp_label.heightForWidth(available_width)
        temp_label.deleteLater()

        # ---------- Feste Bereiche ----------
        header_height = 55
        icon_height = 80 if self.icon_type and self.icon_type != "" else 0
        button_height = 70

        # ---------- Inhalts-Höhe ----------
        # Grundhöhe (Titel + Text + Padding)
        content_height = text_height + 30

        # Input-Felder: pro Feld ca. 85px (Label + Feld + Abstand)
        if self.input_fields:
            content_height += 30  # Separator
            content_height += len(self.input_fields) * 75

        # Große Ansicht mit QTextEdit: Mindestens 250px, maximal 500px
        if self.selectable_text:
            content_height = max(content_height, 320)
            content_height = min(content_height, 500)

        # ---------- Gesamthöhe ----------
        total_height = (
            header_height
            + icon_height
            + content_height
            + 40  # Scroll-Padding
            + button_height
        )

        # ---------- Grenzen ----------
        screen = QApplication.primaryScreen().availableGeometry()
        min_height = 250
        max_height = int(screen.height() * 0.8)
        final_height = max(min_height, min(int(total_height), max_height))

        self.setMinimumHeight(final_height)
        self.setMaximumHeight(max_height)
        self.resize(self.width(), final_height)

    def _position_dialog_top(self):
        """
        Positioniert den Dialog oben auf dem Bildschirm, mit etwas Abstand
        zum oberen Rand. So bleiben die Buttons immer sichtbar, auch wenn
        die Taskleiste/Dock am unteren Rand ist.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        geo = self.frameGeometry()
        # Horizontal zentriert, vertikal mit 40px Abstand von oben
        x = screen.left() + (screen.width() - geo.width()) // 2
        y = screen.top() + 40
        # Sicherstellen, dass der Dialog nicht über den unteren Rand hinausragt
        if y + geo.height() > screen.bottom():
            y = max(screen.top() + 10, screen.bottom() - geo.height() - 20)
        self.move(x, y)

    def reject(self):
        if self.result_value is None:
            self.result_value = 'cancel'
        super().reject()
        self.closed.emit()


### ============================================================
### BENUTZERVERWALTUNG
### ============================================================

class UserManager:
    """
    Verwaltet GitHub-Benutzernamen persistent in einer JSON-Datei.
    """

    def __init__(self, users_file: Path = None):
        self.users_file = users_file or (APP_PATHS["settings"] / USERS_FILE)
        self.users: List[str] = []
        self.last_user: str = ""
        self._load()

    def _load(self):
        if self.users_file.exists():
            try:
                with open(self.users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.users = list(dict.fromkeys(data.get("users", [])))
                    self.last_user = data.get("last_user", "")
                logger.debug(f"UserManager: {len(self.users)} Benutzer geladen")
            except Exception:
                logger.exception("Benutzerdatei konnte nicht geladen werden")
                print(f"⚠️  Benutzerdatei konnte nicht geladen werden")

    def _save(self):
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"users": self.users, "last_user": self.last_user},
                    f, indent=2, ensure_ascii=False
                )
            logger.debug(f"UserManager gespeichert: {self.users}")

        except Exception:
            logger.exception("Benutzerdatei konnte nicht gespeichert werden")
            print(f"⚠️  Benutzerdatei konnte nicht gespeichert werden")

    def add_user(self, username: str, make_current: bool = True):
        username = (username or "").strip()
        if not username:
            return
        if username not in self.users:
            self.users.append(username)
        if make_current:
            self.last_user = username
        self._save()

    def remove_user(self, username: str):
        if username in self.users:
            self.users.remove(username)
        if self.last_user == username:
            self.last_user = self.users[-1] if self.users else ""
        self._save()

    def set_current(self, username: str):
        if username in self.users:
            self.last_user = username
            self._save()

    def has_users(self) -> bool:
        return len(self.users) > 0

    def get_users(self) -> List[str]:
        return list(self.users)

    def get_current(self) -> str:
        return self.last_user

def check_github_user_exists(username: str) -> Tuple[bool, str]:
    """
    Prüft, ob ein GitHub-Benutzer existiert.
    Rückgabe: (existiert_bool, fehler_string)
    fehler_string ist leer, wenn API erreichbar war.
    """
    try:
        url = f"https://api.github.com/users/{username}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return (True, "")
        elif response.status_code == 404:
            return (False, "")
        elif response.status_code == 403:
            return (True, "GitHub Rate-Limit")
        else:
            return (True, f"HTTP {response.status_code}")
    except Exception as e:
        return (True, f"Netzwerkfehler: {e}")

def get_rate_limit_status(token: str = "") -> Optional[dict]:
    """
    Fragt bei GitHub das aktuelle Rate-Limit ab.
    Rückgabe: Dict mit 'remaining', 'limit', 'reset' oder None bei Fehler.
    """
    try:
        url = "https://api.github.com/rate_limit"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("rate", {})
    except Exception:
        pass
    return None


### ============================================================
### TOKEN-VERWALTUNG (pro Benutzer)
### ============================================================

TOKENS_FILE = "github_tokens.json"

class TokenManager:
    """
    Verwaltet GitHub Personal Access Tokens, gekoppelt an Benutzernamen.

    Speichert in github_tokens.json:
    {
      "tokens": {
        "BinhDiez": {"token": "ghp_…", "saved_at": "2026-01-15T12:34:56"},
        "Jason":    {"token": "ghp_…", "saved_at": "2026-01-16T09:00:00"}
      }
    }

    ACHTUNG: Klartext-Speicherung! Datei liegt neben dem Skript.
    """

    def __init__(self, tokens_file: Path = None):
        self.tokens_file = tokens_file or (APP_PATHS["settings"] / TOKENS_FILE)
        self.tokens: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.tokens_file.exists():
            try:
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tokens = data.get("tokens", {}) or {}
                logger.debug(f"TokenManager: {len(self.tokens)} Tokens geladen")
            except Exception:
                logger.exception("Token-Datei konnte nicht geladen werden")
                print(f"⚠️  Token-Datei konnte nicht geladen werden")

    def _save(self):
        try:
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump({"tokens": self.tokens}, f, indent=2, ensure_ascii=False)
            # Datei nur für Besitzer lesbar
            try:
                os.chmod(self.tokens_file, 0o600)
            except Exception:
                pass
        except Exception:
            print(f"⚠️  Token-Datei konnte nicht gespeichert werden")
            logger.exception(f"⚠️  Token-Datei konnte nicht gespeichert werden")

    def get_token(self, username: str) -> str:
        entry = self.tokens.get(username)
        if entry and isinstance(entry, dict):
            return entry.get("token", "")
        return ""

    def has_token(self, username: str) -> bool:
        return bool(self.get_token(username))

    def set_token(self, username: str, token: str):
        if not username:
            return
        token = token.strip()
        if not token:
            self.remove_token(username)
            return
        self.tokens[username] = {
            "token": token,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save()

    def remove_token(self, username: str):
        if username in self.tokens:
            del self.tokens[username]
            self._save()
            logger.debug(f"Token gelöscht für '{username}'")

    def get_saved_at(self, username: str) -> str:
        entry = self.tokens.get(username)
        if entry and isinstance(entry, dict):
            return entry.get("saved_at", "")
        return ""

def check_token_valid(token: str) -> Tuple[bool, str, str]:
    """
    Prüft einen GitHub-Token live.

    Rückgabe: (ist_gueltig, benutzername, fehlermeldung)
      - ist_gueltig=True,  benutzername="…", fehlermeldung=""
      - ist_gueltig=False, benutzername="",  fehlermeldung="401 Unauthorized"
    """
    if not token:
        return (False, "", "Leerer Token")

    try:
        url = "https://api.github.com/user"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector",
            "Authorization": f"Bearer {token}",
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return (True, data.get("login", ""), "")
        elif response.status_code == 401:
            return (False, "", "401 Unauthorized – Token ungültig oder abgelaufen")
        elif response.status_code == 403:
            # Kann bei manchen Token-Scopes vorkommen – Token ist aber gültig
            return (True, "", "403 – Scope reicht evtl. nicht aus")
        else:
            return (False, "", f"HTTP {response.status_code}")
    except Exception as e:
        # Bei Netzwerkfehler: Token als gültig annehmen (nicht löschen!)
        return (True, "", f"Netzwerkfehler: {e}")


### ============================================================
### GitHub API CLIENT
### ============================================================

class GitHubStatsCollector:
    """Sammelt Statistiken von der GitHub API für ein einzelnes Repository"""

    def __init__(self, config: Config, repo_name: str = None):
        self.config = config
        self.repo_name = repo_name or config.owner
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        if config.token:
            self.headers["Authorization"] = f"Bearer {config.token}"

        self.base_url = "https://api.github.com"
        self.repo_url = f"{self.base_url}/repos/{config.owner}/{self.repo_name}"

        self.releases = []
        self.total_downloads = 0
        self.platform_stats = {
            "windows": 0,
            "mac_intel": 0,
            "mac_arm": 0,
            "linux": 0,
            "android": 0,
            "bsd": 0,
            "other": 0,
        }
        self.assets = []
        self.page_views = None
        self.traffic_data = None
        self.clone_data = None
        self.contributors = []
        self.stars = 0
        self.forks = 0
        self.watchers = 0
        self.repo_info = None
        self.error = None
        self.rate_limited = False

    def fetch_all_pages(self, url: str) -> List[dict]:
        all_data = []
        current_url = url
        while current_url:
            try:
                logger.debug(f"  → GET {current_url}")
                response = requests.get(current_url, headers=self.headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                logger.debug(
                    f"  ← {response.status_code} "
                    f"({len(data) if isinstance(data, list) else 'obj'} items)"
                )
                if isinstance(data, list):
                    all_data.extend(data)
                elif isinstance(data, dict):
                    all_data.append(data)
                current_url = response.links.get("next", {}).get("url")

            except requests.exceptions.RequestException as e:
                logger.debug(f"  ✗ Fehler: {e}")
                err_str = str(e).lower()
                # Rate-Limit erkennen
                if "rate limit" in err_str or "403" in err_str or "429" in err_str:
                    self.rate_limited = True
                    if self.config.verbose:
                        print(f"  ⚠️  Rate-Limit erreicht bei {current_url}")
                else:
                    logger.debug(f"  Fehler beim Abrufen von {current_url}: {e}")
                    if self.config.verbose:
                        print(f"  Fehler beim Abrufen von {current_url}: {e}")
                break
        return all_data

    def fetch_releases(self):
        url = f"{self.repo_url}/releases"
        self.releases = self.fetch_all_pages(url)

        for release in self.releases:
            for asset in release.get("assets", []):
                count = asset["download_count"]
                self.total_downloads += count
                platform = classify_platform(asset["name"])
                # Fallback für neue Plattform-Kategorien
                if platform not in self.platform_stats:
                    platform = "other"
                self.platform_stats[platform] += count
                self.assets.append((count, asset["name"]))
        self.assets.sort(reverse=True)

    def fetch_page_views(self):
        if not self.config.token:
            return
        try:
            url = f"{self.repo_url}/traffic/views"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.page_views = {
                    "count": data.get("count", 0),
                    "uniques": data.get("uniques", 0),
                    "views": data.get("views", [])
                }
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Seitenaufrufen für {self.repo_name}: {e}")

    def fetch_traffic(self):
        if not self.config.token or not self.config.include_traffic:
            return
        try:
            url = f"{self.repo_url}/traffic/popular/referrers"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                self.traffic_data = response.json()
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Traffic für {self.repo_name}: {e}")

    def fetch_clones(self):
        if not self.config.token or not self.config.include_clones:
            return
        try:
            url = f"{self.repo_url}/traffic/clones"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.clone_data = {
                    "count": data.get("count", 0),
                    "uniques": data.get("uniques", 0),
                    "clones": data.get("clones", [])
                }
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Clones für {self.repo_name}: {e}")

    def fetch_repository_metadata(self):
        try:
            response = requests.get(self.repo_url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.repo_info = data
                self.stars = data.get("stargazers_count", 0)
                self.forks = data.get("forks_count", 0)
                self.watchers = data.get("watchers_count", 0)

            if self.config.include_contributors:
                url = f"{self.repo_url}/contributors"
                self.contributors = self.fetch_all_pages(url)
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Metadaten für {self.repo_name}: {e}")

    def collect_all(self):
        try:
            self.fetch_releases()
            self.fetch_repository_metadata()
            if self.config.include_page_views:
                self.fetch_page_views()
            if self.config.include_clones:
                self.fetch_clones()
            if self.config.include_traffic:
                self.fetch_traffic()

            if self.rate_limited and self.config.verbose:
                print(f"⚠️  {self.repo_name}: Daten unvollständig (Rate-Limit)")
        except Exception as e:
            self.error = str(e)
            logger.exception(
                f"Fehler beim Sammeln der Stats für '{self.repo_name}'"
            )
            if self.config.verbose:
                print(f"❌ Fehler bei {self.repo_name}: {e}")

    @property
    def has_releases(self) -> bool:
        return len(self.releases) > 0

    @property
    def description(self) -> str:
        if self.repo_info:
            return self.repo_info.get("description", "") or ""
        return ""

    @property
    def language(self) -> str:
        if self.repo_info:
            return self.repo_info.get("language", "") or ""
        return ""

    @property
    def is_fork(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("fork", False)
        return False

    @property
    def is_archived(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("archived", False)
        return False

    @property
    def is_private(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("private", False)
        return False

    @property
    def html_url(self) -> str:
        if self.repo_info:
            return self.repo_info.get("html_url", f"https://github.com/{self.config.owner}/{self.repo_name}")
        return f"https://github.com/{self.config.owner}/{self.repo_name}"


### ============================================================
### MULTI-REPO-COLLECTOR
### ============================================================

class MultiRepoCollector:
    """Sammelt Statistiken für ALLE Repositories eines Benutzers"""

    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        if config.token:
            self.headers["Authorization"] = f"Bearer {config.token}"

        self.base_url = "https://api.github.com"
        self.repositories = []
        self.collectors: Dict[str, GitHubStatsCollector] = {}
        self.repo_metadata: Dict[str, dict] = {}

        self.followers = []
        self.followers_detailed = []
        self.following_count = 0
        self.followers_count = 0
        self.user_info = None
        self.rate_limited = False

    def _check_rate_limit(self, err_str: str) -> bool:
        """Prüft, ob ein Fehler ein Rate-Limit-Fehler ist."""
        s = err_str.lower()
        return "rate limit" in s or "403" in s or "429" in s

    def _print_rate_limit_hint(self):
        print("")
        print("=" * 60)
        print("⚠️  GITHUB RATE LIMIT ERREICHT!")
        print("=" * 60)
        print("Ohne Token: nur 60 Anfragen/Stunde.")
        print("→ Bitte GitHub Personal Access Token verwenden:")
        print("   https://github.com/settings/tokens")
        print("→ Aufruf mit:  --token ghp_xxxxxxxxxxxx")
        print("=" * 60)
        print("")

    def fetch_user_repositories(self) -> List[dict]:
        if self.config.verbose:
            print(f"🔍 Sammle Repository-Liste für Benutzer: {self.config.owner}...")

        all_repos = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/users/{self.config.owner}/repos"
            params = {
                "per_page": per_page,
                "page": page,
                "sort": "updated",
                "direction": "desc"
            }
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                if response.status_code == 404:
                    print(f"❌ Benutzer '{self.config.owner}' nicht gefunden!")
                    break
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_repos.extend(data)
                logger.debug(f"  Repo-Seite {page}: {len(data)} Einträge "
                             f"(gesamt: {len(all_repos)})")
                if self.config.verbose:
                    print(f"  Seite {page}: {len(data)} Repos gefunden (gesamt: {len(all_repos)})")

                if len(data) < per_page:
                    break
                page += 1

            except requests.exceptions.RequestException as e:
                err_str = str(e)
                if self._check_rate_limit(err_str):
                    self._print_rate_limit_hint()
                    self.rate_limited = True
                else:
                    print(f"❌ Fehler beim Abrufen der Repo-Liste: {e}")
                break

        return all_repos

    def fetch_user_info(self):
        if self.config.verbose:
            print(f"👤 Sammle Benutzer-Info für: {self.config.owner}...")

        try:
            url = f"{self.base_url}/users/{self.config.owner}"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                self.user_info = response.json()
                self.followers_count = self.user_info.get("followers", 0)
                self.following_count = self.user_info.get("following", 0)
                if self.config.verbose:
                    print(f"  Follower:  {self.followers_count:,}")
                    print(f"  Following: {self.following_count:,}")
            elif response.status_code == 404:
                print(f"❌ Benutzer '{self.config.owner}' existiert nicht auf GitHub!")
            elif response.status_code == 403:
                self._print_rate_limit_hint()
                self.rate_limited = True
        except Exception as e:
            if self._check_rate_limit(str(e)):
                # Rate-Limit ist ein erwartbarer Zustand — kein Traceback
                logger.warning(
                    f"Rate-Limit in fetch_user_info(): {e}"
                )
                self._print_rate_limit_hint()
                self.rate_limited = True
            else:
                # Unerwarteter Fehler → Traceback
                logger.exception(
                    f"Fehler beim Abrufen der Benutzer-Info für "
                    f"'{self.config.owner}'"
                )
                print(f"❌ Fehler beim Abrufen der Benutzer-Info: {e}")

    def fetch_followers(self):
        if not self.config.include_followers:
            return

        if self.config.verbose:
            print(f"👥 Sammle Follower-Liste für: {self.config.owner}...")

        all_followers = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/users/{self.config.owner}/followers"
            params = {"per_page": per_page, "page": page}
            try:
                response = requests.get(url, headers=self.headers,
                                        params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_followers.extend(data)
                logger.debug(f"  Follower-Seite {page}: {len(data)} Einträge "
                             f"(gesamt: {len(all_followers)})")
                if self.config.verbose:
                    print(f"  Seite {page}: {len(data)} Follower "
                        f"(gesamt: {len(all_followers)})")

                if len(data) < per_page:
                    break
                page += 1

            except requests.exceptions.RequestException as e:
                err_str = str(e)
                if self._check_rate_limit(err_str):
                    self._print_rate_limit_hint()
                    self.rate_limited = True
                else:
                    print(f"❌ Fehler beim Abrufen der Follower: {e}")
                break

        self.followers = all_followers
        if self.config.verbose:
            print(f"✅ {len(self.followers)} Follower gesammelt")

    def enrich_followers(self, progress_cb=None):
        """
        Reichert Follower mit Detail-Infos an.

        progress_cb: Optionaler Callback, der pro Follower aufgerufen wird.
                     Signatur: progress_cb(current, total, login, success)
        """
        if not self.config.followers_detail or not self.followers:
            return

        if self.config.verbose:
            print(f"🔎 Lade Details für {len(self.followers)} Follower...")

        detailed = []
        total = len(self.followers)
        failed = 0

        for i, follower in enumerate(self.followers, 1):
            login = follower.get("login")
            if not login:
                continue

            success = False
            try:
                url = f"{self.base_url}/users/{login}"
                response = requests.get(url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    detailed.append({
                        "login": data.get("login", login),
                        "name": data.get("name", "") or "",
                        "location": (data.get("location", "") or "").strip(),
                        "company": (data.get("company", "") or "").strip(),
                        "bio": (data.get("bio", "") or "").strip(),
                        "blog": (data.get("blog", "") or "").strip(),
                        "public_repos": data.get("public_repos", 0),
                        "followers": data.get("followers", 0),
                        "following": data.get("following", 0),
                        "created_at": data.get("created_at", ""),
                        "html_url": data.get("html_url", ""),
                    })
                    success = True
                elif response.status_code == 403:
                    # Rate-Limit → abbrechen
                    self.rate_limited = True
                    if self.config.verbose:
                        print(f"  ⚠️  Rate-Limit erreicht bei Follower {login}")
                    break

                # Sanfte Pause alle 10 Requests
                if i % 10 == 0:
                    import time
                    time.sleep(0.5)

                if self.config.verbose and i % 50 == 0:
                    print(f"  {i}/{total} Follower angereichert...")

            except Exception as e:
                failed += 1
                if self.config.verbose:
                    print(f"  ⚠️  Fehler bei {login}: {e}")

            # Progress-Callback
            if progress_cb:
                try:
                    progress_cb(i, total, login, success)
                except Exception:
                    pass

        self.followers_detailed = detailed
        if self.config.verbose:
            print(f"✅ {len(detailed)} Follower mit Details angereichert "
                  f"({failed} Fehler)")

    def filter_repositories(self, repos: List[dict]) -> List[dict]:
        logger.debug(f"Filter: {len(repos)} Repos eingelesen")
        filtered = []
        regex = None
        if self.config.repo_filter:
            try:
                regex = re.compile(self.config.repo_filter, re.IGNORECASE)
            except re.error as e:
                print(f"⚠️  Ungültiger Regex-Filter: {e}")

        for repo in repos:
            name = repo.get("name", "")

            if self.config.skip_forks and repo.get("fork", False):
                logger.debug(f"  ⏭️  Fork: {name}")
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe Fork: {name}")
                continue

            if self.config.skip_archived and repo.get("archived", False):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe archiviert: {name}")
                continue

            if self.config.skip_private and repo.get("private", False):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe privat: {name}")
                continue

            if regex and not regex.search(name):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe (Filter): {name}")
                continue

            filtered.append(repo)

        logger.debug(f"Filter: {len(filtered)} von {len(repos)} Repos bleiben")
        return filtered

    def collect_all(self):
        self.fetch_user_info()

        # Bei Rate-Limit sofort abbrechen
        if self.rate_limited:
            return

        self.fetch_followers()
        if self.rate_limited:
            return

        self.enrich_followers()

        all_repos = self.fetch_user_repositories()

        if self.rate_limited:
            return

        if not all_repos:
            print("")
            print("❌ Keine Repositories gefunden!")
            print("   Mögliche Ursachen:")
            print("   • GitHub Rate Limit erreicht (60/Std. ohne Token)")
            print("   • Benutzername falsch oder keine Repos vorhanden")
            print("   • Kein Internet")
            print("")
            return

        filtered_repos = self.filter_repositories(all_repos)

        print(f"📦 {len(filtered_repos)} von {len(all_repos)} Repositories werden analysiert...")
        print("")

        for i, repo in enumerate(filtered_repos, 1):
            repo_name = repo["name"]
            self.repo_metadata[repo_name] = repo

            if self.config.verbose:
                print(f"[{i}/{len(filtered_repos)}] Analysiere: {repo_name}")

            collector = GitHubStatsCollector(self.config, repo_name)
            collector.collect_all()

            if self.config.only_with_releases and not collector.has_releases:
                if self.config.verbose:
                    print(f"  ⏭️  Keine Releases, übersprungen")
                continue

            self.collectors[repo_name] = collector
            self.repositories.append(repo_name)

        if self.config.verbose:
            print("")
            print(f"✅ Analyse abgeschlossen: {len(self.collectors)} Repositories mit Daten")

    def get_total_stats(self) -> dict:
        total_downloads = 0
        total_stars = 0
        total_forks = 0
        total_watchers = 0
        total_releases = 0
        total_assets = 0
        total_views = 0
        total_unique_views = 0
        total_clones = 0
        total_unique_clones = 0
        platform_totals = {
            "windows": 0,
            "mac_intel": 0,
            "mac_arm": 0,
            "linux": 0,
            "android": 0,
            "bsd": 0,
            "other": 0,
        }

        for collector in self.collectors.values():
            total_downloads += collector.total_downloads
            total_stars += collector.stars
            total_forks += collector.forks
            total_watchers += collector.watchers
            total_releases += len(collector.releases)
            total_assets += len(collector.assets)

            for key in platform_totals:
                platform_totals[key] += collector.platform_stats.get(key, 0)

            if collector.page_views:
                total_views += collector.page_views.get("count", 0)
                total_unique_views += collector.page_views.get("uniques", 0)

            if collector.clone_data:
                total_clones += collector.clone_data.get("count", 0)
                total_unique_clones += collector.clone_data.get("uniques", 0)

        return {
            "repos_analyzed": len(self.collectors),
            "total_downloads": total_downloads,
            "total_stars": total_stars,
            "total_forks": total_forks,
            "total_watchers": total_watchers,
            "total_releases": total_releases,
            "total_assets": total_assets,
            "total_views": total_views,
            "total_unique_views": total_unique_views,
            "total_clones": total_clones,
            "total_unique_clones": total_unique_clones,
            "platform_totals": platform_totals,
        }


### ============================================================
### Worker-Thread für die Analyse mit Fortschrittsmeldungen
### ============================================================

class AnalysisWorker(QThread):
    """
    Führt die komplette GitHub-Analyse in einem eigenen Thread aus,
    damit die UI nicht einfriert.
    """

    # Signale
    progress = _pyqt_signal(int, int)          # (aktuell, gesamt)
    status = _pyqt_signal(str)                 # Statuszeile (Haupttext)
    log = _pyqt_signal(str)                    # Log-Zeile (append)
    finished_ok = _pyqt_signal(object, object) # (multi_collector, report_text)
    finished_err = _pyqt_signal(str, str)      # (plain_text, html_text)
    cancelled = _pyqt_signal()               # bei Benutzer-Abbruch

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _check_cancel(self) -> bool:
        if self._cancelled:
            self.cancelled.emit()
            return True
        return False

    def run(self):
        """Wird im eigenen Thread ausgeführt."""
        try:
            self.status.emit(f"Lade Benutzer-Informationen für {self.config.owner}…")
            self.log.emit(f"👤 Benutzer: {self.config.owner}")

            multi = MultiRepoCollector(self.config)

            # ---------- Benutzer-Info ----------
            if self._check_cancel(): return
            multi.fetch_user_info()
            if multi.rate_limited:
                self._emit_error(
                    plain="Rate-Limit erreicht beim Abrufen der Benutzer-Info.",
                    html="<b>Rate-Limit erreicht</b> beim Abrufen der "
                         "Benutzer-Info.<br><br>Bitte einen GitHub-Token "
                         "verwenden oder später erneut versuchen."
                )
                return
            self.log.emit(
                f"📊 Follower: {multi.followers_count:,} | "
                f"Following: {multi.following_count:,}"
            )

            # ---------- Follower ----------
            if self.config.include_followers:
                self.status.emit("Lade Follower-Liste…")
                if self._check_cancel(): return
                multi.fetch_followers()
                if multi.rate_limited:
                    self._emit_error(
                        plain="Rate-Limit erreicht beim Abrufen der Follower.",
                        html="<b>Rate-Limit erreicht</b> beim Abrufen der "
                             "Follower.<br><br>Bitte einen GitHub-Token "
                             "verwenden."
                    )
                    return
                self.log.emit(f"👥 {len(multi.followers)} Follower geladen")

                if self.config.followers_detail and multi.followers:
                    total_f = len(multi.followers)
                    self.status.emit(f"Reichere {total_f} Follower an…")
                    self.log.emit(f"🔎 Lade Details für {total_f} Follower…")

                    last_logged = {"i": 0}

                    def on_follower_progress(current, total, login, success):
                        if current - last_logged["i"] >= 10 or current == total:
                            last_logged["i"] = current
                            self.log.emit(
                                f"  … {current}/{total} Follower "
                                f"({login})"
                            )

                    multi.enrich_followers(progress_cb=on_follower_progress)

                    if multi.rate_limited:
                        self._emit_error(
                            plain=(
                                f"Rate-Limit erreicht während der "
                                f"Follower-Anreicherung. Nur "
                                f"{len(multi.followers_detailed)} von "
                                f"{total_f} Followern konnten geladen werden."
                            ),
                            html=(
                                f"<b>Rate-Limit erreicht</b> während der "
                                f"Follower-Anreicherung.<br><br>"
                                f"Nur <b>{len(multi.followers_detailed)} von "
                                f"{total_f}</b> Followern konnten geladen "
                                f"werden.<br><br>Bitte einen GitHub-Token "
                                f"verwenden."
                            )
                        )
                        return

                    self.log.emit(
                        f"✅ {len(multi.followers_detailed)} Follower "
                        f"detailliert"
                    )

            # ---------- Repo-Liste ----------
            self.status.emit("Lade Repository-Liste…")
            if self._check_cancel(): return
            all_repos = multi.fetch_user_repositories()
            if multi.rate_limited:
                self._emit_error(
                    plain="Rate-Limit erreicht beim Abrufen der Repo-Liste.",
                    html="<b>Rate-Limit erreicht</b> beim Abrufen der "
                         "Repository-Liste.<br><br>Bitte einen GitHub-Token "
                         "verwenden."
                )
                return

            # Fall A: User hat wirklich KEINE Repos
            if not all_repos:
                self._emit_error(
                    plain=(
                        f"Für '{self.config.owner}' wurden keine Repositories "
                        f"auf GitHub gefunden."
                    ),
                    html=(
                        f"Für den Benutzer <b>'{self.config.owner}'</b> wurden "
                        f"keine Repositories auf GitHub gefunden.<br><br>"
                        f"<b>Mögliche Ursachen:</b><br>"
                        f"&nbsp;&nbsp;• Der Benutzer hat keine öffentlichen "
                        f"Repositories<br>"
                        f"&nbsp;&nbsp;• Der Token hat keinen Zugriff auf "
                        f"private Repos (Scope <code>repo</code> nötig)<br>"
                        f"&nbsp;&nbsp;• Der Benutzername ist falsch geschrieben"
                    )
                )
                return

            # ---------- Filter anwenden ----------
            filtered_repos = multi.filter_repositories(all_repos)
            total = len(filtered_repos)
            total_all = len(all_repos)

            # Fall B: Repos da, aber alle rausgefiltert
            if total == 0:
                reasons = []
                if self.config.skip_archived:
                    reasons.append("Archivierte Repos sind ausgeschlossen "
                                   "(skip_archived = true)")
                if self.config.skip_forks:
                    reasons.append("Forks sind ausgeschlossen "
                                   "(skip_forks = true)")
                if self.config.skip_private:
                    reasons.append("Private Repos sind ausgeschlossen "
                                   "(skip_private = true)")
                if self.config.only_with_releases:
                    reasons.append("Nur Repos mit Releases "
                                   "(only_with_releases = true)")
                if self.config.repo_filter:
                    reasons.append(f"Regex-Filter aktiv: "
                                   f"'{self.config.repo_filter}'")

                # ---- Plain-Text (für Log) ----
                plain_lines = [
                    f"Für '{self.config.owner}' wurden {total_all} "
                    f"Repositories gefunden,",
                    f"aber ALLE durch die aktuellen Filter ausgeschlossen:",
                    "",
                ]
                for r in reasons:
                    plain_lines.append(f"  • {r}")
                plain_lines.append("")
                plain_lines.append(
                    "Tipp: In 'github_stats_config.json' anpassen:"
                )
                plain_lines.append("  • \"skip_archived\": false")
                plain_lines.append("  • \"skip_forks\": false")
                plain_lines.append("  • \"only_with_releases\": false")
                plain_text = "\n".join(plain_lines)

                # ---- HTML (für show_error_dialog) ----
                html_lines = [
                    f"Für den Benutzer <b>'{self.config.owner}'</b> wurden "
                    f"<b>{total_all}</b> Repositories gefunden,<br>"
                    f"aber <b>keines</b> konnte analysiert werden.",
                    "",
                    "<b>Aktive Filter:</b>",
                ]
                for r in reasons:
                    html_lines.append(f"&nbsp;&nbsp;• {r}")
                html_lines.append("")
                html_lines.append("<b>Tipp:</b> In der Datei "
                                  "<code>github_stats_config.json</code> "
                                  "können die Filter angepasst werden:")
                html_lines.append(
                    "&nbsp;&nbsp;<code>\"skip_archived\": false</code>"
                )
                html_lines.append(
                    "&nbsp;&nbsp;<code>\"skip_forks\": false</code>"
                )
                html_lines.append(
                    "&nbsp;&nbsp;<code>\"only_with_releases\": false</code>"
                )
                html_text = "<br>".join(html_lines)

                self._emit_error(plain=plain_text, html=html_text)
                return

            # ---------- Analyse starten ----------
            self.log.emit(
                f"📦 {total} von {total_all} Repos werden analysiert"
            )
            self.progress.emit(0, total)

            for i, repo in enumerate(filtered_repos, 1):
                if self._check_cancel(): return

                repo_name = repo["name"]
                multi.repo_metadata[repo_name] = repo

                self.status.emit(f"Analysiere {repo_name} ({i}/{total})…")
                self.progress.emit(i - 1, total)

                collector = GitHubStatsCollector(self.config, repo_name)
                logger.debug(f"── [{i}/{total}] {repo_name}")
                collector.collect_all()
                logger.debug(
                    f"   {len(collector.releases)} Releases, "
                    f"{collector.total_downloads:,} Downloads, "
                    f"{collector.stars} Stars, "
                    f"{len(collector.contributors)} Contributors")
                if self.config.only_with_releases and not collector.has_releases:
                    self.log.emit(f"⏭️  {repo_name} (keine Releases)")
                    self.progress.emit(i, total)
                    continue

                multi.collectors[repo_name] = collector
                multi.repositories.append(repo_name)

                dl = collector.total_downloads
                if collector.rate_limited:
                    self.log.emit(f"⚠️  {repo_name} ({dl:,} Downloads, "
                                  f"UNVOLLSTÄNDIG – Rate-Limit)")
                    multi.rate_limited = True  # global markieren
                elif dl > 0:
                    self.log.emit(f"✅ {repo_name} ({dl:,} Downloads)")
                else:
                    self.log.emit(f"✅ {repo_name}")

                self.progress.emit(i, total)

            # ---------- Bericht generieren ----------
            self.status.emit("Erstelle Bericht…")
            self.log.emit("📝 Bericht wird erstellt…")

            if multi.rate_limited:
                self.log.emit("")
                self.log.emit("⚠️  ACHTUNG: Mindestens ein Repo war von "
                              "Rate-Limit betroffen.")
                self.log.emit("   Die Zahlen können UNVOLLSTÄNDIG sein!")
                self.log.emit("   → Bitte GitHub-Token verwenden.")

            report = MultiRepoReportGenerator(multi)
            report.generate_report()
            report_text = report.get_report_text()

            self.status.emit("Fertig ✓")
            self.finished_ok.emit(multi, report_text)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.exception(f"Unerwarteter Fehler im AnalysisWorker: {e}")
            self._emit_error(
                plain=f"Unerwarteter Fehler: {e}\n\n{tb}",
                html=f"<b>Unerwarteter Fehler:</b><br><br>"
                     f"<code>{e}</code><br><br>"
                     f"Details siehe Logdatei."
            )
            import traceback
            tb = traceback.format_exc()
            self._emit_error(
                plain=f"Unerwarteter Fehler: {e}\n\n{tb}",
                html=f"<b>Unerwarteter Fehler:</b><br><br>"
                     f"<code>{e}</code><br><br>"
                     f"Details siehe Konsole / Log."
            )

    def _emit_error(self, plain: str, html: str):
        """Sendet Fehler sowohl als Plain-Text als auch als HTML."""
        # In den Log (Plain-Text – gut lesbar)
        for line in plain.split("\n"):
            self.log.emit(line)
        # An den Dialog (HTML für show_error_dialog)
        self.finished_err.emit(plain, html)


### ============================================================
### FORTSCHRITTSANZEIGE
### ============================================================

class AnalysisProgressDialog(QDialog):
    """
    Zeigt den Fortschritt der Analyse an, mit Log-Ausgabe und
    Abbrechen-Button. Arbeitet mit einem AnalysisWorker-Thread.
    """

    def __init__(self, parent, config: Config):
        super().__init__(parent)
        self.config = config
        self.worker = None
        self.cancelled = False
        self.result_multi = None
        self.result_report_text = None
        self.error_message = None
        self.error_message_plain = None
        self.error_message_html = None

        self.setWindowTitle("GitHub-Analyse läuft…")
        self.setModal(True)
        self.setMinimumSize(750, 480)
        self.setStyleSheet("""
            QDialog { background-color: #000000; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background-color: transparent; }
            QLabel#titleLabel { font-size: 20px; font-weight: bold; }
            QLabel#statusLabel { font-size: 15px; padding: 4px; }
            QProgressBar {
                border: 1px solid #333333;
                border-radius: 6px;
                text-align: center;
                background-color: #0A0A0A;
                color: #FFFFFF;
                min-height: 22px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #1565C0;
                border-radius: 5px;
            }
            QTextEdit {
                background-color: #000000;
                color: #FFFFFF;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
            }
            QPushButton {
                background-color: #C62828;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 14px;
                border: none;
                min-width: 140px;
                min-height: 36px;
            }
            QPushButton:hover { background-color: #8E0000; }
            QPushButton:disabled { background-color: #333333; color: #888888; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Titel
        title = QLabel("📊 GitHub-Analyse läuft…")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Status-Zeile
        self.status_label = QLabel("Starte…")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress-Bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # Log-Bereich
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, 1)

        # Abbrechen-Button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Fenster-Schließen abfangen
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )

    def start(self, worker: AnalysisWorker):
        self.worker = worker
        worker.progress.connect(self._on_progress)
        worker.status.connect(self._on_status)
        worker.log.connect(self._on_log)
        worker.finished_ok.connect(self._on_finished_ok)
        worker.finished_err.connect(self._on_finished_err)
        worker.cancelled.connect(self._on_cancelled)
        worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            pct = int(current / total * 100)
            self.progress.setValue(pct)
        else:
            self.progress.setValue(0)

    def _on_status(self, text: str):
        self.status_label.setText(text)

    def _on_log(self, text: str):
        self.log_edit.append(text)
        # Auto-Scroll ans Ende
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    @safe_slot
    def _on_finished_ok(self, multi, report_text):
        self.result_multi = multi
        self.result_report_text = report_text
        self.progress.setValue(100)
        self.accept()

    @safe_slot
    def _on_finished_err(self, plain: str, html: str):
        self.error_message_plain = plain
        self.error_message_html = html
        self.error_message = html  # Fallback: HTML anzeigen
        self.status_label.setText("❌ Fehler – Dialog wird geschlossen…")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Bitte warten…")
        QTimer.singleShot(1200, self.reject)

    def _on_cancelled(self):
        self.cancelled = True
        self.reject()

    @safe_slot
    def _on_cancel(self, _checked=False):
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Wird abgebrochen…")
        self._on_log("⏹️  Abbruch angefordert – warte auf aktuelles Repo…")
        if self.worker:
            self.worker.cancel()

    def closeEvent(self, event):
        # Schließen-Kreuz blockieren, solange Analyse läuft
        if self.worker and self.worker.isRunning():
            event.ignore()
            self._on_cancel()
        else:
            event.accept()


# ============================================================
# WARTEDIALOG (Feedback beim Token-Check)
# ============================================================

class BusyDialog(QDialog):
    """
    Kleiner Warte-Dialog mit animiertem Punkt-Spinner.
    Wird während kurzer synchroner Operationen (Token-Check,
    Benutzer-Existenz-Check) angezeigt.
    """

    def __init__(self, parent, text: str = "Bitte warten…"):
        super().__init__(parent)
        self.setWindowTitle("Bitte warten…")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet("""
            QDialog { background-color: #000000; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background-color: transparent;
                     font-size: 15px; }
        """)

        # Fenster-Rahmen ohne Schließen-Knopf
        self.setWindowFlags(
            Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        self.icon_label = QLabel("⏳")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet(
            "font-size: 42px; background: transparent;"
        )
        layout.addWidget(self.icon_label)

        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        # Punkt-Animation
        self._dot_state = 0
        self._base_text = text
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(300)

    def _animate(self):
        self._dot_state = (self._dot_state + 1) % 4
        dots = "." * self._dot_state
        self.text_label.setText(f"{self._base_text}{dots}")

    def closeEvent(self, event):
        # Esc / Schließen-Kreuz blockieren
        event.ignore()

    def keyPressEvent(self, event):
        # Esc blockieren
        if event.key() == Qt.Key_Escape:
            event.ignore()
        else:
            super().keyPressEvent(event)

def run_with_busy_dialog(parent, text: str, func):
    """
    Führt `func()` synchron aus, während ein BusyDialog angezeigt wird.
    Rückgabe: das Ergebnis von `func()`.
    """
    busy = BusyDialog(parent, text)

    # Dialog zeigen, dann kurz warten, damit er sichtbar wird,
    # dann die eigentliche (blockierende) Operation ausführen.
    def do_work():
        busy.accept()

    busy.show()
    QApplication.processEvents()

    try:
        result = func()
    finally:
        busy.accept()

    return result


### ============================================================
### Multi-Repo Report Generator
### ============================================================

class MultiRepoReportGenerator:
    """Erstellt einen übersichtlichen Bericht für alle Repositories"""

    def __init__(self, multi_collector: MultiRepoCollector):
        self.multi = multi_collector
        self.lines = []

    def add_line(self, line: str = ""):
        self.lines.append(line)

    def add_section(self, title: str, char: str = "=", width: int = 80):
        self.lines.append(char * width)
        self.lines.append(title)
        self.lines.append(char * width)
        self.lines.append("")

    def generate_report(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        config = self.multi.config

        self.add_section("📊 GitHub Multi-Repository Statistik")
        self.add_line(f"Benutzer:    {config.owner}")
        self.add_line(f"Erstellt:    {now}")
        self.add_line(f"Repos:       {len(self.multi.collectors)} analysiert")
        self.add_line("")

        self._add_followers_overview()
        self._add_overview()
        self._add_repo_ranking()

        self.add_section("📋 DETAILS PRO REPOSITORY", "=")
        self.add_line("")

        sorted_repos = sorted(
            self.multi.collectors.items(),
            key=lambda x: x[1].total_downloads,
            reverse=True
        )

        for i, (repo_name, collector) in enumerate(sorted_repos, 1):
            self._add_repo_details(repo_name, collector, i)

        self.add_section("📈 Ende der Statistik")

    def _add_overview(self):
        self.add_section("🌍 GESAMTÜBERSICHT", "-")

        stats = self.multi.get_total_stats()

        self.add_line(f"{'Metrik':<30} {'Wert':>15}")
        self.add_line("-" * 47)
        self.add_line(f"{'Analysierte Repositories':<30} {stats['repos_analyzed']:>15,}")
        self.add_line(f"{'Gesamt Downloads':<30} {stats['total_downloads']:>15,}")
        self.add_line(f"{'Gesamt Releases':<30} {stats['total_releases']:>15,}")
        self.add_line(f"{'Gesamt Assets':<30} {stats['total_assets']:>15,}")
        self.add_line(f"{'Gesamt Stars':<30} {stats['total_stars']:>15,}")
        self.add_line(f"{'Gesamt Forks':<30} {stats['total_forks']:>15,}")
        self.add_line(f"{'Gesamt Watchers':<30} {stats['total_watchers']:>15,}")

        if self.multi.config.include_page_views and stats['total_views'] > 0:
            self.add_line(f"{'Seitenaufrufe (14 Tage)':<30} {stats['total_views']:>15,}")
            self.add_line(f"{'Einzigartige Besucher':<30} {stats['total_unique_views']:>15,}")

        if self.multi.config.include_clones and stats['total_clones'] > 0:
            self.add_line(f"{'Clones (14 Tage)':<30} {stats['total_clones']:>15,}")
            self.add_line(f"{'Einzigartige Cloner':<30} {stats['total_unique_clones']:>15,}")

        self.add_line("")

        platform = stats['platform_totals']
        total_platform = sum(platform.values())

        if total_platform > 0:
            self.add_line("💻 Plattform-Verteilung (Gesamt):")
            self.add_line(f"{'Plattform':<25} {'Downloads':>12} {'Anteil':>8}")
            self.add_line("-" * 47)

            labels = {
                "windows": "Windows",
                "mac_intel": "macOS Intel",
                "mac_arm": "macOS Apple Silicon",
                "linux": "Linux",
                "android": "Android",
                "bsd": "BSD",
                "other": "Sonstige"
            }
            for key, label in labels.items():
                count = platform.get(key, 0)
                pct = (count / total_platform * 100) if total_platform > 0 else 0
                self.add_line(f"{label:<25} {count:>12,} {pct:>7.1f}%")

            self.add_line("")

    def _add_repo_ranking(self):
        self.add_section("🏆 REPOSITORY-RANKING (nach Downloads)", "-")

        sorted_repos = sorted(
            self.multi.collectors.items(),
            key=lambda x: x[1].total_downloads,
            reverse=True
        )

        self.add_line(f"{'#':<4} {'Repository':<30} {'Downloads':>12} {'Stars':>8} {'Releases':>9}")
        self.add_line("-" * 66)

        for i, (repo_name, collector) in enumerate(sorted_repos[:30], 1):
            self.add_line(
                f"{i:<4} {repo_name[:30]:<30} "
                f"{collector.total_downloads:>12,} "
                f"{collector.stars:>8,} "
                f"{len(collector.releases):>9}"
            )

        if len(sorted_repos) > 30:
            self.add_line(f"... und {len(sorted_repos) - 30} weitere Repositories")

        self.add_line("")
        self._add_language_distribution()

    def _add_language_distribution(self):
        languages = {}
        for repo_name, collector in self.multi.collectors.items():
            lang = collector.language or "Unbekannt"
            if lang not in languages:
                languages[lang] = {"count": 0, "downloads": 0, "stars": 0}
            languages[lang]["count"] += 1
            languages[lang]["downloads"] += collector.total_downloads
            languages[lang]["stars"] += collector.stars

        if not languages:
            return

        self.add_section("💻 SPRACH-VERTEILUNG", "-")
        self.add_line(f"{'Sprache':<20} {'Repos':>8} {'Downloads':>12} {'Stars':>8}")
        self.add_line("-" * 52)

        sorted_langs = sorted(
            languages.items(),
            key=lambda x: x[1]["downloads"],
            reverse=True
        )
        for lang, data in sorted_langs:
            self.add_line(
                f"{lang[:20]:<20} {data['count']:>8} "
                f"{data['downloads']:>12,} {data['stars']:>8,}"
            )
        self.add_line("")

    def _add_repo_details(self, repo_name: str, collector: GitHubStatsCollector, index: int):
        separator = f"═══ [{index}] {repo_name} ═══"
        self.add_line(separator)
        self.add_line("")

        if collector.description:
            self.add_line(f"📝 {collector.description[:100]}")
            self.add_line("")

        self.add_line(f"🔗 URL:        {collector.html_url}")
        if collector.language:
            self.add_line(f"💻 Sprache:    {collector.language}")
        self.add_line(f"⭐ Stars:      {collector.stars:,}")
        self.add_line(f"🍴 Forks:      {collector.forks:,}")
        self.add_line(f"👁️  Watchers:   {collector.watchers:,}")
        self.add_line(f"📦 Releases:   {len(collector.releases)}")
        self.add_line(f"📥 Downloads:  {collector.total_downloads:,}")
        self.add_line("")

        if collector.releases:
            self._add_repo_releases(collector)
        else:
            self.add_line("⚠️  Keine Releases vorhanden.")
            self.add_line("")

        if collector.total_downloads > 0:
            self._add_repo_platforms(collector)

        if collector.assets:
            self._add_repo_top_assets(collector)

        if collector.page_views:
            self._add_repo_page_views(collector)

        if collector.clone_data:
            self._add_repo_clones(collector)

        if collector.traffic_data:
            self._add_repo_traffic(collector)

        if collector.contributors:
            self._add_repo_contributors(collector)

        self.add_line("")

    def _add_repo_releases(self, collector: GitHubStatsCollector):
        self.add_line("  📦 Release-Details:")
        now = datetime.now(timezone.utc)

        for release in collector.releases[:10]:
            release_name = release.get("name") or release["tag_name"]
            tag_name = release["tag_name"]
            published = release.get("published_at", "")
            release_total = 0

            for asset in release.get("assets", []):
                release_total += asset["download_count"]

            release_date = parse_iso_safe(published)
            if release_date:
                age_days = max((now - release_date).days, 1)
            else:
                age_days = 1

            dl_per_day = release_total / age_days
            date_short = published[:10] if published else "?"

            self.add_line(f"    • {release_name[:40]:<40} ({tag_name})")
            self.add_line(f"      Datum: {date_short}  |  Downloads: {release_total:,}  |  {dl_per_day:.2f}/Tag")

            if release.get("assets"):
                top_assets = sorted(
                    release["assets"],
                    key=lambda a: a["download_count"],
                    reverse=True
                )[:3]
                for asset in top_assets:
                    self.add_line(
                        f"        - {asset['download_count']:>8,}  {asset['name']}"
                    )

        if len(collector.releases) > 10:
            self.add_line(f"    ... und {len(collector.releases) - 10} weitere Releases")

        self.add_line("")

    def _add_repo_platforms(self, collector: GitHubStatsCollector):
        stats = collector.platform_stats
        total = sum(stats.values())

        if total == 0:
            return

        self.add_line("  💻 Plattform-Verteilung:")
        labels = {
            "windows": "Windows",
            "mac_intel": "macOS Intel",
            "mac_arm": "macOS ARM",
            "linux": "Linux",
            "android": "Android",
            "bsd": "BSD",
            "other": "Sonstige"
        }
        for key, label in labels.items():
            count = stats.get(key, 0)
            if count > 0:
                pct = (count / total * 100)
                bar = "█" * int(pct / 5)
                self.add_line(f"    {label:<15} {count:>8,}  {pct:>5.1f}%  {bar}")
        self.add_line("")

    def _add_repo_top_assets(self, collector: GitHubStatsCollector):
        self.add_line("  🏆 Top Assets:")
        for count, name in collector.assets[:5]:
            self.add_line(f"    {count:>8,}  {name}")
        self.add_line("")

    def _add_repo_page_views(self, collector: GitHubStatsCollector):
        views = collector.page_views
        self.add_line(f"  👁️  Seitenaufrufe (14 Tage): {views['count']:,} "
                      f"(unique: {views['uniques']:,})")

        if views.get("views"):
            recent = views["views"][-7:]
            self.add_line("    Letzte Tage:")
            for day in recent:
                date = day["timestamp"][:10]
                bar = "█" * min(day["count"] // 5, 40)
                self.add_line(f"      {date}  {day['count']:>5}  {bar}")
        self.add_line("")

    def _add_repo_clones(self, collector: GitHubStatsCollector):
        clones = collector.clone_data
        self.add_line(f"  📦 Clones (14 Tage): {clones['count']:,} "
                      f"(unique: {clones['uniques']:,})")
        self.add_line("")

    def _add_repo_traffic(self, collector: GitHubStatsCollector):
        if not collector.traffic_data:
            return
        self.add_line("  🔗 Top Referrer:")
        for ref in collector.traffic_data[:5]:
            name = ref["referrer"] or "Direkt"
            self.add_line(
                f"    {name[:35]:<35} {ref['count']:>6} views"
            )
        self.add_line("")

    def _add_repo_contributors(self, collector: GitHubStatsCollector):
        self.add_line(f"  👥 Contributors ({len(collector.contributors)}):")
        for contrib in collector.contributors[:5]:
            name = contrib.get("login", "?")
            commits = contrib.get("contributions", 0)
            self.add_line(f"    {name[:30]:<30} {commits:>5} commits")
        if len(collector.contributors) > 5:
            self.add_line(f"    ... und {len(collector.contributors) - 5} weitere")
        self.add_line("")

    def get_report_text(self) -> str:
        return "\n".join(self.lines)

    def save(self, output_file: str) -> Path:
        outfile = Path(output_file)
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(self.get_report_text())
        return outfile

    def _add_followers_overview(self):
        multi = self.multi
        config = multi.config

        if not config.include_followers:
            return

        self.add_section("👥 FOLLOWER-ANALYSE", "-")

        followers_count = multi.followers_count or len(multi.followers)
        following_count = multi.following_count

        ratio = (followers_count / following_count) if following_count > 0 else 0

        self.add_line(f"{'Metrik':<30} {'Wert':>15}")
        self.add_line("-" * 47)
        self.add_line(f"{'Follower':<30} {followers_count:>15,}")
        self.add_line(f"{'Following':<30} {following_count:>15,}")
        self.add_line(f"{'Follower/Following-Ratio':<30} {ratio:>15.2f}")
        self.add_line("")

        if not multi.followers_detailed:
            if multi.followers:
                self.add_line("Basis-Follower-Liste (ohne Detail-Infos):")
                self.add_line(f"  (Detail-Abfrage war "
                              f"{'aktiviert, aber fehlgeschlagen' if config.followers_detail else 'deaktiviert'})")
                self.add_line("")
                for f in multi.followers[:20]:
                    self.add_line(f"  • {f.get('login', '?')}")
                if len(multi.followers) > 20:
                    self.add_line(f"  ... und {len(multi.followers) - 20} weitere")
                self.add_line("")
            return

        detailed = multi.followers_detailed
        self._add_followers_by_location(detailed)
        self._add_followers_by_company(detailed)
        self._add_top_followers(detailed)
        self._add_followers_by_account_age(detailed)
        self._add_followers_list(detailed)

    def _add_followers_by_location(self, detailed):
        self.add_line("🌍 Follower nach Ort (Freitext-Feld):")

        locations = {}
        without_location = 0

        for f in detailed:
            loc = f["location"]
            if not loc:
                without_location += 1
                continue
            normalized = loc.split(",")[0].strip().title()
            locations[normalized] = locations.get(normalized, 0) + 1

        if not locations:
            self.add_line("  Keine Ortsangaben vorhanden.")
            self.add_line("")
            return

        sorted_locs = sorted(locations.items(), key=lambda x: x[1], reverse=True)

        self.add_line(f"  {'Ort':<35} {'Anzahl':>8}")
        self.add_line("  " + "-" * 45)
        for loc, count in sorted_locs[:20]:
            bar = "█" * min(count, 30)
            self.add_line(f"  {loc[:35]:<35} {count:>8}  {bar}")

        if len(sorted_locs) > 20:
            self.add_line(f"  ... und {len(sorted_locs) - 20} weitere Orte")

        if without_location > 0:
            self.add_line(f"  (ohne Ortsangabe: {without_location})")
        self.add_line("")

        self.add_line("  ℹ️  Hinweis: location ist ein Freitext-Feld und "
                    "daher ungenau/nicht standardisiert.")
        self.add_line("")

    def _add_followers_by_company(self, detailed):
        companies = {}
        for f in detailed:
            comp = f["company"]
            if not comp:
                continue
            normalized = comp.lstrip("@").strip()
            companies[normalized] = companies.get(normalized, 0) + 1

        if not companies:
            return

        self.add_line("🏢 Top-Unternehmen/Organisationen:")
        sorted_companies = sorted(companies.items(),
                                key=lambda x: x[1], reverse=True)

        for comp, count in sorted_companies[:15]:
            self.add_line(f"  {comp[:40]:<40} {count:>5}")
        self.add_line("")

    def _add_top_followers(self, detailed):
        if not detailed:
            return

        self.add_line("⭐ Top-Follower (nach eigenen Followern):")
        self.add_line(f"  {'#':<4} {'Login':<25} {'Follower':>10} {'Repos':>7} {'Ort'}")
        self.add_line("  " + "-" * 75)

        sorted_followers = sorted(detailed,
                                key=lambda x: x["followers"],
                                reverse=True)

        for i, f in enumerate(sorted_followers[:20], 1):
            login = f["login"][:25]
            followers = f["followers"]
            repos = f["public_repos"]
            loc = f["location"][:25] if f["location"] else "—"
            self.add_line(
                f"  {i:<4} {login:<25} {followers:>10,} {repos:>7} {loc}"
            )
        self.add_line("")

    def _add_followers_by_account_age(self, detailed):
        if not detailed:
            return

        now = datetime.now(timezone.utc)
        buckets = {
            "< 1 Jahr": 0,
            "1-3 Jahre": 0,
            "3-5 Jahre": 0,
            "5-10 Jahre": 0,
            "> 10 Jahre": 0,
            "Unbekannt": 0,
        }

        for f in detailed:
            created = f.get("created_at", "")
            if not created:
                buckets["Unbekannt"] += 1
                continue
            created_dt = parse_iso_safe(created)
            if created_dt is None:
                buckets["Unbekannt"] += 1
                continue

            age_days = (now - created_dt).days
            age_years = age_days / 365.25

            if age_years < 1:
                buckets["< 1 Jahr"] += 1
            elif age_years < 3:
                buckets["1-3 Jahre"] += 1
            elif age_years < 5:
                buckets["3-5 Jahre"] += 1
            elif age_years < 10:
                buckets["5-10 Jahre"] += 1
            else:
                buckets["> 10 Jahre"] += 1

        total = sum(buckets.values())
        if total == 0:
            return

        self.add_line("📅 Follower nach Account-Alter:")
        for bucket, count in buckets.items():
            if count == 0:
                continue
            pct = (count / total * 100)
            bar = "█" * int(pct / 3)
            self.add_line(f"  {bucket:<15} {count:>5}  {pct:>5.1f}%  {bar}")
        self.add_line("")

        # ===== Bonus: Jüngste und älteste Follower =====
        with_date = [
            (f, parse_iso_safe(f.get("created_at", "")))
            for f in detailed
        ]
        with_date = [(f, dt) for f, dt in with_date if dt is not None]

        if with_date:
            with_date.sort(key=lambda x: x[1])
            self.add_line("📅 Jüngste Follower-Accounts:")
            for f, dt in with_date[:5]:
                age_days = (now - dt).days
                self.add_line(
                    f"  {f['login'][:30]:<30} seit {dt.strftime('%Y-%m-%d')} "
                    f"({age_days} Tage)"
                )
            self.add_line("")

    def _add_followers_list(self, detailed):
        if not detailed:
            return

        self.add_line(f"📋 Alle Follower ({len(detailed)}):")
        self.add_line(
            f"  {'Login':<25} {'Name':<25} {'Ort':<20} {'Followers':>9}"
        )
        self.add_line("  " + "-" * 82)

        for f in sorted(detailed, key=lambda x: x["login"].lower()):
            login = f["login"][:25]
            name = (f["name"] or "—")[:25]
            loc = (f["location"] or "—")[:20]
            followers = f["followers"]
            self.add_line(
                f"  {login:<25} {name:<25} {loc:<20} {followers:>9,}"
            )
        self.add_line("")


# ============================================================
# DIALOG Wrapper (benutzen alles darüber)
# ============================================================

def ask_save_location(config) -> Optional[Path]:
    """
    Bestimmt, wo die Datei gespeichert wird.

    - Wenn output_file ein absoluter Pfad ist → diesen nutzen
    - Wenn config.save_location gesetzt → nutzen ohne zu fragen
    - Wenn kein Dialog erlaubt → Statistics-Ordner
    - Sonst: Dialog mit 2 Optionen + Merk-Option
    """
    raw = Path(config.output_file)
    if raw.is_absolute():
        return raw.parent

    statistics_dir = APP_PATHS["statistics"]
    downloads_dir = get_downloads_dir()

    # Gespeicherten Ort verwenden (ohne Nachfrage)
    # "script" ist der alte Wert → wird als "statistics" interpretiert
    # (Rückwärtskompatibilität für bestehende JSON-Dateien)
    if config.save_location in ("statistics", "script"):
        return statistics_dir
    if config.save_location == "downloads":
        return downloads_dir

    # Kein Dialog → Default = Statistics-Ordner
    if not config.show_dialog:
        return statistics_dir

    # Dialog anzeigen
    info_html = (
        "<div style='text-align:left; font-size:14px; line-height:1.5;'>"

        "<p style='margin-bottom:12px;'>"
        "Wählen Sie den Speicherort für den Bericht:"
        "</p>"

        "<div style='margin-bottom:12px;'>"
        "  <b>📊 Statistik-Ordner</b> (empfohlen)<br>"
        f"  <span style='color:#4FC3F7; font-family:monospace;'>"
        f"{statistics_dir}</span>"
        "</div>"

        "<div style='margin-bottom:12px;'>"
        "  <b>⬇ Downloads-Ordner</b><br>"
        f"  <span style='color:#4FC3F7; font-family:monospace;'>"
        f"{downloads_dir}</span>"
        "</div>"

        "<hr style='border:none; border-top:1px solid #333; margin:10px 0;'>"

        "<div style='color:#B0B0B0; font-size:12px;'>"
        "  <b>Dateiname</b>: <code>" + raw.name + "</code><br>"
        "  <b>Tipp</b>: Einmal wählen und merken – jederzeit änderbar in "
        "<code>settings/github_stats_config.json</code> → "
        "<code>\"save_location\": \"statistics\"</code> oder "
        "<code>\"downloads\"</code>."
        "</div>"

        "</div>"
    )

    dialog = myUniversalDialog(
        None,
        "Speicherort wählen",
        info_html,
        buttons=[
            ("Statistik-Ordner", "primary", "statistics"),
            ("Downloads-Ordner", "success", "downloads"),
            ("Abbrechen", "danger", "cancel"),
        ],
        icon_type="",
        text_alignment=Qt.AlignLeft,
        input_fields=[{
            "type": "combobox",
            "name": "remember",
            "label": "Für zukünftige Starts merken?",
            "items": [
                "Nein, jedes Mal fragen",
                "Ja, Auswahl merken",
            ],
            "default": "Ja, Auswahl merken",
        }],
        default_button="statistics",
    )
    dialog.exec_()

    result = dialog.result_value

    if result in ("cancel", None):
        return None

    # Merken?
    remember_val = dialog.get_input_value("remember") or ""
    remember = remember_val.startswith("Ja")

    if result == "downloads":
        target = downloads_dir
        chosen = "downloads"
    else:  # "statistics"
        target = statistics_dir
        chosen = "statistics"

    if remember:
        config.save_location = chosen
        config.save_to_file()

    return target

def ask_username_dialog(parent=None, initial: str = "",
                        title: str = "GitHub-Benutzer",
                        message: str = "Bitte GitHub-Benutzernamen eingeben:",
                        config: "Config" = None
                        ) -> Optional[str]:
    """
    Zeigt einen Dialog zur Eingabe eines GitHub-Benutzernamens.
    Mit Validierung + Einstellungen.
    """
    info_html = (
        "<div style='text-align:left; font-size:14px; line-height:1.6;'>"
        f"<p>{message}</p>"
        "<p style='color:#B0B0B0; font-size:12px;'>"
        "Der Name wird <b>live gegen GitHub geprüft</b>.<br>"
        "Bitte vollständig eingeben, nicht nur einzelne Buchstaben.<br>"
        "Beispiel: <code>BinhDiez</code>"
        "</p>"
        "</div>"
    )

    while True:
        dialog = myUniversalDialog(
            parent,
            title,
            info_html,
            buttons=add_settings_button([
                ("OK", "primary", "accept"),
                ("Abbrechen", "danger", "cancel"),
            ]),
            icon_type="",
            text_alignment=Qt.AlignLeft,
            input_fields=[{
                "type": "text",
                "name": "username",
                "label": "GitHub-Benutzername:",
                "default": initial,
                "placeholder": "z.B. BinhDiez",
            }],
            default_button="accept",
        )
        dialog.exec_()
        result = dialog.result_value

        if result == "settings":
            if config is not None:
                saved = show_settings_dialog(parent, config)
                if saved:
                    show_confirm_dialog(
                        parent,
                        "Einstellungen gespeichert",
                        "Die Einstellungen wurden gespeichert.",
                        config=None  # kein weiterer Settings-Button
                    )
            continue

        if result != "accept":
            return None

        val = (dialog.get_input_value("username") or "").strip()

        # --- Validierung ---
        if len(val) < 2:
            show_error_dialog(
                parent,
                "Ungültiger Benutzername",
                f"Der eingegebene Name <b>'{val}'</b> ist zu kurz.<br><br>"
                "GitHub-Benutzernamen haben mindestens 2 Zeichen.<br>"
                "Bitte erneut versuchen."
            )
            initial = val
            continue

        if not re.match(r'^[A-Za-z0-9\-]+$', val):
            show_error_dialog(
                parent,
                "Ungültiger Benutzername",
                f"Der Name <b>'{val}'</b> enthält ungültige Zeichen.<br><br>"
                "GitHub-Benutzernamen dürfen nur Buchstaben, Zahlen und "
                "Bindestriche enthalten."
            )
            initial = val
            continue

        exists, api_error = run_with_busy_dialog(
            parent,
            f"Prüfe Benutzer '{val}' bei GitHub",
            lambda v=val: check_github_user_exists(v)
        )
        if api_error:
            reply = show_confirm_dialog(
                parent,
                "GitHub nicht erreichbar",
                f"Der Benutzer <b>'{val}'</b> konnte nicht live geprüft "
                f"werden ({api_error}).<br><br>"
                "Möchten Sie trotzdem mit diesem Namen fortfahren?",
                config=config
            )
            if not reply:
                initial = val
                continue
        elif not exists:
            show_error_dialog(
                parent,
                "Benutzer nicht gefunden",
                f"Der GitHub-Benutzer <b>'{val}'</b> existiert nicht.<br><br>"
                "Bitte prüfen Sie die Schreibweise und versuchen Sie es erneut."
            )
            initial = val
            continue

        return val

def ask_user_selection(parent=None, users: Optional[List[str]] = None,
                       preselect: str = "", config: "Config" = None
                       ) -> Optional[str]:
    """
    Fragt bei mehreren gespeicherten Benutzern, welcher verwendet werden soll.
    Bietet auch 'Anderen Benutzer eingeben…' und Einstellungen.
    """
    users = list(users or [])
    items = users + ["➕ Anderen Benutzer eingeben…"]

    default = preselect if preselect in users else items[0]

    # --- Schleife: nach Settings-Rückkehr Dialog erneut zeigen ---
    while True:
        dialog = myUniversalDialog(
            parent,
            "Benutzer auswählen",
            f"Es sind <b>{len(users)}</b> Benutzer gespeichert.<br>"
            "Bitte wählen Sie den gewünschten Benutzer:",
            buttons=add_settings_button([
                ("OK", "primary", "accept"),
                ("Abbrechen", "danger", "cancel"),
            ]),
            icon_type="",
            text_alignment=Qt.AlignLeft,
            input_fields=[{
                "type": "combobox",
                "name": "user",
                "label": "Benutzer:",
                "items": items,
                "default": default,
            }],
            default_button="accept",
        )
        dialog.exec_()
        result = dialog.result_value

        # Settings-Button geklickt
        if result == "settings":
            if config is not None:
                saved = show_settings_dialog(parent, config)
                if saved:
                    show_confirm_dialog(
                        parent,
                        "Einstellungen gespeichert",
                        "Die Einstellungen wurden gespeichert.",
                        config=None  # kein weiterer Settings-Button
                    )
            continue

        if result != "accept":
            return None

        selected = dialog.get_input_value("user") or ""
        if selected == "➕ Anderen Benutzer eingeben…":
            return ask_username_dialog(parent, "", "Neuen Benutzer hinzufügen",
                                       "Bitte neuen GitHub-Benutzernamen eingeben:")
        return selected

def ask_token_dialog(parent=None, rate_limit_warning: bool = False,
                     initial_token: str = "",
                     existing_token_valid: bool = False,
                     existing_token_user: str = "") -> Optional[str]:
    """
    Fragt nach einem GitHub Personal Access Token (optional).

    rate_limit_warning:     Warnbox anzeigen (Rate-Limit erreicht)
    initial_token:          Vorbelegung des Felds
    existing_token_valid:   True, wenn bereits ein gültiger Token vorliegt
    existing_token_user:    Der GitHub-Benutzer, zu dem der Token gehört
    """
    warning_block = ""
    if rate_limit_warning:
        warning_block = (
            "<div style='background-color:#3A1F00; border-left:4px solid #FF9800; "
            "padding:10px; margin-bottom:12px; border-radius:4px;'>"
            "<b style='color:#FFB74D;'>⚠️ Rate-Limit erreicht!</b><br>"
            "<span style='color:#FFFFFF; font-size:13px;'>"
            "Ohne gültigen Token wird die Analyse <b>fehlschlagen</b>."
            "</span>"
            "</div>"
        )

    if existing_token_valid:
        status_block = (
            "<div style='background-color:#0D2C0D; border-left:4px solid #4CAF50; "
            "padding:10px; margin-bottom:12px; border-radius:4px;'>"
            "<b style='color:#81C784;'>✅ Gültiger Token vorhanden</b><br>"
            f"<span style='color:#FFFFFF; font-size:13px;'>"
            f"Gespeichert für Benutzer <b>{existing_token_user}</b>.<br>"
            "Du kannst ihn behalten oder einen neuen eingeben."
            "</span>"
            "</div>"
        )
    else:
        status_block = (
            "<p>Ohne Token erlaubt GitHub nur <b>60 Anfragen/Stunde</b>.<br>"
            "Mit Token sind es <b>5.000 Anfragen/Stunde</b>.</p>"
        )

    info_html = (
        "<div style='text-align:left; font-size:14px; line-height:1.6;'>"
        + warning_block
        + status_block +
        "<p>Token erstellen/verwalten:<br>"
        "<a href='https://github.com/settings/tokens' "
        "style='color:#4FC3F7;'>https://github.com/settings/tokens</a><br>"
        "<small>(Scope: <code>public_repo</code>, "
        "oder <code>repo</code> für private Repos)</small></p>"
        "<p style='color:#B0B0B0; font-size:12px;'>"
        "Der Token wird lokal in <code>github_tokens.json</code> gespeichert "
        "(Klartext!) und automatisch gelöscht, wenn er ungültig wird.</p>"
        "</div>"
    )

    if existing_token_valid and not rate_limit_warning:
        buttons = [
            ("Behalten & fortfahren", "success", "keep_token"),
            ("Neuen Token eingeben", "primary", "accept"),
            ("Token löschen", "danger", "delete_token"),
            ("Abbrechen", "danger", "cancel"),
        ]
        icon = "success"
        default_btn = "keep_token"
    elif rate_limit_warning:
        buttons = [
            ("Token eingeben", "success", "accept"),
            ("Trotzdem ohne Token", "danger", "no_token"),
            ("Abbrechen", "danger", "cancel"),
        ]
        icon = "warning"
        default_btn = "accept"
    else:
        buttons = [
            ("Token eingeben", "success", "accept"),
            ("Ohne Token fortfahren", "warning", "no_token"),
            ("Abbrechen", "danger", "cancel"),
        ]
        icon = "info"
        default_btn = "accept"

    # ------------------------------------------------------------
    # Live-Callback: Button-Text passt sich dem Feldinhalt an
    # ------------------------------------------------------------
    def _on_token_field_changed(text: str):
        # Beim allerersten Aufruf (während der Dialog-Erstellung) ist
        # _btn noch nicht gesetzt → dann nichts tun.
        if not hasattr(_on_token_field_changed, "_btn"):
            return
        btn = _on_token_field_changed._btn
        new_text = ("Behalten & fortfahren"
                    if text.strip() else "Ohne Token fortfahren")
        if btn.text() != new_text:
            btn.setText(new_text)
            fm = QFontMetrics(btn.font())
            w = max(180, fm.horizontalAdvance(new_text) + 40)
            btn.setFixedWidth(w)

    # Nur wenn wir einen gültigen Token haben, brauchen wir das Callback
    use_callbacks = existing_token_valid and not rate_limit_warning
    field_callbacks = {"token": _on_token_field_changed} if use_callbacks else None

    dialog = myUniversalDialog(
        parent,
        "GitHub Token",
        info_html,
        buttons=buttons,
        icon_type=icon,
        text_alignment=Qt.AlignLeft,
        input_fields=[{
            "type": "text",
            "name": "token",
            "label": "GitHub Token:",
            "default": initial_token,
            "placeholder": "ghp_… (leer lassen = ohne Token)",
        }],
        default_button=default_btn,
        field_changed_callbacks=field_callbacks,
    )

    # ------------------------------------------------------------
    # Button-Referenz ermitteln und initialen Text setzen
    # ------------------------------------------------------------
    if use_callbacks:
        for btn in dialog.button_widgets:
            if btn.property("action") == "keep_token":
                _on_token_field_changed._btn = btn
                _on_token_field_changed(initial_token)
                break

        # "keep_token"-Button umleiten:
        #   Feld unverändert → keep_token (alten Token behalten)
        #   Feld geleert     → no_token   (ohne Token fortfahren)
        def _keep_or_no_token():
            current_text = dialog.get_input_value("token") or ""
            if current_text.strip():
                dialog.result_value = "keep_token"
            else:
                dialog.result_value = "no_token"
            dialog.accept()

        dialog.action_callbacks["keep_token"] = _keep_or_no_token

    # ------------------------------------------------------------
    # Neu eingetippten Token ebenfalls über den "accept"-Button leiten:
    # Wenn der User etwas anderes als initial_token eingetippt hat und
    # "Neuen Token eingeben" klickt, geht das über handle_button.
    # Wenn der User allerdings direkt auf "Behalten & fortfahren" klickt,
    # obwohl er etwas Neues eingetippt hat, fangen wir das hier ab:
    # ------------------------------------------------------------
    if use_callbacks:
        def _handle_accept_with_new_token():
            current_text = (dialog.get_input_value("token") or "").strip()
            if current_text and current_text != initial_token:
                # User hat einen neuen Token eingetippt → wie "accept"
                dialog.result_value = "accept"
            else:
                dialog.result_value = "keep_token"
            dialog.accept()

        # Wenn "accept" geklickt wird, soll standardmäßig der Feldwert genommen
        # werden — dafür brauchen wir keine Umleitung, weil handle_button den
        # Feldwert bereits einsammelt.

    dialog.exec_()

    # ------------------------------------------------------------
    # Ergebnis-Auswertung
    # ------------------------------------------------------------
    if dialog.result_value == "cancel":
        return None
    if dialog.result_value in ("no_token", "keep_token"):
        return initial_token
    if dialog.result_value == "delete_token":
        return "__DELETE__"
    val = dialog.get_input_value("token") or ""
    return val.strip()

def show_error_dialog(parent, title: str, message: str,
                      config: "Config" = None,
                      show_settings: bool = True):
    """
    Zeigt einen Fehler-Dialog. Optional mit Einstellungen-Button.

    Nach Klick auf Einstellungen und Speichern wird der User gefragt:
      • 'Erneut versuchen' → Fehlerdialog schließen, Aufrufer startet neu
      • 'Zurück'          → Fehlerdialog erneut anzeigen
    """
    buttons = [("OK", "primary", "accept")]
    if show_settings and config is not None:
        buttons = add_settings_button(buttons)

    while True:
        dialog = myUniversalDialog(
            parent,
            title,
            message,
            buttons=buttons,
            icon_type="error",
            text_alignment=Qt.AlignLeft,
        )
        dialog.exec_()

        if dialog.result_value == "settings":
            if config is None:
                continue
            # --- Settings-Dialog öffnen ---
            saved = show_settings_dialog(parent, config)
            if not saved:
                # User hat abgebrochen → zurück zum Fehlerdialog
                continue
            # --- Nachfrage: neu starten? ---
            restart = show_confirm_dialog(
                parent,
                "Einstellungen geändert",
                "Die Einstellungen wurden gespeichert.<br><br>"
                "Möchtest du die Analyse jetzt <b>mit den neuen "
                "Einstellungen erneut starten</b>?",
            )
            if restart:
                # Signal an den Aufrufer: er soll neu starten
                return True
            # Sonst: Fehlerdialog erneut zeigen
            continue

        break
    return False  # kein Neustart gewünscht

def show_confirm_dialog(parent, title: str, message: str,
                        config: "Config" = None) -> bool:
    """Zeigt einen Ja/Nein-Dialog. Rückgabe: True bei Ja."""
    buttons = [
        ("Ja", "success", "yes"),
        ("Nein, neu eingeben", "warning", "no"),
    ]
    if config is not None:
        buttons = add_settings_button(buttons)

    while True:
        dialog = myUniversalDialog(
            parent,
            title,
            message,
            buttons=buttons,
            icon_type="",
            text_alignment=Qt.AlignLeft,
            default_button="yes",
        )
        dialog.exec_()

        if dialog.result_value == "settings":
            if config is None:
                continue
            saved = show_settings_dialog(parent, config)
            if not saved:
                continue
            # Nach Settings-Rückkehr: direkt neu anzeigen
            # (kein Neustart-Signal – der Aufrufer entscheidet)
            continue
        return dialog.result_value == "yes"

def show_info_dialog(parent, release_info: Optional[dict] = None):
    """
    Zeigt den Info-Dialog über GitPulseX.
    Wenn release_info übergeben wird und neuer ist, wird ein
    Update-Hinweis eingeblendet.
    """
    # Update-Block nur wenn neuer
    update_block = ""
    if release_info and release_info.get("is_newer"):
        new_tag = release_info["tag"]
        new_url = release_info["url"]
        published = release_info.get("published_at", "")[:10]
        update_block = (
            "<div style='background-color:#1A3A1A; "
            "border-left:4px solid #4CAF50; padding:12px; "
            "margin:12px 0; border-radius:4px;'>"
            "<b style='color:#81C784;'>🎉 Neues Release verfügbar!</b><br>"
            f"<span style='color:#FFFFFF; font-size:13px;'>"
            f"Version <b>{new_tag}</b> ist seit {published} verfügbar.<br>"
            f"<a href='{new_url}' style='color:#4FC3F7;'>"
            f"→ Zum Release auf GitHub</a>"
            f"</span>"
            "</div>"
        )

    info_html = (
        "<div style='text-align:left; font-size:14px; line-height:1.7;'>"

        f"<p style='font-size:18px;'>"
        f"<b>{APP_NAME}</b> <span style='color:#4FC3F7;'>v{APP_VERSION}</span>"
        f"</p>"

        "<p>GitHub Multi-Repository Statistik-Collector<br>"
        "Analysiert Repositories, Releases, Downloads, Follower und mehr.</p>"

        "<hr style='border:none; border-top:1px solid #333; margin:12px 0;'>"

        f"<p><b>Autor:</b> {APP_AUTHOR}<br>"
        f"<b>Lizenz:</b> {APP_LICENSE}<br>"
        f"<b>Projekt:</b> "
        f"<a href='{APP_GITHUB_URL}' style='color:#4FC3F7;'>{APP_GITHUB_URL}</a>"
        f"</p>"

        "<p style='color:#B0B0B0; font-size:12px;'>"
        "Bugs & Feature-Wünsche bitte als Issue auf GitHub melden.<br>"
        "Pull Requests sind willkommen."
        "</p>"

        + update_block +

        "<hr style='border:none; border-top:1px solid #333; margin:12px 0;'>"

        "<p style='color:#B0B0B0; font-size:12px;'>"
        "<b>Verwendete Bibliotheken:</b><br>"
        "• <b>PyQt5</b> – GUI-Framework<br>"
        "• <b>requests</b> – HTTP-Client<br>"
        "• <b>platformdirs</b> – Plattform-Pfade"
        "</p>"

        "</div>"
    )

    buttons = [("OK", "primary", "accept")]
    # buttons = add_settings_button(buttons)  # konsistent mit anderen Dialogen

    while True:
        dialog = myUniversalDialog(
            parent,
            f"Über {APP_NAME}",
            info_html,
            buttons=buttons,
            icon_type="",
            text_alignment=Qt.AlignLeft,
            selectable_text=False,
        )
        dialog.exec_()

        result = dialog.result_value

        break

def show_settings_dialog(parent, config: Config) -> bool:
    """
    Zeigt einen Dialog mit allen Konfigurationsoptionen.
    Rückgabe: True wenn gespeichert wurde, False bei Abbruch.
    """
    def _bool(v): return "Ja" if v else "Nein"

    info_html = (
        "<div style='text-align:left; font-size:14px; line-height:1.6;'>"
        "<p>Hier kannst du alle Einstellungen anpassen.</p>"
        "<p style='color:#81C784;'>"
        "Die Werte werden <b>sofort</b> in "
        "<code>github_stats_config.json</code> gespeichert."
        "</p>"
        "<p style='color:#FFB74D;'>"
        "Nach dem Speichern läuft die Analyse automatisch neu, "
        "damit die geänderten Filter greifen."
        "</p>"
        "</div>"
    )

    dialog = myUniversalDialog(
        parent,
        "Einstellungen",
        info_html,
        buttons=[
            ("Speichern", "success", "accept"),
            ("Abbrechen", "danger", "cancel"),
        ],
        icon_type="",
        text_alignment=Qt.AlignLeft,
        input_fields=[
            # ----- Repository-Filter -----
            {
                "type": "combobox",
                "name": "save_location",
                "label": "Speicherort für Berichte:",
                "items": [
                    "Statistik-Ordner (empfohlen)",
                    "Downloads-Ordner",
                    "Jedes Mal fragen",
                ],
                "default": {
                    "statistics": "Statistik-Ordner (empfohlen)",
                    "downloads": "Downloads-Ordner",
                    "": "Jedes Mal fragen",
                }.get(config.save_location, "Statistik-Ordner (empfohlen)"),
            },
            {
                "type": "combobox",
                "name": "skip_forks",
                "label": "Forks überspringen?",
                "items": ["Ja", "Nein"],
                "default": _bool(config.skip_forks),
            },
            {
                "type": "combobox",
                "name": "skip_archived",
                "label": "Archivierte Repos überspringen?",
                "items": ["Ja", "Nein"],
                "default": _bool(config.skip_archived),
            },
            {
                "type": "combobox",
                "name": "skip_private",
                "label": "Private Repos überspringen?",
                "items": ["Ja", "Nein"],
                "default": _bool(config.skip_private),
            },
            {
                "type": "combobox",
                "name": "only_with_releases",
                "label": "Nur Repos mit Releases anzeigen?",
                "items": ["Nein", "Ja"],
                "default": "Ja" if config.only_with_releases else "Nein",
            },
            {
                "type": "text",
                "name": "repo_filter",
                "label": "Regex-Filter für Repo-Namen (leer = kein Filter):",
                "default": config.repo_filter,
                "placeholder": "z. B. ^tool- (leer lassen für alle)",
            },
            # ----- Trafik-Daten -----
            {
                "type": "combobox",
                "name": "include_page_views",
                "label": "Seitenaufrufe abfragen? (nur mit Token)",
                "items": ["Ja", "Nein"],
                "default": _bool(config.include_page_views),
            },
            {
                "type": "combobox",
                "name": "include_clones",
                "label": "Clone-Statistiken abfragen? (nur mit Token)",
                "items": ["Ja", "Nein"],
                "default": _bool(config.include_clones),
            },
            {
                "type": "combobox",
                "name": "include_traffic",
                "label": "Traffic-Quellen abfragen? (nur mit Token)",
                "items": ["Ja", "Nein"],
                "default": _bool(config.include_traffic),
            },
            # ----- Follower -----
            {
                "type": "combobox",
                "name": "include_followers",
                "label": "Follower-Liste abrufen?",
                "items": ["Ja", "Nein"],
                "default": _bool(config.include_followers),
            },
            {
                "type": "combobox",
                "name": "followers_detail",
                "label": "Follower-Details abrufen? (langsam, viele API-Calls)",
                "items": ["Nein", "Ja"],
                "default": "Ja" if config.followers_detail else "Nein",
            },
            # ----- Dialog -----
            {
                "type": "combobox",
                "name": "show_dialog",
                "label": "Report-Dialog nach Analyse anzeigen?",
                "items": ["Ja", "Nein"],
                "default": _bool(config.show_dialog),
            },
            {
                "type": "combobox",
                "name": "log_level",
                "label": "Log-Level (für Logdatei app.log):",
                "items": ["DEBUG", "INFO", "WARNING", "ERROR"],
                "default": config.log_level or "INFO",
            },
        ],
        default_button="accept",
    )
    dialog.exec_()

    if dialog.result_value != "accept":
        return False

    # Werte auslesen und anwenden
    def _get_bool(field):
        return (dialog.get_input_value(field) or "Nein") == "Ja"

    # Speicherort (Klartext → technischer Wert)
    _save_loc_map = {
        "Statistik-Ordner (empfohlen)": "statistics",
        "Downloads-Ordner": "downloads",
        "Jedes Mal fragen": "",
    }
    save_loc_choice = dialog.get_input_value("save_location") or ""
    config.save_location = _save_loc_map.get(
        save_loc_choice, "statistics"
    )
    config.skip_forks = _get_bool("skip_forks")
    config.skip_archived = _get_bool("skip_archived")
    config.skip_private = _get_bool("skip_private")
    config.only_with_releases = _get_bool("only_with_releases")
    config.repo_filter = (dialog.get_input_value("repo_filter") or "").strip()
    config.include_page_views = _get_bool("include_page_views")
    config.include_clones = _get_bool("include_clones")
    config.include_traffic = _get_bool("include_traffic")
    config.include_followers = _get_bool("include_followers")
    config.followers_detail = _get_bool("followers_detail")
    config.show_dialog = _get_bool("show_dialog")
    config.log_level = (dialog.get_input_value("log_level") or "INFO").upper()

    # In JSON speichern
    config.save_to_file()

    # Log-Level sofort anwenden
    try:
        new_level = log_level_from_str(config.log_level)
        logger.setLevel(new_level)
        for handler in logger.handlers:
            handler.setLevel(new_level)
        logger.info(f"Log-Level geändert auf "
                    f"{logging.getLevelName(new_level)}")
    except Exception as e:
        print(f"⚠️  Log-Level konnte nicht gesetzt werden: {e}")

    return True

def add_settings_button(buttons):
    """Hängt einen ⚙️-Einstellungen-Button hinzu (vor 'cancel', falls vorhanden)."""
    new_buttons = list(buttons or [])
    insert_at = len(new_buttons)
    if new_buttons and len(new_buttons[-1]) >= 3 and new_buttons[-1][2] == "cancel":
        insert_at = len(new_buttons) - 1
    new_buttons.insert(insert_at, ("Einstellungen", "primary", "settings"))
    return new_buttons


# ============================================================
# Hauptprogramm
# ============================================================

def main():
    """
    Hauptfunktion. Führt den kompletten Ablauf aus.
    Bei „Benutzer wechseln" oder „Einstellungen geändert" wird
    der Ablauf in einer Schleife erneut gestartet.
    """
    # ===== QApplication EINMAL erstellen =====
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setDesktopFileName(APP_NAME.lower())


    # ===== Startup-Info =====
    mode = "Bundle" if APP_PATHS["is_frozen"] else "Dev"
    print(f"🚀 {APP_NAME} v{APP_VERSION} startet ({mode}-Modus)")
    print(f"   Basis:    {APP_PATHS['base']}")
    print(f"   Settings: {APP_PATHS['settings']}")
    print(f"   Logs:     {APP_PATHS['logs']}")
    print(f"   Berichte: {APP_PATHS['statistics']}")

    # ===== Alte Dateien migrieren (nur Dev-Modus) =====
    migrate_legacy_files()

    # ===== Logging initialisieren (erst mit Default-Level) =====
    log_path = None
    try:
        log_path = setup_logging(level=LOG_LEVEL_DEFAULT)
        print(f"📝 Logdatei: {log_path}")
    except Exception as e:
        print(f"⚠️  Logging-Setup fehlgeschlagen: {e}")


    # ==== Icon: bevorzugt BinhDiez.png im Script-Ordner, sonst Qt-Standard
    custom_icon_path = APP_PATHS["assets"] / "GitPulseX.png"
    if custom_icon_path.exists():
        try:
            app.setWindowIcon(QIcon(str(custom_icon_path)))
        except Exception as e:
            print(f"⚠️  Icon konnte nicht geladen werden: {e}")
    else:
        # Fallback: Qt-Standard-Icon
        try:
            icon = app.style().standardIcon(app.style().SP_ComputerIcon)
            app.setWindowIcon(icon)
        except Exception:
            pass

    # ===== Konfiguration EINMAL laden =====
    config = Config()
    config.load_from_file()

    # Ursprünglichen verbose-Wert (aus JSON) merken
    _json_verbose = config.verbose

    config.parse_args()

    logger.debug(f"CLI-Args: owner={config.owner!r}, "
                 f"token={'<gesetzt>' if config.token else '<leer>'}, "
                 f"verbose={config.verbose}")

    # ===== Log-Level festlegen =====
    apply_log_level(config, verbose_override=config.verbose)

    # CLI-verbose NICHT persistieren
    config.verbose = _json_verbose

    logger.info(f"Konfiguration geladen (owner={config.owner!r}, "
                f"verbose={config.verbose})")

    cli_owner = config.owner.strip()
    config.owner = ""

    # ===== Manager EINMAL erzeugen =====
    user_mgr = UserManager()
    token_mgr = TokenManager()

    # ===== Release-Check (einmal pro Lauf) =====
    release_info = None
    try:
        release_info = check_latest_release(APP_VERSION)
        if release_info and release_info.get("is_newer"):
            print(f"🎉 Neues Release verfügbar: {release_info['tag']} "
                  f"(aktuell: v{APP_VERSION})")
            print(f"   → {release_info['url']}")
            logger.info(f"Neues Release verfügbar: {release_info['tag']}")
        elif release_info:
            logger.debug(f"Release-Check: {release_info['tag']} "
                         f"(aktuell: v{APP_VERSION})")
    except Exception as e:
        logger.debug(f"Release-Check übersprungen: {e}")

    # ===== Wiederholungs-Schleife =====
    force_user_selection = False
    previous_token = ""

    while True:
        # ------------------------------------------------------------
        # 1) Benutzer-Auswahl
        # ------------------------------------------------------------
        if cli_owner and not force_user_selection:
            user_mgr.add_user(cli_owner, make_current=True)
            selected_user = cli_owner
            cli_owner = ""
        else:
            if not user_mgr.has_users():
                username = ask_username_dialog(
                    None, "",
                    "Erstbenutzung – GitHub-Benutzer anlegen",
                    "Willkommen!<br><br>Bitte geben Sie Ihren "
                    "<b>GitHub-Benutzernamen</b> ein.<br>"
                    "Dieser wird für zukünftige Starts gespeichert.",
                    config=config
                )
                if not username:
                    print("❌ Kein Benutzer angegeben. Abbruch.")
                    return 1
                user_mgr.add_user(username)
                selected_user = username
            elif len(user_mgr.get_users()) == 1 and not force_user_selection:
                selected_user = user_mgr.get_users()[0]
                user_mgr.set_current(selected_user)
            else:
                selected_user = ask_user_selection(
                    None, user_mgr.get_users(), user_mgr.get_current(),
                    config=config
                )
                if not selected_user:
                    print("❌ Kein Benutzer ausgewählt. Abbruch.")
                    return 1
                user_mgr.add_user(selected_user)

        config.owner = selected_user
        logger.debug(f"Aktueller Benutzer: {config.owner}")
        force_user_selection = False

        # ------------------------------------------------------------
        # 2) Benutzer-Validierung
        # ------------------------------------------------------------
        exists, api_error = run_with_busy_dialog(
            None,
            f"Prüfe Benutzer '{config.owner}' bei GitHub",
            lambda: check_github_user_exists(config.owner)
        )
        if not exists:
            show_error_dialog(
                None,
                "Benutzer nicht gefunden",
                f"Der Benutzer <b>'{config.owner}'</b> existiert nicht "
                f"auf GitHub.<br><br>"
                "Bitte wählen oder geben Sie einen gültigen "
                "Benutzernamen ein.",
                config=config
            )
            user_mgr.remove_user(config.owner)
            force_user_selection = True
            continue

        if api_error and config.verbose:
            print(f"⚠️  Benutzer-Prüfung nicht möglich: {api_error}")

        # ---------- Avatar von GitHub laden ----------
        # Vorherigen Avatar zurücksetzen (falls User gewechselt hat)
        if _APP_AVATAR_USER and _APP_AVATAR_USER != config.owner:
            clear_app_avatar()

        # Avatar laden (mit Token für höhere Rate-Limits)
        avatar_loaded = set_app_avatar(config.owner, config.token)
        if config.verbose:
            if avatar_loaded:
                print(f"🖼️  Avatar für '{config.owner}' geladen")
            else:
                print(f"🖼️  Avatar für '{config.owner}' nicht verfügbar "
                      f"(Fallback)")

        logger.debug(f"Avatar für '{config.owner}': "
                     f"{'geladen' if avatar_loaded else 'nicht verfügbar'}")

        # ------------------------------------------------------------
        # 3) Token
        # ------------------------------------------------------------
        if previous_token:
            config.token = previous_token
            previous_token = ""

        saved_token = config.token or token_mgr.get_token(config.owner)
        token_valid = False
        token_owner = ""

        if saved_token:
            print("🔎 Prüfe gespeicherten Token…")
            is_valid, api_user, err = run_with_busy_dialog(
                None,
                "Prüfe gespeicherten Token bei GitHub",
                lambda: check_token_valid(saved_token)
            )
            if is_valid:
                token_valid = True
                token_owner = api_user or config.owner
                config.token = saved_token
                saved_at = token_mgr.get_saved_at(config.owner)
                print(f"🔑 Token für '{config.owner}' geladen "
                      f"(gespeichert: {saved_at or '?'}) → gültig ✓")
            else:
                print(f"⚠️  Gespeicherter Token für '{config.owner}' "
                      f"ungültig: {err}")
                print(f"    → Token wird gelöscht.")
                token_mgr.remove_token(config.owner)
                saved_token = ""
                config.token = ""

        rate_limit_hit = (api_error == "GitHub Rate-Limit")

        if not token_valid:
            # ---- Fall A: Kein gültiger Token vorhanden ----
            token_input = ask_token_dialog(
                None,
                rate_limit_warning=rate_limit_hit,
                initial_token=saved_token,
                existing_token_valid=False,
            )
            if token_input is None:
                print("❌ Abgebrochen.")
                return 1
            if token_input == "":
                config.token = ""
                print("⚠️  Kein Token – Rate-Limit auf 60 Anfragen/Stunde "
                      "beschränkt!")
                print("")
            else:
                is_valid, api_user, err = run_with_busy_dialog(
                    None,
                    "Prüfe neuen Token bei GitHub",
                    lambda: check_token_valid(token_input)
                )
                if not is_valid:
                    show_error_dialog(
                        None,
                        "Token ungültig",
                        f"Der eingegebene Token ist ungültig:<br><br>"
                        f"<b>{err}</b><br><br>"
                        "Bitte neuen Token erstellen und erneut versuchen.",
                        config=config
                    )
                    previous_token = ""
                    continue
                config.token = token_input
                token_mgr.set_token(config.owner, token_input)
                print(f"✅ Token gespeichert für '{config.owner}'"
                      + (f" (GitHub-User: {api_user})" if api_user else ""))
        else:
            # ---- Fall B: Gültiger Token vorhanden → User fragen ----
            token_input = ask_token_dialog(
                None,
                rate_limit_warning=False,
                initial_token=saved_token,
                existing_token_valid=True,
                existing_token_user=token_owner or config.owner,
            )
            if token_input is None:
                print("❌ Abgebrochen.")
                return 1
            elif token_input == "__DELETE__":
                token_mgr.remove_token(config.owner)
                config.token = ""
                print(f"🗑️  Token für '{config.owner}' gelöscht.")
                previous_token = ""
                continue
            elif token_input == "":
                # User hat das Feld geleert (Button wurde zu "Ohne Token")
                token_mgr.remove_token(config.owner)
                config.token = ""
                print(f"🗑️  Token für '{config.owner}' entfernt "
                      f"(Feld geleert).")
                previous_token = ""
                continue
            elif token_input == saved_token:
                config.token = saved_token
                print(f"🔑 Verwende bestehenden Token für '{config.owner}'.")
            else:
                # Neuer Token eingegeben → prüfen + speichern
                is_valid, api_user, err = run_with_busy_dialog(
                    None,
                    "Prüfe neuen Token bei GitHub",
                    lambda: check_token_valid(token_input)
                )
                if not is_valid:
                    show_error_dialog(
                        None,
                        "Token ungültig",
                        f"Der eingegebene Token ist ungültig:<br><br>"
                        f"<b>{err}</b><br><br>"
                        "Bitte neuen Token erstellen und erneut versuchen.",
                        config=config
                    )
                    previous_token = ""
                    continue
                config.token = token_input
                token_mgr.set_token(config.owner, token_input)
                print(f"✅ Neuer Token gespeichert für '{config.owner}'"
                      + (f" (GitHub-User: {api_user})" if api_user else ""))

        logger.info(f"Token-Status: {'gültig' if token_valid else 'nicht vorhanden/ungültig'}")

        # ---------- Avatar aktualisieren (falls Token jetzt vorhanden) ----------
        if not avatar_loaded and config.token:
            avatar_loaded = set_app_avatar(config.owner, config.token)

        # ------------------------------------------------------------
        # 4) Rate-Limit-Status anzeigen
        # ------------------------------------------------------------
        rl = get_rate_limit_status(config.token)
        if rl:
            remaining = rl.get("remaining", "?")
            limit = rl.get("limit", "?")
            reset_ts = rl.get("reset", 0)
            reset_str = ""
            if reset_ts:
                try:
                    reset_dt = datetime.fromtimestamp(reset_ts)
                    reset_str = reset_dt.strftime("%H:%M:%S")
                except Exception:
                    pass
            if isinstance(remaining, int) and isinstance(limit, int):
                if remaining < 10:
                    print(f"⚠️  GitHub API: nur noch {remaining}/{limit} "
                          f"Anfragen (Reset um {reset_str})")
                    print("    → Bei zu vielen Repos wird die Analyse "
                          "abgebrochen.")
                else:
                    print(f"✅ GitHub API: {remaining}/{limit} Anfragen "
                          f"verfügbar (Reset um {reset_str})")

        # ------------------------------------------------------------
        # 5) Speicherort
        # ------------------------------------------------------------
        target_dir = ask_save_location(config)
        if target_dir is None:
            print("❌ Abgebrochen durch Benutzer.")
            return 1

        # ---------- Dateiname zusammensetzen ----------
        # WICHTIG: config.output_file ist immer nur der BASISNAME!
        # (wird in save_to_file() entsprechend gespeichert)
        output_name = build_output_filename(config.owner, config.output_file)
        output_path = target_dir / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # config.output_file NICHT mit vollem Pfad überschreiben,
        # sonst wächst der Name bei jedem Lauf.
        # Wir nutzen output_path nur lokal für das Speichern.

        config.save_to_file()  # speichert weiterhin nur den Basisnamen

        if config.verbose:
            print(f"📄 Ausgabedatei: {output_path.name}")
            logger.info(f"Ausgabedatei: {output_path.name}")

        logger.debug(f"Speicherort: {target_dir}")
        logger.debug(f"Dateiname:   {output_name}")
        logger.debug(f"Vollpfad:    {output_path}")

        # ------------------------------------------------------------
        # 6) Analyse (Worker + Progress-Dialog)
        # ------------------------------------------------------------
        print("🚀 Starte Analyse…")
        logger.debug(f"Konfiguration für Analyse:")
        logger.debug(f"  skip_archived={config.skip_archived}, "
                     f"skip_forks={config.skip_forks}, "
                     f"skip_private={config.skip_private}")
        logger.debug(f"  only_with_releases={config.only_with_releases}, "
                     f"repo_filter={config.repo_filter!r}")
        logger.debug(f"  include_followers={config.include_followers}, "
                     f"followers_detail={config.followers_detail}")

        worker = AnalysisWorker(config)
        progress_dlg = AnalysisProgressDialog(None, config)
        progress_dlg.start(worker)
        exec_result = progress_dlg.exec_()

        if progress_dlg.cancelled:
            print("⏹️  Vom Benutzer abgebrochen.")
            return 1

        if progress_dlg.error_message_html or progress_dlg.error_message_plain:
            html_msg = progress_dlg.error_message_html or \
                       (progress_dlg.error_message_plain or "").replace("\n", "<br>")

            # Vor dem Fehlerdialog: relevante Werte merken, um Änderungen
            # durch den Settings-Button zu erkennen.
            old_snapshot = (
                config.skip_archived,
                config.skip_forks,
                config.skip_private,
                config.only_with_releases,
                config.repo_filter,
                config.include_followers,
                config.followers_detail,
                config.include_page_views,
                config.include_clones,
                config.include_traffic,
            )

            user_wants_restart = show_error_dialog(
                None,
                "Analyse fehlgeschlagen",
                html_msg,
                config=config
            )
            print("❌ Analyse fehlgeschlagen:")
            if progress_dlg.error_message_plain:
                print(progress_dlg.error_message_plain)

            if user_wants_restart:
                print(" Benutzer wünscht Neustart – Analyse läuft erneut.")
                previous_token = config.token
                continue

            return 1

        if exec_result != QDialog.Accepted or progress_dlg.result_multi is None:
            print("❌ Analyse unerwartet beendet.")
            return 1

        multi_collector = progress_dlg.result_multi
        report_text_ready = progress_dlg.result_report_text

        if multi_collector.rate_limited:
            show_error_dialog(
                None,
                "Rate-Limit erreicht",
                "GitHub hat die API-Anfragen limitiert.<br><br>"
                "Bitte einen <b>Personal Access Token</b> verwenden – "
                "damit steigt das Limit von 60 auf 5.000 Anfragen/Stunde.<br><br>"
                "<a href='https://github.com/settings/tokens' "
                "style='color:#4FC3F7;'>Token erstellen</a>",
                config=config
            )
            print("❌ Abbruch wegen Rate-Limit. Bitte Token verwenden.")
            previous_token = ""
            continue

        if not multi_collector.collectors:
            total_all = len(multi_collector.repo_metadata)
            reasons = []
            if config.skip_archived:
                reasons.append("Archivierte Repos werden übersprungen "
                               "(skip_archived = true)")
            if config.skip_forks:
                reasons.append("Forks werden übersprungen "
                               "(skip_forks = true)")
            if config.skip_private:
                reasons.append("Private Repos werden übersprungen "
                               "(skip_private = true)")
            if config.only_with_releases:
                reasons.append("Nur Repos mit Releases "
                               "(only_with_releases = true)")
            if config.repo_filter:
                reasons.append(f"Regex-Filter aktiv: '{config.repo_filter}'")

            msg_parts = [
                f"Für den Benutzer <b>'{config.owner}'</b> wurden "
                f"<b>{total_all}</b> Repositories gefunden, aber "
                f"<b>keines</b> konnte analysiert werden.",
                "",
            ]
            if reasons:
                msg_parts.append("<b>Aktive Filter:</b>")
                for r in reasons:
                    msg_parts.append(f"&nbsp;&nbsp;• {r}")
                msg_parts.append("")
            msg_parts.append("<b>Tipp:</b> Öffne die <b>Einstellungen</b> "
                             "und passe die Filter an (z. B. "
                             "<code>skip_archived → Nein</code>).")
            msg_parts.append("Alternativ: <code>github_stats_config.json</code> "
                             "direkt bearbeiten.")
            full_message = "<br>".join(msg_parts)

            # Snapshot vor dem Fehlerdialog
            user_wants_restart = show_error_dialog(
                None,
                "Keine Repositories zum Analysieren",
                full_message,
                config=config
            )
            print("❌ Keine Daten zum Auswerten gefunden!")

            if user_wants_restart:
                print("⚙️  Benutzer wünscht Neustart – Analyse läuft erneut.")
                previous_token = config.token
                continue

            # Keine Änderung → Benutzerauswahl erneut zeigen
            force_user_selection = True
            previous_token = config.token
            continue

        # ------------------------------------------------------------
        # 7) Bericht speichern
        # ------------------------------------------------------------
        class _ReadyReport:
            def __init__(self, text: str):
                self._text = text
            def get_report_text(self) -> str:
                return self._text
            def save(self, output_file: str) -> Path:
                outfile = Path(output_file)
                with open(outfile, "w", encoding="utf-8") as f:
                    f.write(self._text)
                return outfile

        report = _ReadyReport(report_text_ready)

        try:
            output_path = report.save(str(output_path))
        except Exception as e:
            logger.exception(
                f"Bericht konnte nicht gespeichert werden: {output_path}"
            )
            show_error_dialog(
                None,
                "Speichern fehlgeschlagen",
                f"Der Bericht konnte nicht gespeichert werden:<br><br>"
                f"<b>{e}</b><br><br>"
                f"Pfad: <code>{output_path}</code>",
                config=config
            )
            print(f"❌ Speichern fehlgeschlagen: {e}")
            return 1
        # ------------------------------------------------------------
        # 8) Zusammenfassung Konsole
        # ------------------------------------------------------------
        stats = multi_collector.get_total_stats()
        print("")
        print("📊 ZUSAMMENFASSUNG:")
        print(f"  Repositories:   {stats['repos_analyzed']}")
        print(f"  Downloads:      {stats['total_downloads']:,}")
        print(f"  Releases:       {stats['total_releases']}")
        print(f"  Assets:         {stats['total_assets']}")
        print(f"  Stars:          {stats['total_stars']:,}")
        print(f"  Forks:          {stats['total_forks']:,}")
        if stats['total_views']:
            print(f"  Seitenaufrufe:  {stats['total_views']:,}")
        if stats['total_clones']:
            print(f"  Clones:         {stats['total_clones']:,}")
        print(f"  Bericht:        {output_path}")

        logger.info(f"Analyse abgeschlossen: {stats['repos_analyzed']} Repos, "
              f"{stats['total_downloads']:,} Downloads")

        # ------------------------------------------------------------
        # 9) Report-Dialog
        # ------------------------------------------------------------
        switch_requested = False
        settings_changed = False

        if config.show_dialog:
            full_report_text = report.get_report_text()
            preview_text = build_report_preview(full_report_text, max_lines=80)

            file_info = (
                f"{'=' * 78}\n"
                f"  GitHub-Statistik-Bericht\n"
                f"{'=' * 78}\n"
                f"  Datei:      {Path(output_path).name}\n"
                f"  Vollpfad:   {output_path}\n"
                f"\n"
            )
            display_text = file_info + preview_text

            # Callbacks für Aktionen, die den Dialog NICHT schließen sollen
            def _on_info_clicked():
                show_info_dialog(dialog, release_info)
                # danach: Report-Dialog ist weiterhin offen

            def _on_settings_clicked():
                # Settings öffnen, OHNE Report-Dialog zu schließen
                saved = show_settings_dialog(dialog, config)
                if saved:
                    # Nach Settings-Speichern: Analyse neu starten
                    nonlocal settings_changed
                    settings_changed = True
                    dialog.accept()   # jetzt Report-Dialog schließen
                # sonst: Report-Dialog bleibt offen

            dialog = myUniversalDialog(
                None,
                "GitHub Multi-Repository Statistik",
                display_text,
                buttons=[
                    ("OK", "primary", "accept"),
                    ("Bericht öffnen", "success", "open"),
                    ("Ordner öffnen", "primary", "open_folder"),
                    ("Info", "primary", "info"),
                    ("Einstellungen", "primary", "settings"),
                    ("Benutzer wechseln…", "warning", "switch_user"),
                ],
                icon_type="",
                selectable_text=True,
                show_copy_button=True,
                text_alignment=Qt.AlignLeft,
                action_callbacks={
                    "info": _on_info_clicked,
                    "settings": _on_settings_clicked,
                }
            )

            @safe_slot
            def handle_dialog_result(_result=None):
                nonlocal switch_requested, settings_changed
                if dialog.result_value == "open":
                    import subprocess
                    import platform
                    try:
                        if platform.system() == "Windows":
                            os.startfile(str(output_path))
                        elif platform.system() == "Darwin":
                            subprocess.run(["open", str(output_path)])
                        else:
                            subprocess.run(["xdg-open", str(output_path)])
                    except Exception as e:
                        print(f"Fehler beim Öffnen der Datei: {e}")
                elif dialog.result_value == "open_folder":
                    try:
                        open_directory(output_path.parent)
                    except Exception as e:
                        print(f"Fehler beim Öffnen des Ordners: {e}")
                elif dialog.result_value == "switch_user":
                    switch_requested = True
                # "info" und "settings" werden jetzt per action_callbacks
                # behandelt und erreichen diesen Slot nicht mehr.

            dialog.finished.connect(handle_dialog_result)
            dialog.exec_()

        # ------------------------------------------------------------
        # 10) Nächste Runde?
        # ------------------------------------------------------------
        if settings_changed:
            previous_token = config.token
            # Log-Level neu anwenden (kann im Settings-Dialog geändert worden sein)
            apply_log_level(config, verbose_override=False)
            print("⚙️  Einstellungen wurden geändert – Neustart der Analyse.")
            continue
        elif switch_requested:
            force_user_selection = True
            previous_token = config.token
            continue
        else:
            break


    return 0


if __name__ == "__main__":
    sys.exit(main())
