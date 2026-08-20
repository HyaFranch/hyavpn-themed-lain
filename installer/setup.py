"""
hyavpn installer — by hyafranch
Baixa a última versão publicada no GitHub (exe + assets + audio), instala o
OpenVPN, cria atalho no Desktop. Única coisa que o usuário baixa manualmente.

Compilado como hyavpn-setup.exe (via PyInstaller, --uac-admin).
UI: webview (HTML/CSS/JS) — mesmo motor que o app principal.
"""

import os
import sys
import json
import shutil
import socket
import subprocess
import ssl
import tempfile
import threading
import time
import urllib.request
import urllib.error
import zipfile

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_REPO      = "HyaFranch/hyavpn-themed-lain"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DIST_ASSET_NAME  = "hyavpn-dist.zip"

INSTALL_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "hyavpn")
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", "."), "hyavpn")
EXE_NAME    = "hyavpn.exe"

OPENVPN_URL = "https://swupdate.openvpn.org/community/releases/OpenVPN-2.6.9-I001-amd64.msi"
OPENVPN_MSI = os.path.join(tempfile.gettempdir(), "openvpn-setup.msi")
DIST_ZIP_TMP = os.path.join(tempfile.gettempdir(), "hyavpn-dist.zip")


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    # When running as script, icons/ is one level up (repo root)
    candidate = os.path.join(base, relative_path)
    if not os.path.exists(candidate):
        parent = os.path.join(os.path.dirname(base), relative_path)
        if os.path.exists(parent):
            return parent
    return candidate


INSTALLER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>hyavpn setup</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #000000; --panel: #0a0005; --border: #3d0028;
    --pink: #ff2d78; --pink-dim: #5a0030; --green: #00ff41;
    --dim: #3a1a28; --red: #ff0033; --white: #f0d0dc;
    --font: 'Courier New', monospace;
  }
  html, body { width:100%; height:100%; overflow:hidden; background:var(--bg);
    color:var(--white); font-family:var(--font); user-select:none; }

  /* titlebar */
  #titlebar {
    height:36px; background:var(--panel); display:flex; align-items:center;
    -webkit-app-region:drag; app-region:drag;
  }
  .tb-dots { display:flex; align-items:center; gap:8px; padding:0 14px;
    -webkit-app-region:no-drag; app-region:no-drag; }
  .dot-btn { width:14px; height:14px; border-radius:50%; border:none; cursor:pointer; outline:none; }
  .dot-close { background:var(--pink); }
  .dot-close:hover { background:var(--red); }
  .dot-mini { background:transparent; border:2px solid var(--pink-dim); }
  .dot-mini:hover { border-color:var(--pink); }
  .tb-title { font-size:9px; color:var(--dim); letter-spacing:1px; margin-left:8px; }

  /* content */
  #content { display:flex; flex-direction:column; align-items:center; padding:20px 30px 24px; }
  h1 { font-size:28px; font-weight:bold; color:var(--pink); letter-spacing:3px; margin-bottom:4px; }
  .subtitle { font-size:9px; color:var(--dim); letter-spacing:1px; margin-bottom:16px; }
  .divider { width:100%; height:1px; background:var(--pink); margin:4px 0 16px; }

  #status { font-size:10px; color:var(--green); letter-spacing:1px; margin-bottom:8px; text-align:center; }

  /* log */
  #log { width:440px; height:160px; background:var(--panel); border:1px solid var(--border);
    border-radius:2px; padding:8px 10px; overflow-y:auto; font-size:8px; line-height:1.7; }
  #log::-webkit-scrollbar { width:3px; }
  #log::-webkit-scrollbar-thumb { background:var(--border); }
  .c-pink { color:var(--pink); } .c-green { color:var(--green); }
  .c-red { color:var(--red); }   .c-dim { color:var(--dim); }
  .log-line { display:block; }
  .ts { color:var(--dim); }

  /* progress */
  #progress-wrap { width:440px; height:4px; background:var(--border);
    border-radius:2px; margin:12px 0 4px; overflow:hidden; }
  #progress-bar { height:100%; background:var(--pink); width:0%;
    transition:width 0.4s ease; box-shadow:0 0 8px rgba(255,45,120,0.5); }

  /* open-after-install checkbox */
  #open-after-row {
    display:flex; align-items:center; gap:8px;
    width:440px; margin-top:12px;
    font-size:9px; color:var(--dim); letter-spacing:1px;
    cursor:pointer; user-select:none;
  }
  #open-after-row:hover { color:var(--white); }
  #open-after-row input[type="checkbox"] {
    width:12px; height:12px;
    accent-color:var(--pink);
    cursor:pointer;
  }

  /* button */
  #btn-install {
    margin-top:14px;
    width:200px; height:44px;
    background:var(--panel);
    border:1px solid var(--pink);
    border-radius:2px;
    color:var(--pink);
    font-family:var(--font);
    font-size:13px;
    font-weight:bold;
    letter-spacing:3px;
    cursor:pointer;
    transition:background 0.2s, box-shadow 0.2s;
  }
  #btn-install:hover:not(:disabled) { background:#150008; box-shadow:0 0 14px rgba(255,45,120,0.3); }
  #btn-install:disabled { border-color:var(--dim); color:var(--dim); cursor:default; }
