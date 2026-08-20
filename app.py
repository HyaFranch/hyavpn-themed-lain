"""
hyavpn — by hyafranch
Estética: Accela / Serial Experiments Lain
Preto + rosa/magenta, terminal verde, personagem sketch

Motor de UI: webview  (HTML/CSS/JS no lugar de customtkinter)
"""

import os
import sys
import json
import math
import base64
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import zipfile

# ── Versão / Auto-update ─────────────────────────────────────────────────────
__version__ = "1.6.7"
GITHUB_REPO        = "HyaFranch/hyavpn-themed-lain"
GITHUB_API_LATEST  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_ASSET_NAME  = "hyavpn-dist.zip"

# ── Instância única ──────────────────────────────────────────────────────────
_SINGLE_INSTANCE_PORT   = 51737
_single_instance_socket = None


def _ssl_context() -> ssl.SSLContext:
    """Cria um contexto SSL usando o bundle de CAs do certifi.

    Corrige o erro `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify
    failed: unable to get local issuer certificate`. Ele acontece porque o
    Python embutido no .exe do PyInstaller usa `ssl.create_default_context()`,
    que no Windows depende do keystore de certificados do sistema — e esse
    keystore muitas vezes não tem (ou o processo empacotado não enxerga) a CA
    raiz necessária pra validar o certificado do GitHub/riseup.net. Usar o
    cacert.pem do pacote `certifi` resolve isso de forma independente do SO.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def resource_path(relative_path: str) -> str:
    """Resolve um caminho de recurso tanto como script quanto PyInstaller --onefile.

    No --onefile, sys._MEIPASS é a pasta temporária de extração. Mas "assets/"
    (e "ui/") não são embutidos com --add-data no build (ver release.yml) —
    eles são copiados ao lado do hyavpn.exe. Por isso, se o caminho não existir
    dentro de _MEIPASS, cai para a pasta do executável.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(base, relative_path)
    if not os.path.exists(candidate) and getattr(sys, "frozen", False):
        alt = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(alt):
            return alt
    return candidate


# ── Audio ─────────────────────────────────────────────────────────────────────
_AUDIO_ERROR = None
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    AUDIO = True
except Exception as e:
    AUDIO = False
    _AUDIO_ERROR = f"{type(e).__name__}: {e}"


# ── Split tunneling ───────────────────────────────────────────────────────────
SPLIT_TUNNEL_DOMAINS = [
    "discord.com",
    "discordapp.com",
    "discord.gg",
    "gateway.discord.gg",
    "cdn.discordapp.com",
    "media.discordapp.net",
]


