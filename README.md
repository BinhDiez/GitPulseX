# GitPulseX

**GitHub Multi-Repository Statistik-Collector**

GitPulseX sammelt umfassende Statistiken über alle Repositories eines GitHub-Benutzers und erstellt einen übersichtlichen Bericht mit Downloads, Releases, Traffic, Followern und mehr.

![Version](https://img.shields.io/badge/version-2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

---

## 📋 Inhaltsverzeichnis

- [Features](#-features)
- [Screenshots](#-screenshots)
- [Installation](#-installation)
  - [Voraussetzungen](#voraussetzungen)
  - [Schritt 1: Repository klonen](#schritt-1-repository-klonen)
  - [Schritt 2: Virtuelle Umgebung](#schritt-2-virtuelle-umgebung)
  - [Schritt 3: Abhängigkeiten installieren](#schritt-3-abhängigkeiten-installieren)
- [Verwendung](#-verwendung)
  - [Erststart](#erststart)
  - [Kommandzeilen-Argumente](#kommandozeilen-argumente)
- [GitHub-Token erstellen](#-github-token-erstellen)
- [Konfiguration](#-konfiguration)
- [Verzeichnisstruktur](#-verzeichnisstruktur)
- [Als App bauen](#-als-app-bauen)
- [Fehlerbehebung](#-fehlerbehebung)
- [Lizenz](#-lizenz)
- [Autor](#-autor)

---

## ✨ Features

### 📊 Umfassende Analyse
- **Alle Repositories** eines GitHub-Benutzers auf einmal
- **Release-Details** mit Download-Zahlen und Downloads/Tag
- **Plattform-Verteilung** (Windows, macOS Intel/ARM, Linux, Android, BSD)
- **Top-Assets** nach Download-Zahl sortiert
- **Repository-Metriken**: Stars, Forks, Watchers, Contributors

### 📈 Traffic & Aktivität (mit Token)
- **Seitenaufrufe** der letzten 14 Tage
- **Clone-Statistiken** mit einzigartigen Clonern
- **Traffic-Quellen** (Top-Referrer)
- **Tagesverlauf** als Mini-Diagramm

### 👥 Follower-Analyse
- **Follower-Liste** mit Details (optional)
- **Geografische Verteilung** (Freitext-Feld)
- **Top-Unternehmen** der Follower
- **Einflussreichste Follower** nach eigenen Followern
- **Account-Alter** als Histogramm

### 🎨 Moderne Oberfläche
- **Dunkles Design** mit klarer Struktur
- **Progress-Dialog** mit Live-Log während der Analyse
- **Mehrere Benutzer** verwaltbar
- **Token-Verwaltung** pro Benutzer
- **Settings-Dialog** mit allen Optionen
- **Auto-Update-Check** für neue Releases
- **GitHub-Avatar** des ausgewählten Benutzers

### 🌍 Plattformübergreifend
- **macOS** (Intel + Apple Silicon)
- **Windows** 10/11
- **Linux** (alle gängigen Distributionen)
- **Plattformgerechte Pfade** via `platformdirs`

---

## 📸 Screenshots

*(Hier später Screenshots einfügen — Hauptdialog, Report, Settings)*

---

<details>
<summary>## 🚀 Installation</summary>

## 🚀 Installation

###Hier wird die Verwendung in einer Entwicklungsumgebung beschrieben.

###Wer das nicht möchte kann sich die fertigen Apps aus dem Release herunterladen.

### Voraussetzungen

- **Python 3.9** oder neuer
  - Prüfen: `python3 --version`
  - Download: [python.org](https://www.python.org/downloads/)
- **Internetverbindung** (für GitHub-API-Zugriffe)
- **GitHub-Konto** (für Token und Repositories)

### Schritt 1: Repository klonen

bash
git clone https://github.com/BinhDiez/GitPulseX.git
cd GitPulseX


Alternativ: Als ZIP herunterladen und entpacken.

### Schritt 2: Virtuelle Umgebung

**macOS / Linux:**

bash
python3 -m venv venv
source venv/bin/activate


**Windows:**

cmd
python -m venv venv
venv\Scripts\activate


### Schritt 3: Abhängigkeiten installieren

bash
pip install -r requirements.txt


Die `requirements.txt` enthält:
- `requests` – HTTP-Client für GitHub-API
- `PyQt5` – GUI-Framework
- `platformdirs` – plattformgerechte Verzeichnisse
</details>

---

<details>
<summary>## 💻 Verwendung</summary>

### Erststart

###Hier wird die Verwendung in einer Entwicklungsumgebung beschrieben.

###Wer das nicht möchte kann sich die fertigen Apps aus dem Release herunterladen.

**macOS / Linux:**

bash
python GitPulseX.py

**Windows:**

cmd
python GitPulseX.py

Beim ersten Start führt GitPulseX durch folgende Schritte:

1. **GitHub-Benutzername** eingeben
2. **GitHub-Token** eingeben (optional, aber empfohlen)
3. **Speicherort** für Berichte wählen
4. **Analyse** läuft automatisch

Nach der Analyse erscheint ein Bericht-Dialog mit einer Vorschau. Der vollständige Bericht wird in die Zieldatei geschrieben.

### Kommandozeilen-Argumente

bash
python GitPulseX.py [OPTIONEN]


| Argument | Beschreibung |
|---|---|
| `-o, --owner NAME` | GitHub-Benutzername (überschreibt gespeicherten) |
| `-t, --token TOKEN` | GitHub Personal Access Token |
| `-f, --output DATEI` | Ausgabedatei |
| `--no-page-views` | Seitenaufrufe nicht abfragen |
| `--no-traffic` | Traffic-Daten nicht abfragen |
| `--no-clones` | Clone-Daten nicht abfragen |
| `--no-dialog` | Keinen Dialog anzeigen (nur Datei schreiben) |
| `--include-forks` | Geforkte Repos einschließen |
| `--include-archived` | Archivierte Repos einschließen |
| `--include-private` | Private Repos einschließen |
| `--only-with-releases` | Nur Repos mit Releases |
| `--filter REGEX` | Filter für Repo-Namen (z. B. `^tool-`) |
| `--no-followers` | Follower nicht abfragen |
| `--followers-detail` | Details für jeden Follower (langsam!) |
| `-v, --verbose` | Ausführliche Ausgabe (DEBUG-Level) |
| `--log-level LEVEL` | Log-Level (DEBUG/INFO/WARNING/ERROR) |

**Beispiele:**

bash
# Nur Repos mit "tool" im Namen, ohne Follower-Abfrage
python GitPulseX.py --filter "tool" --no-followers

# Mit Token und ausführlicher Ausgabe
python GitPulseX.py -t ghp_xxxxx -v

# Nur die Datei schreiben, keinen Dialog
python GitPulseX.py --no-dialog
</details>

---

<details>
<summary>## 🔑 GitHub-Token erstellen</summary>

Ein Token ist **nicht zwingend erforderlich**, aber **stark empfohlen**.

**Ohne Token:** 60 API-Anfragen pro Stunde → reicht für kleine Accounts
**Mit Token:** 5.000 API-Anfragen pro Stunde → ausreichend für große Accounts

### Schritte

1. Öffne [github.com/settings/tokens](https://github.com/settings/tokens)
2. Klicke auf **Generate new token** → **Generate new token (classic)**
3. Name: z. B. `GitPulseX`
4. Ablaufdatum: 90 Tage (oder nach Wunsch)
5. **Scopes** wählen:
   - Für öffentliche Repos: **`public_repo`** (empfohlen)
   - Für private Repos: **`repo`**
6. Klicke auf **Generate token**
7. **Kopiere** den Token sofort (wird nur einmal angezeigt!)
8. Füge ihn in GitPulseX ein

**Sicherheit:** Der Token wird **lokal** in `settings/github_tokens.json` gespeichert (Klartext!). Bei Verdacht auf Missbrauch: Token auf GitHub widerrufen und neu erstellen.
</details>

---

<details>
<summary>### ⚙️ Konfiguration</summary>

Alle Einstellungen werden in `settings/github_stats_config.json` gespeichert und können **im Programm** über den **Einstellungen**-Button geändert werden.

| Einstellung | Standard | Beschreibung |
|---|---|---|
| `output_file` | `GitHub_all_repos_stats.txt` | Basis-Dateiname |
| `save_location` | `statistics` | `statistics`, `downloads` oder `""` (fragen) |
| `skip_forks` | `true` | Forks überspringen |
| `skip_archived` | `true` | Archivierte Repos überspringen |
| `skip_private` | `false` | Private Repos überspringen |
| `only_with_releases` | `false` | Nur Repos mit Releases |
| `repo_filter` | `""` | Regex-Filter für Repo-Namen |
| `include_page_views` | `true` | Seitenaufrufe abfragen |
| `include_traffic` | `true` | Traffic-Quellen abfragen |
| `include_clones` | `true` | Clone-Daten abfragen |
| `include_followers` | `true` | Follower-Liste abrufen |
| `followers_detail` | `false` | Follower-Details (langsam!) |
| `show_dialog` | `true` | Report-Dialog anzeigen |
| `log_level` | `INFO` | Log-Level |

**Manuell ändern:** Datei direkt bearbeiten, dann Programm neu starten.
</details>

---

<details>
<summary>## 📁 Verzeichnisstruktur</summary>

GitPulseX trennt sauber zwischen **Programm** und **Daten**:

### Entwicklungsmodus (Skript läuft direkt)


Github-API-Abfrage/
├── GitHub-API-Abfrage_03.py   ← Hauptskript
├── requirements.txt
├── README.md
├── assets/                     ← Icons
│   ├── BinhDiez.png
│   └── GitHub_API_Icon.png
├── logs/                       ← Logdateien
│   └── app.log
├── settings/                   ← Konfiguration
│   ├── github_stats_config.json
│   ├── github_users.json
│   └── github_tokens.json
└── statistics/                 ← Berichte
    └── GitHub_all_repos_stats_BinhDiez_2026-09-20.txt


### Bundle-Modus (gebaute App)

**macOS:**

~/Library/Application Support/GitPulseX/
├── logs/
├── settings/
└── statistics/


**Windows:**

%APPDATA%\GitPulseX\
├── logs\
├── settings\
└── statistics\


**Linux:**

~/.local/share/GitPulseX/
├── logs/
├── settings/
└── statistics/
</details>

---

<details>
<summary>## 📦 Als App bauen</summary>


GitPulseX kann mit **PyInstaller** in eine eigenständige App für Mac oder Windows verpackt werden. 

Oder lade einfach die App aus dem Release herunter.
</details>

---

<details>
<summary>## 🔧 Fehlerbehebung</summary>

### „Rate-Limit erreicht"

**Ursache:** GitHub erlaubt ohne Token nur 60 Anfragen/Stunde.

**Lösung:**
1. GitHub-Token erstellen (siehe oben)
2. Im Programm unter **Einstellungen** oder beim Token-Dialog eintragen

### „Keine Repositories gefunden"

**Mögliche Ursachen:**
- Alle Repos durch Filter ausgeschlossen (z. B. `skip_archived = true`)
- Benutzer hat keine Repos
- Benutzername falsch geschrieben

**Lösung:** **⚙️ Einstellungen** öffnen und Filter anpassen (z. B. `skip_archived → Nein`).

### „ModuleNotFoundError: platformdirs"

**Ursache:** Abhängigkeit nicht installiert.

**Lösung:**
bash
pip install -r requirements.txt


### Logdatei prüfen

Bei unerwartetem Verhalten hilft die Logdatei:

**Dev-Modus:** `logs/app.log`
**Bundle-Modus:** `~/Library/Application Support/GitPulseX/logs/app.log`

bash
tail -50 logs/app.log


### Icon wird nicht angezeigt

**Ursache:** `BinhDiez.png` und `GitPulseX.png` fehlen im `assets/`-Ordner.

**Lösung:** PNGs wiederherstellen oder durch eigene ersetzen (256×256 px empfohlen).
</details>

---

<details>
<summary>## 📄 Lizenz</summary>

Dieses Projekt ist unter der **MIT-Lizenz** lizenziert.


MIT License

Copyright (c) 2026 BinhDiez

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

PyQt5 Notice: This application uses PyQt5, which is licensed under the GNU General Public License v3 (GPLv3).
Copyright (c) Riverbank Computing Limited.
Full license text: https://www.gnu.org/licenses/gpl-3.0.html
</details>

---

## 👤 Autor

**BinhDiez**

- GitHub: [@BinhDiez](https://github.com/BinhDiez)
- Projekt: [GitPulseX](https://github.com/BinhDiez/GitPulseX)

---

## 🙏 Danksagungen

- **[PyQt5](https://pypi.org/project/PyQt5/)** – GUI-Framework
- **[requests](https://requests.readthedocs.io/)** – HTTP-Client
- **[platformdirs](https://pypi.org/project/platformdirs/)** – Plattform-Pfade
- **[PyInstaller](https://pyinstaller.org/)** – App-Packaging
- **[GitHub API](https://docs.github.com/en/rest)** – Datenquelle

---

<details>
<summary>## 🤝 Beitragen</summary>



Beiträge sind willkommen! Bitte:

1. **Fork** das Repository
2. **Branch** erstellen (`git checkout -b feature/neues-feature`)
3. **Commit** (`git commit -am 'Füge neues Feature hinzu'`)
4. **Push** (`git push origin feature/neues-feature`)
5. **Pull Request** öffnen

### Bugs & Wünsche

Bitte als [Issue](https://github.com/BinhDiez/GitPulseX/issues) melden.

---

## ⭐ Unterstützung

Wenn GitPulseX dir hilft, freue ich mich über einen **Star** auf GitHub!

---

**Viel Erfolg bei der Analyse deiner Repositories! 🚀**
</details>

---

<details>
<summary>🔒 macOS Gatekeeper Info</summary>


GitPulseX is currently not signed with an Apple Developer certificate.

When starting the app for the first time, macOS Gatekeeper may block the app from running.

1. Open the app once.
2. Close the warning.
3. **System Settings → Privacy & Security**
4. Scroll all the way down to the warning "GitPulseX was blocked..." 
5. Select **“Open Anyway”**
6. If you are warned again: select **“Open Anyway”** again and confirm with your password.

### Alternatively, remove the quarantine attribute:

🍎 macOS Terminal

xattr -d com.apple.quarantine '/Users/username/Downloads/GitPulseX.app'

> Please adjust the file path accordingly.

</details>

---

<details>
<summary>🖥️ Download-Info</summary>

### Download-Versiones

| Suffix | Betriebssystem |
|--------|-----------------|
| `_macOS_as` | Apple Silicon (M1–M4) |
| `_macOS_intel` | Intel Macs |

### Extract 7z-Archive

| Betriebssystem | Empfohlene App |
|---------------|----------------|
| 🍎 macOS | **Keka** – <https://www.keka.io/> |
| 🪟 Windows | **7-Zip** – <https://www.7-zip.org/> |

</details>

---

<details>
<summary>🔑 7z Password</summary>

**BinhDiez**

</details>