</style>
</head>
<body>
<div id="titlebar">
  <div class="tb-dots">
    <button class="dot-btn dot-close" onclick="pywebview.api.close_window()" title="close"></button>
    <button class="dot-btn dot-mini"  onclick="pywebview.api.minimize_window()" title="minimize"></button>
  </div>
  <span class="tb-title">hyavpn setup</span>
</div>

<div id="content">
  <h1>hyavpn</h1>
  <div class="subtitle">by hyafranch  //  installer</div>
  <div class="divider"></div>

  <div id="status">ready to install.</div>

  <div id="log"></div>

  <div id="progress-wrap"><div id="progress-bar"></div></div>

  <label id="open-after-row">
    <input type="checkbox" id="chk-open-after" checked
           onchange="pywebview.api.set_open_after_install(this.checked)">
    <span>abrir hyavpn depois de instalar</span>
  </label>

  <button id="btn-install" onclick="pywebview.api.start_install()">[ INSTALL ]</button>
</div>

<script>
function addLog(msg, color) {
  const el = document.getElementById('log');
  const now = new Date();
  const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
  const line = document.createElement('span');
  line.className = `log-line c-${color||'dim'}`;
  line.innerHTML = `<span class="ts">[${ts}]</span> ${msg.replace(/</g,'&lt;')}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}
function setStatus(msg, color) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = color || 'var(--green)';
}
function setProgress(pct) {
  document.getElementById('progress-bar').style.width = pct + '%';
}
function setBtn(text, disabled) {
  const b = document.getElementById('btn-install');
  if (text) b.textContent = text;
  b.disabled = disabled;
  if (!disabled) b.onclick = disabled ? null : () => pywebview.api.start_install();
}
function onDone(closeText) {
  document.getElementById('btn-install').textContent = closeText || '[ CLOSE ]';
  document.getElementById('btn-install').disabled = false;
  document.getElementById('btn-install').onclick = () => pywebview.api.close_window();
}

window.installer = { addLog, setStatus, setProgress, setBtn, onDone };
</script>
</body>
</html>
"""


class InstallerApi:
    """JS API for the installer webview."""

    def __init__(self, wh):
        self._wh                 = wh
        self._release_info       = None
        self._skip_openvpn       = False
        self._open_after_install = True
        self._install_succeeded  = False

    @property
    def _win(self):
        return self._wh["win"]

    def _js(self, expr):
        if self._win:
            self._win.evaluate_js(expr)

    def _log(self, msg, color="dim"):
        safe = msg.replace("\\", "\\\\").replace("'", "\\'")
        self._js(f"installer.addLog('{safe}', '{color}')")

    def _status(self, msg, color="#00ff41"):
        safe = msg.replace("'", "\\'")
        self._js(f"installer.setStatus('{safe}', '{color}')")

    def _progress(self, pct):
        self._js(f"installer.setProgress({pct})")

    def close_window(self):
        if self._install_succeeded and self._open_after_install:
            try:
                exe_path = os.path.join(INSTALL_DIR, EXE_NAME)
                subprocess.Popen([exe_path], cwd=INSTALL_DIR)
            except Exception as e:
                self._log(f"failed to launch hyavpn: {e}", "red")
        if self._win:
            self._win.destroy()

    def set_open_after_install(self, checked: bool):
        self._open_after_install = bool(checked)

    def minimize_window(self):
        if self._win:
            self._win.minimize()

    def start_install(self):
        self._js("installer.setBtn('[ INSTALLING... ]', true)")
        threading.Thread(target=self._install, daemon=True).start()

    # ── Install steps ─────────────────────────────────────────────────────────
    def _install(self):
        steps = [
            ("creating directories",    self._step_dirs,              8),
            ("checking latest release", self._step_fetch_release,    20),
            ("downloading hyavpn",      self._step_download_dist,    45),
            ("installing files",        self._step_extract_dist,     58),
            ("checking openvpn",        self._step_openvpn,          72),
            ("installing openvpn",      self._step_openvpn_install,  88),
            ("creating shortcut",       self._step_shortcut,         98),
            ("done",                    None,                       100),
        ]
        for label, fn, pct in steps:
            self._status(f"// {label}...")
            self._log(label, "pink")
            self._progress(pct)
            if fn:
                try:
                    fn()
                except Exception as e:
                    self._log(f"error: {e}", "red")
                    self._status("installation failed.", "#ff2d78")
                    self._js("installer.onDone('[ RETRY ]')")
                    return

        self._install_succeeded = True
        self._log("installation complete.", "green")
        self._status("// INSTALLED SUCCESSFULLY", "#00ff41")
        self._js("installer.onDone('[ CLOSE ]')")

    def _step_dirs(self):
        os.makedirs(INSTALL_DIR, exist_ok=True)
        os.makedirs(APPDATA_DIR, exist_ok=True)
        self._log(f"install dir: {INSTALL_DIR}", "dim")

    def _github_get(self, url, timeout, retries=3):
        ctx      = ssl.create_default_context()
        last_err = None
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": "hyavpn-installer"})
            try:
                return urllib.request.urlopen(req, context=ctx, timeout=timeout)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (403, 429):
                    raise RuntimeError(
                        "GitHub API rate limit excedido pro seu IP. "
                        "Espere alguns minutos e tente de novo."
                    ) from e
                if e.code == 404:
                    raise RuntimeError(
                        f"nenhum Release em github.com/{GITHUB_REPO}/releases"
                    ) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
            if attempt < retries:
                self._log(f"tentativa {attempt}/{retries} falhou, retrying...", "dim")
                time.sleep(1.5 * attempt)
        raise RuntimeError(f"falha de rede: {last_err}") from last_err

    def _step_fetch_release(self):
        with self._github_get(GITHUB_API_LATEST, timeout=15) as r:
            data = json.loads(r.read())
        tag       = data.get("tag_name", "unknown")
        asset_url = None
        for a in data.get("assets", []):
            if a.get("name") == DIST_ASSET_NAME:
                asset_url = a.get("browser_download_url")
                break
        if not asset_url:
            raise RuntimeError(f"release {tag} found but no '{DIST_ASSET_NAME}' asset.")
        self._release_info = {"tag": tag, "asset_url": asset_url}
        self._log(f"latest version: {tag}", "green")

    def _step_download_dist(self):
        url = self._release_info["asset_url"]
        self._log(f"downloading {DIST_ASSET_NAME}...", "dim")
        with self._github_get(url, timeout=60) as r, open(DIST_ZIP_TMP, "wb") as f:
            shutil.copyfileobj(r, f)
        self._log("download complete.", "green")

    def _step_extract_dist(self):
        if os.path.exists(INSTALL_DIR):
            for item in os.listdir(INSTALL_DIR):
                p = os.path.join(INSTALL_DIR, item)
                try:
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                except Exception:
                    pass
        with zipfile.ZipFile(DIST_ZIP_TMP) as z:
            z.extractall(INSTALL_DIR)
        exe_path = os.path.join(INSTALL_DIR, EXE_NAME)
        if not os.path.exists(exe_path):
            raise RuntimeError(f"{EXE_NAME} not found after extracting.")
        self._log(f"installed to {INSTALL_DIR}", "green")

    def _step_openvpn(self):
        if os.path.exists(r"C:\Program Files\OpenVPN\bin\openvpn.exe"):
            self._log("openvpn already installed, skipping.", "dim")
            self._skip_openvpn = True
            return
        self._skip_openvpn = False
        self._log("downloading openvpn...", "dim")
        ctx = ssl.create_default_context()
        # urlretrieve manda o User-Agent padrão do Python (Python-urllib/x.y),
        # e o Cloudflare do swupdate.openvpn.org bloqueia isso com 403.
        # Usando Request com um User-Agent normal, igual o resto do arquivo já faz.
        req = urllib.request.Request(OPENVPN_URL, headers={"User-Agent": "hyavpn-installer"})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r, open(OPENVPN_MSI, "wb") as f:
            shutil.copyfileobj(r, f)
        self._log("download complete.", "green")

    def _step_openvpn_install(self):
        if self._skip_openvpn:
            self._log("openvpn already installed.", "dim")
            return
        self._log("installing openvpn silently (requires admin)...", "pink")
        subprocess.run(
            ["msiexec", "/i", OPENVPN_MSI, "/quiet", "/norestart", "ADDLOCAL=OpenVPN"],
            check=True,
        )
        self._log("openvpn installed.", "green")

    def _get_desktop_path(self):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            raw, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            path = os.path.expandvars(raw)
            if path:
                return path
        except Exception:
            pass
        return os.path.join(os.environ.get("USERPROFILE", "."), "Desktop")

    def _step_shortcut(self):
        exe_path = os.path.join(INSTALL_DIR, EXE_NAME)
        desktop  = self._get_desktop_path()
        os.makedirs(desktop, exist_ok=True)
        lnk_path = os.path.join(desktop, "hyavpn.lnk")
        ps_cmd = (
            f'$WS = New-Object -ComObject WScript.Shell; '
            f'$SC = $WS.CreateShortcut("{lnk_path}"); '
            f'$SC.TargetPath = "{exe_path}"; '
            f'$SC.WorkingDirectory = "{INSTALL_DIR}"; '
            f'$SC.IconLocation = "{exe_path}"; '
            f'$SC.Description = "hyavpn by hyafranch"; $SC.Save()'
        )
        r = subprocess.run(["powershell", "-Command", ps_cmd],
                           check=False, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(lnk_path):
            self._log(f"shortcut: {lnk_path}", "green")
        else:
            err = (r.stderr or r.stdout or "").strip()
            self._log(f"shortcut failed: {err[-150:]}", "red")


def _set_dpi_aware():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    import webview
    _set_dpi_aware()

    wh  = {"win": None}
    api = InstallerApi(wh)

    win = webview.create_window(
        "hyavpn setup",
        html             = INSTALLER_HTML,
        js_api           = api,
        width            = 500,
        height           = 476,
        resizable        = False,
        frameless        = True,
        background_color = "#000000",
    )
    wh["win"] = win

    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