# ── Auto-update helpers ───────────────────────────────────────────────────────
def _version_tuple(v: str):
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def check_for_update():
    import urllib.request
    ctx = _ssl_context()
    try:
        req = urllib.request.Request(GITHUB_API_LATEST, headers={"User-Agent": "hyavpn-updater"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = json.loads(r.read())
        tag       = data.get("tag_name", "")
        asset_url = None
        for a in data.get("assets", []):
            if a.get("name") == UPDATE_ASSET_NAME:
                asset_url = a.get("browser_download_url")
                break
        return {
            "tag":        tag,
            "has_update": _version_tuple(tag) > _version_tuple(__version__),
            "asset_url":  asset_url,
            "notes":      (data.get("body") or "").strip()[:300],
        }
    except Exception as e:
        return {"error": str(e)}


# ── VPN Manager ───────────────────────────────────────────────────────────────
class VPNManager:
    CONFIG_DIR      = os.path.join(os.environ.get("APPDATA", "."), "hyavpn")
    OVPN_FILE       = os.path.join(CONFIG_DIR, "hyavpn.ovpn")
    CA_FILE         = os.path.join(CONFIG_DIR, "ca.crt")
    SPLIT_OVPN_FILE = os.path.join(CONFIG_DIR, "hyavpn_split.ovpn")
    SETTINGS_FILE   = os.path.join(CONFIG_DIR, "settings.json")
    PROVIDER_URL    = "https://riseup.net/provider.json"

    def __init__(self, log_fn):
        self.log  = log_fn
        self._proc = None
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        self.split_tunnel     = self._load_split_tunnel_pref()
        self.discord_delay_s  = self._load_discord_delay()
        self.vpn_hold_s       = self._load_vpn_hold()

    # ── Prefs ────────────────────────────────────────────────────────────────
    def _load_split_tunnel_pref(self) -> bool:
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("split_tunnel", True))
        except Exception:
            return True

    def _load_discord_delay(self) -> int:
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                return int(json.load(f).get("discord_delay", 2))
        except Exception:
            return 2

    def _load_vpn_hold(self) -> int:
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                return int(json.load(f).get("vpn_hold", 5))
        except Exception:
            return 5

    def _save_settings(self):
        try:
            data = {}
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["split_tunnel"]   = self.split_tunnel
            data["discord_delay"]  = self.discord_delay_s
            data["vpn_hold"]       = self.vpn_hold_s
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            self.log(f"failed to save settings: {e}", "red")

    def set_split_tunnel(self, enabled: bool):
        self.split_tunnel = bool(enabled)
        self._save_settings()

    def set_discord_delay(self, seconds: int):
        self.discord_delay_s = max(2, min(30, int(seconds)))
        self._save_settings()

    def set_vpn_hold(self, seconds: int):
        self.vpn_hold_s = max(2, min(60, int(seconds)))
        self._save_settings()

    # ── Config ───────────────────────────────────────────────────────────────
    def _ovpn_is_stale(self) -> bool:
        try:
            with open(self.OVPN_FILE, "r", encoding="utf-8") as f:
                cfg = f.read()
        except Exception:
            return True
        for line in cfg.splitlines():
            s = line.strip()
            if (s.startswith("ca ") or s.startswith("cert ") or s.startswith("key ")) and "\\" in s:
                return True
        return False

    def setup(self) -> bool:
        import urllib.request
        ctx  = _ssl_context()

        self.log("fetching provider.json...", "pink")
        try:
            with urllib.request.urlopen(self.PROVIDER_URL, context=ctx, timeout=10) as r:
                provider = json.loads(r.read())
        except Exception as e:
            self.log(f"provider fetch failed: {e}", "red")
            return False

        api_uri = provider.get("api_uri",     "https://api.black.riseup.net")
        ca_uri  = provider.get("ca_cert_uri", "https://black.riseup.net/ca.crt")
        api_ver = provider.get("api_version", "3")
        self.log(f"api: {api_uri}", "dim")

        self.log("fetching CA certificate...", "pink")
        try:
            with urllib.request.urlopen(ca_uri, context=ctx, timeout=10) as r:
                ca_data = r.read()
            with open(self.CA_FILE, "wb") as f:
                f.write(ca_data)
        except Exception as e:
            self.log(f"ca fetch failed: {e}", "red")
            return False

        eip_url = f"{api_uri}/{api_ver}/config/eip-service.json"
        self.log("fetching gateway list...", "pink")
        try:
            ctx2 = ssl.create_default_context()
            ctx2.check_hostname = False
            ctx2.verify_mode    = ssl.CERT_NONE
            with urllib.request.urlopen(eip_url, context=ctx2, timeout=10) as r:
                eip = json.loads(r.read())
        except Exception as e:
            self.log(f"eip fetch failed: {e}", "red")
            return False

        gateways = eip.get("gateways", [])
        if not gateways:
            self.log("no gateways found.", "red")
            return False

        gw = None
        for g in gateways:
            for t in g.get("capabilities", {}).get("transport", []):
                if t.get("type") == "openvpn":
                    gw = {
                        "ip":    g["ip_address"],
                        "port":  t.get("ports",     ["1194"])[0],
                        "proto": t.get("protocols", ["udp"])[0],
                    }
                    break
            if gw:
                break

        if not gw:
            self.log("no openvpn gateway available.", "red")
            return False

        self.log(f"gateway: {gw['ip']}:{gw['port']}/{gw['proto']}", "green")

        cert_url = f"{api_uri}/{api_ver}/cert"
        self.log("requesting client certificate...", "pink")
        try:
            import urllib.request as urlreq
            req = urlreq.Request(cert_url, method="POST", data=b"")
            with urlreq.urlopen(req, context=ctx2, timeout=15) as r:
                cert_pem = r.read().decode()
        except Exception as e:
            self.log(f"cert fetch failed: {e}", "red")
            return False

        cert_file = os.path.join(self.CONFIG_DIR, "client.pem")
        with open(cert_file, "w", encoding="utf-8") as f:
            f.write(cert_pem)

        ovpn_cfg   = eip.get("openvpn_configuration", {})
        cipher     = ovpn_cfg.get("cipher",     "AES-256-CBC")
        auth       = ovpn_cfg.get("auth",       "SHA256")
        tls_cipher = ovpn_cfg.get("tls-cipher", "")

        ca_path   = self.CA_FILE.replace("\\", "/")
        cert_path = cert_file.replace("\\", "/")

        ovpn = (
            f"client\ndev tun\nproto {gw['proto']}\n"
            f"remote {gw['ip']} {gw['port']}\n"
            "resolv-retry infinite\nnobind\npersist-key\npersist-tun\n"
            f'ca "{ca_path}"\ncert "{cert_path}"\nkey "{cert_path}"\n'
            f"cipher {cipher}\nauth {auth}\nverb 1\nmute 3\nscript-security 1\n"
        )
        if tls_cipher:
            ovpn += f"tls-cipher {tls_cipher}\n"

        with open(self.OVPN_FILE, "w", encoding="utf-8") as f:
            f.write(ovpn)

        self.log("config ready.", "green")
        return True

    def _build_split_tunnel_config(self):
        self.log("resolving discord ip ranges...", "pink")
        ips = set()
        for domain in SPLIT_TUNNEL_DOMAINS:
            try:
                _, _, addrs = socket.gethostbyname_ex(domain)
                ips.update(addrs)
            except Exception as e:
                self.log(f"dns lookup failed for {domain}: {e}", "dim")

        if not ips:
            self.log("no discord ips resolved, aborting split tunnel.", "red")
            return None

        try:
            with open(self.OVPN_FILE, "r", encoding="utf-8") as f:
                base_cfg = f.read().rstrip()
        except Exception as e:
            self.log(f"failed to read base config: {e}", "red")
            return None

        lines = [base_cfg, "", "# -- split tunneling --", "route-nopull"]
        for ip in sorted(ips):
            lines.append(f"route {ip} 255.255.255.255 vpn_gateway")

        try:
            with open(self.SPLIT_OVPN_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            self.log(f"failed to write split config: {e}", "red")
            return None

        self.log(f"split tunnel: {len(ips)} discord ip(s) routed via vpn.", "green")
        return self.SPLIT_OVPN_FILE

    # ── Connect / Disconnect ──────────────────────────────────────────────────
    def connect(self) -> bool:
        openvpn = self._find_openvpn()
        if not openvpn:
            self.log("openvpn.exe not found. run the installer first.", "red")
            return False
        if not os.path.exists(self.OVPN_FILE) or self._ovpn_is_stale():
            self.log("config missing or outdated, regenerating...", "pink")
            if not self.setup():
                return False

        config_path = self.OVPN_FILE
        if self.split_tunnel:
            split_path = self._build_split_tunnel_config()
            if split_path:
                config_path = split_path
            else:
                self.log("falling back to full tunnel.", "dim")

        try:
            self._proc = subprocess.Popen(
                [openvpn, "--config", config_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self.log(f"openvpn started (pid {self._proc.pid})", "green")
            return True
        except Exception as e:
            self.log(f"failed to start openvpn: {e}", "red")
            return False

    def wait_connected(self, timeout: int = 30) -> bool:
        if not self._proc:
            return False
        start = time.time()
        while time.time() - start < timeout:
            line = self._proc.stdout.readline()
            if not line:
                break
            decoded = line.decode(errors="ignore").strip()
            if decoded:
                self.log(decoded[:72], "dim")
            if "Initialization Sequence Completed" in decoded:
                return True
            if self._proc.poll() is not None:
                break
        return False

    def disconnect(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                pass
            self._proc = None
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                try:
                    if "openvpn" in p.info["name"].lower():
                        p.terminate()
                except Exception:
                    pass
        except ImportError:
            pass
        self.log("vpn disconnected.", "dim")

    def _find_openvpn(self):
        local = os.path.join(os.path.dirname(sys.executable), "openvpn", "openvpn.exe")
        if os.path.exists(local):
            return local
        for p in [
            r"C:\Program Files\OpenVPN\bin\openvpn.exe",
            r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
            os.path.join(self.CONFIG_DIR, "openvpn", "openvpn.exe"),
        ]:
            if os.path.exists(p):
                return p
        return shutil.which("openvpn")


# ── JS API (exposed to webview) ───────────────────────────────────────────────
class JsApi:
    """Methods here are callable from JS as webview.api.<method>(...)."""

    def __init__(self, window_ref_holder):
        # We receive a mutable holder so we can swap the window reference
        # after webview creates it (webview.create_window returns after init).
        self._wh        = window_ref_holder   # {"win": None}
        self._vpn       = None                # set after init
        self._update_info = None
        self._discord_delay = 2

    @property
    def _win(self):
        return self._wh["win"]

    def _js(self, expr: str):
        """Evaluate JS in the webview (thread-safe via evaluate_js)."""
        if self._win:
            self._win.evaluate_js(expr)

    def _log(self, msg: str, color: str = "dim"):
        # escape single quotes for JS string literal
        safe = msg.replace("\\", "\\\\").replace("'", "\\'")
        self._js(f"hyavpn.addLog('{safe}', '{color}')")

    def _set_state(self, state: str):
        self._js(f"hyavpn.setState('{state}')")

    # ── Window controls ───────────────────────────────────────────────────────
    def close_window(self):
        try:
            if self._vpn:
                self._vpn.disconnect()
        except Exception:
            pass
        if self._win:
            self._win.destroy()

    def minimize_window(self):
        if self._win:
            self._win.minimize()

    # ── VPN settings ──────────────────────────────────────────────────────────
    def get_split_tunnel(self) -> bool:
        return self._vpn.split_tunnel if self._vpn else False

    def set_split_tunnel(self, enabled: bool):
        if self._vpn:
            self._vpn.set_split_tunnel(bool(enabled))

    def get_delay(self) -> int:
        return self._vpn.discord_delay_s if self._vpn else 10

    def set_delay(self, seconds: int):
        if self._vpn:
            self._vpn.set_discord_delay(int(seconds))
        self._discord_delay = int(seconds)

    def get_vpn_hold(self) -> int:
        return self._vpn.vpn_hold_s if self._vpn else 5

    def set_vpn_hold(self, seconds: int):
        if self._vpn:
            self._vpn.set_vpn_hold(int(seconds))

    def refresh_config(self):
        if not self._vpn:
            return
        def run():
            ok = self._vpn.setup()
            self._log("config refreshed." if ok else "config refresh failed.", "green" if ok else "red")
        threading.Thread(target=run, daemon=True).start()

    # ── Main bypass flow ───────────────────────────────────────────────────────
    def start_bypass(self):
        threading.Thread(target=self._flow, daemon=True).start()

    def _flow(self):
        self._set_state("connecting")
        self._play("connecting")
        self._log("initiating bypass...", "pink")

        if not os.path.exists(self._vpn.OVPN_FILE) or self._vpn._ovpn_is_stale():
            self._log("fetching riseup config...", "dim")
            if not self._vpn.setup():
                self._log("setup failed.", "red")
                self._set_state("idle")
                return

        self._log("connecting to vpn...", "pink")
        if not self._vpn.connect():
            self._set_state("idle")
            return

        self._log("waiting for tunnel...", "dim")
        ok = self._vpn.wait_connected(timeout=40)
        if not ok:
            self._log("tunnel timeout.", "red")
            self._vpn.disconnect()
            self._set_state("idle")
            return

        self._set_state("connected")
        self._log("tunnel active.", "green")
        self._play("connected")
        time.sleep(1.5)

        self._log("killing discord...", "dim")
        self._kill_discord()
        time.sleep(self._vpn.discord_delay_s)

        self._log("relaunching discord...", "dim")
        self._open_discord()

        self._log("waiting for discord...", "dim")
        disc_ok = self._wait_discord(25)
        if disc_ok:
            self._log("discord is up.", "green")
        else:
            self._log("discord took too long.", "red")

        hold_s = self._vpn.vpn_hold_s
        self._log(f"holding tunnel {hold_s}s more...", "dim")
        time.sleep(hold_s)

        self._log("releasing tunnel...", "dim")
        self._vpn.disconnect()

        self._set_state("success")
        self._play("success")

    # ── Discord helpers ───────────────────────────────────────────────────────
    def _kill_discord(self):
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                try:
                    if "discord" in p.info["name"].lower():
                        p.terminate()
                except Exception:
                    pass
        except ImportError:
            pass
        time.sleep(1)

    def _open_discord(self):
        local = os.path.expanduser(r"~\AppData\Local\Discord")
        if os.path.exists(local):
            for root, _, files in os.walk(local):
                for f in files:
                    if f.lower() == "discord.exe":
                        subprocess.Popen([os.path.join(root, f)])
                        return
        self._log("discord.exe not found.", "red")

    def _wait_discord(self, timeout: int) -> bool:
        end = time.time() + timeout
        try:
            import psutil
            while time.time() < end:
                for p in psutil.process_iter(["name"]):
                    try:
                        if "discord" in p.info["name"].lower():
                            return True
                    except Exception:
                        pass
                time.sleep(1)
        except ImportError:
            pass
        return False

    # ── Audio ─────────────────────────────────────────────────────────────────
    def _play(self, name: str):
        if not AUDIO:
            return
        path = resource_path(os.path.join("audio", f"{name}.mp3"))
        if not os.path.exists(path):
            self._log(f"audio file not found: {path}", "red")
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except Exception as e:
            self._log(f"audio playback failed ({name}): {e}", "red")

    # ── Overlay close ─────────────────────────────────────────────────────────
    def reset_to_idle(self):
        self._set_state("idle")

    def _get_desktop_path(self):
        """Resolve o caminho real da área de trabalho (mesma lógica do installer)."""
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

    # ── Uninstall ────────────────────────────────────────────────────────────
    def uninstall(self):
        """Desinstala o hyavpn: derruba a vpn, apaga configs e remove a pasta
        de instalação. A confirmação deve ser feita no JS (confirm()) antes
        de chamar pywebview.api.uninstall(), já que aqui é irreversível."""
        threading.Thread(target=self._do_uninstall, daemon=True).start()

    def _do_uninstall(self):
        self._log("desinstalando hyavpn...", "red")

        try:
            if self._vpn:
                self._vpn.disconnect()
        except Exception:
            pass

        # mata qualquer openvpn.exe residual
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                try:
                    if "openvpn" in p.info["name"].lower():
                        p.terminate()
                except Exception:
                    pass
        except ImportError:
            pass

        # remove configs/certs (%APPDATA%\hyavpn)
        try:
            if self._vpn and os.path.isdir(self._vpn.CONFIG_DIR):
                shutil.rmtree(self._vpn.CONFIG_DIR, ignore_errors=True)
        except Exception as e:
            self._log(f"falha ao remover configs: {e}", "red")

        # remove o atalho criado pelo installer na área de trabalho
        try:
            desktop = self._get_desktop_path()
            lnk = os.path.join(desktop, "hyavpn.lnk")
            if os.path.exists(lnk):
                os.remove(lnk)
        except Exception as e:
            self._log(f"falha ao remover atalho: {e}", "dim")

        if getattr(sys, "frozen", False):
            install_dir = os.path.dirname(sys.executable)
        else:
            install_dir = os.path.dirname(os.path.abspath(__file__))

        # apaga a pasta de instalação depois que o processo fechar
        # (mesmo truque do auto-update: um .bat espera o pid morrer)
        pid      = os.getpid()
        bat_path = os.path.join(tempfile.gettempdir(), "hyavpn_uninstall.bat")
        bat = (
            f"@echo off\n:wait\n"
            f'tasklist /fi "PID eq {pid}" | find "{pid}" >nul\n'
            "if not errorlevel 1 (\n  timeout /t 1 /nobreak >nul\n  goto wait\n)\n"
            f'rmdir /s /q "{install_dir}"\n'
            f"del \"%~f0\"\n"
        )
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat)
            self._log("hyavpn será removido e o app vai fechar...", "green")
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            time.sleep(0.6)
            if self._win:
                self._win.destroy()
        except Exception as e:
            self._log(f"falha ao desinstalar: {e}", "red")

    # ── Update ────────────────────────────────────────────────────────────────
    def check_updates(self):
        self._log("checking for updates...", "pink")
        def run():
            info = check_for_update()
            self._update_info = info
            if not info or info.get("error"):
                err = info.get("error") if info else "unknown"
                self._log(f"update check failed: {err}", "red")
                return
            if not info.get("has_update"):
                self._log(f"already on the latest version (v{__version__}).", "green")
                return
            if not info.get("asset_url"):
                self._log(f"update {info['tag']} found but no installable asset.", "dim")
                return
            self._log(f"update {info['tag']} available.", "pink")
            self._js("hyavpn.showUpdateBadge()")
        threading.Thread(target=run, daemon=True).start()

    def apply_update(self):
        if not self._update_info or not self._update_info.get("asset_url"):
            self.check_updates()
            return
        threading.Thread(target=self._do_apply_update, args=(self._update_info,), daemon=True).start()

    def _do_apply_update(self, info):
        import urllib.request
        asset_url = info["asset_url"]
        tmp_zip   = os.path.join(tempfile.gettempdir(), "hyavpn_update.zip")
        tmp_dir   = os.path.join(tempfile.gettempdir(), "hyavpn_update_extract")

        try:
            ctx = _ssl_context()
            req = urllib.request.Request(asset_url, headers={"User-Agent": "hyavpn-updater"})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r, open(tmp_zip, "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            with zipfile.ZipFile(tmp_zip) as z:
                z.extractall(tmp_dir)
        except Exception as e:
            self._log(f"update download failed: {e}", "red")
            return

        if getattr(sys, "frozen", False):
            install_dir = os.path.dirname(sys.executable)
            exe_name    = os.path.basename(sys.executable)
        else:
            install_dir = os.path.dirname(os.path.abspath(__file__))
            exe_name    = None

        pid      = os.getpid()
        bat_path = os.path.join(tempfile.gettempdir(), "hyavpn_updater.bat")
        relaunch = f'start "" "{os.path.join(install_dir, exe_name)}"' if exe_name else "rem rodando via script — reabra manualmente"

        bat = (
            f"@echo off\n:wait\n"
            f'tasklist /fi "PID eq {pid}" | find "{pid}" >nul\n'
            "if not errorlevel 1 (\n  timeout /t 1 /nobreak >nul\n  goto wait\n)\n"
            f'xcopy /y /e /i "{tmp_dir}\\*" "{install_dir}\\" >nul\n'
            f"{relaunch}\ndel \"%~f0\"\n"
        )
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat)
            self._log(f"update {info['tag']} ready — restarting...", "green")
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            time.sleep(0.6)
            if self._win:
                self._win.destroy()
        except Exception as e:
            self._log(f"failed to schedule update: {e}", "red")

    # ── Background update check (called after window loads) ───────────────────
    def _bg_update_check(self):
        time.sleep(1.5)
        info = check_for_update()
        self._update_info = info
        if not info:
            return
        if info.get("error"):
            self._log(f"update check: {info['error']}", "dim")
            return
        if info.get("has_update"):
            self._log(f"update available: {info['tag']} (current v{__version__})", "pink")
            self._js("hyavpn.showUpdateBadge()")
        else:
            self._log("hyavpn is up to date.", "dim")


# ── Single instance lock ──────────────────────────────────────────────────────
def acquire_single_instance_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


# ── Admin elevation (Windows) ────────────────────────────────────────────────
def _ensure_admin():
    if sys.platform != "win32":
        return
    import ctypes
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = True
    if is_admin:
        return
    try:
        if getattr(sys, "frozen", False):
            target, params = sys.executable, ""
        else:
            target = sys.executable
            params = subprocess.list2cmdline([os.path.abspath(__file__)] + sys.argv[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
        if rc > 32:
            sys.exit(0)
    except Exception:
        pass


# ── HTML loader ───────────────────────────────────────────────────────────────
def _build_html() -> str:
    """Inject runtime constants (version, asset paths) into the HTML before serving."""
    html_path = resource_path(os.path.join("ui", "index.html"))
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Build asset URLs as embedded data: URIs (base64).
    # Quando o HTML é passado via `html=` para create_window (string em memória,
    # não um arquivo), a página não tem origem file:// própria — e o WebView2/
    # Chromium bloqueia o carregamento de recursos file:// referenciados por uma
    # página assim, mesmo com o caminho absoluto correto (foi o que causou o
    # GIF continuar quebrado depois de trocarmos pra file://). Embutindo o GIF
    # direto como data:image/gif;base64,... não depende de origem nenhuma —
    # funciona igual rodando `python app.py` ou no .exe do PyInstaller.
    def _asset_url(rel):
        p = resource_path(rel)
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/gif;base64,{b64}"

    inject = f"""<script>
window._HYAVPN_VERSION = '{__version__}';
window._HYAVPN_ASSETS = {{
  idle:       '{_asset_url("assets/idle.gif")}',
  connecting: '{_asset_url("assets/connecting.gif")}',
  connected:  '{_asset_url("assets/connected.gif")}',
}};
</script>"""

    # Insert before </head>
    return html.replace("</head>", inject + "\n</head>")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    import webview

    _ensure_admin()

    _single_instance_socket = acquire_single_instance_lock()
    if _single_instance_socket is None:
        import tkinter as tk
        import tkinter.messagebox as messagebox
        _r = tk.Tk()
        _r.withdraw()
        messagebox.showwarning(
            "hyavpn",
            "hyavpn já está em execução.\n\n"
            "só é permitida uma instância por vez, pra evitar\n"
            "abrir duas conexões vpn ao mesmo tempo.",
        )
        _r.destroy()
        return

    # Window holder (mutable ref so JsApi can grab it after create_window returns)
    wh = {"win": None}

    api = JsApi(wh)

    # VPN manager shares the same log fn
    api._vpn = VPNManager(api._log)
    api._discord_delay = api._vpn.discord_delay_s

    html       = _build_html()
    base_dir   = resource_path("")  # app root for resolving relative asset URLs

    win = webview.create_window(
        "hyavpn",
        html       = html,
        js_api     = api,
        width      = 440,
        height     = 640,
        resizable  = False,
        frameless  = True,         # no native chrome — our custom titlebar handles it
        on_top     = True,          # fica por cima de todos os apps quando não minimizada
        background_color = "#000000",
        min_size   = (440, 640),
    )
    wh["win"] = win

    def on_loaded():
        # Log initial messages
        api._log("hyavpn initialised.", "green")
        if not AUDIO:
            api._log(f"audio disabled: {_AUDIO_ERROR}", "red")
        api._log("press AUTO BYPASS to start.", "dim")
        # Background update check
        threading.Thread(target=api._bg_update_check, daemon=True).start()

    win.events.loaded += on_loaded

    # webview.start() blocks until all windows are closed
    webview.start(
        debug         = ("--debug" in sys.argv),
        # On Windows, use edgechromium (WebView2) for best rendering
        # Falls back to mshtml if not available, or gtk/qt on Linux/macOS
    )


if __name__ == "__main__":
    main()
