# 🌐 GBrowser

> A lightweight, privacy-focused web browser built with Python and PyQt6 — featuring tabbed browsing, built-in ad blocking, credential management, and DLL injection protection.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-6.x-green?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

## ✨ Features

### 🖥️ Modern Browser Experience
- **Tabbed Browsing** — Open multiple sites in tabs, drag to reorder, close with click
- **Smart URL Bar** — Type URLs or search queries directly
- **Navigation Controls** — Back, forward, reload, and home buttons
- **Dark Theme UI** — Easy on the eyes with a sleek dark interface

### 🔒 Privacy & Security
- **Built-in Ad Blocker** — Blocks 80+ ad networks and trackers at the request level
- **DLL Injection Protection** — Monitors and removes unauthorized DLLs in real-time
- **DPAPI Encryption** — Credentials encrypted with Windows Data Protection API
- **No Telemetry** — Zero data collection, everything stays local

### 📚 Bookmarks
- **Import from Browsers** — Load Netscape-format bookmarks.html from any browser
- **Folder Support** — Full hierarchy with nested folders
- **Bookmarks Bar** — Quick access with overflow menu for many bookmarks
- **Persistent Storage** — Bookmarks saved across sessions

### 🔑 Credential Manager
- **Auto-Fill** — Automatically fills saved login credentials
- **Auto-Capture** — Detects and saves new logins (with your permission)
- **Discord Support** — Special handling for React-based login forms
- **Secure Storage** — Encrypted using Windows DPAPI (user-level protection)

### 🎬 Media Support
- **Video Playback** — Full HTML5 video and WebGL support
- **Full Screen** — Native full-screen mode for media
- **Hardware Acceleration** — GPU-accelerated rendering enabled

---

## 🚀 Quick Start

### Prerequisites

```bash
pip install PyQt6 PyQt6-WebEngine beautifulsoup4 html5lib
```

### Run

```bash
python GBrowser.py
```

---

## 📸 Interface Overview

```
┌─────────────────────────────────────────────────────────────┐
│  [←] [→] [↻] [⌂] [+] [B]  │ 🔍 Search or enter address    │
├─────────────────────────────────────────────────────────────┤
│  [Social ▾] [Software ▾] [Dev ▾] [GitHub] [Stack...] [•••] │
├─────────────────────────────────────────────────────────────┤
│ Tab 1 │ Tab 2 │ Tab 3 │ + │                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                     Web Page Content                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| Element | Description |
|---------|-------------|
| `[←] [→]` | Navigate back/forward |
| `[↻]` | Reload current page |
| `[⌂]` | Go to home (Google) |
| `[+]` | Open new tab |
| `[B]` | Import bookmarks file |
| `[•••]` | Overflow menu for hidden bookmarks |

---

## 🛡️ Ad Blocker

GBrowser blocks requests to known ad and tracking domains before they load:

### Blocked Categories
- **Ad Networks** — Google Ads, DoubleClick, Facebook Ads, Amazon Ads, etc.
- **Analytics** — Google Analytics, Hotjar, Mixpanel, Segment, etc.
- **Social Trackers** — Facebook Pixel, Twitter Analytics, LinkedIn tracking
- **Annoyances** — Push notification services, popup networks

### Blocked Domains (80+)
```
doubleclick.net, googlesyndication.com, facebook.net, 
criteo.com, taboola.com, outbrain.com, hotjar.com,
mixpanel.com, segment.io, and many more...
```

### URL Pattern Blocking
```
/ads/, /adserver, /banner, /pixel, /tracking, /sponsored
```

---

## 🔐 Security Features

### DLL Injection Protection

GBrowser monitors for unauthorized DLL injections every 5 seconds:

1. **Baseline Capture** — Records all loaded DLLs at startup
2. **Continuous Monitoring** — Detects new DLLs loaded after startup
3. **Whitelist Filtering** — Ignores legitimate system/driver DLLs
4. **Auto-Removal** — Attempts to unload suspicious DLLs

**Whitelisted Patterns:**
- Windows system directories
- Python and PyQt6 libraries
- Graphics drivers (NVIDIA, AMD, Intel)
- .NET and Visual C++ runtimes

### Credential Encryption

Passwords are encrypted using Windows DPAPI:
- Tied to current Windows user account
- Cannot be decrypted by other users or on other machines
- Stored in `~/.gorstak_browser/credentials.json`

---

## 📁 Data Storage

All user data is stored in `~/.gorstak_browser/`:

```
~/.gorstak_browser/
├── CONFIG_FILE          # Window geometry, bookmarks, last URL
├── credentials.json     # Encrypted login credentials
├── storage/             # Persistent web storage, cookies
└── cache/               # Browser cache
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` (in URL bar) | Navigate to URL or search |
| `Ctrl+Click` | Open link in new tab |
| Click tab `×` | Close tab |
| Drag tab | Reorder tabs |

---

## 🔧 Configuration

### Changing Home Page

Edit line 472 in `GBrowser.py`:
```python
lambda: self._current_browser().setUrl(QUrl("https://www.google.com"))
```

### Disabling Ad Blocker

```python
self.ad_blocker.enabled = False
```

### Adding Custom Blocked Domains

Add to the `AD_DOMAINS` set at the top of the file:
```python
AD_DOMAINS = {
    "example-ad-network.com",
    # ... existing domains
}
```

---

## 📋 Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.10+ | Runtime |
| PyQt6 | 6.x | GUI framework |
| PyQt6-WebEngine | 6.x | Chromium-based web engine |
| beautifulsoup4 | 4.x | Bookmarks HTML parsing |
| html5lib | 1.x | HTML5 parser for BeautifulSoup |

---

## ⚠️ Known Limitations

- **Windows Only** — DLL protection and DPAPI encryption require Windows
- **No Extensions** — Does not support Chrome/Firefox extensions
- **No Sync** — Bookmarks and credentials are local only
- **GPU Test** — The "GPU benchmark" is actually CPU-bound matrix math

---

## 📄 License

This project is provided as-is for personal use.

---

## 👤 Author

**Gorstak**

---

<p align="center">
  <sub>Built with 🐍 Python + 💚 PyQt6</sub>
</p>
