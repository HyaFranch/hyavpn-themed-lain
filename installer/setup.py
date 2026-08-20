"""
hyavpn installer — by hyafranch
Baixa a última versão publicada no GitHub (exe + assets + audio), instala o
OpenVPN, cria atalho no Desktop. Essa é a ÚNICA coisa que o usuário baixa
manualmente — tudo o mais vem do GitHub Releases em tempo de instalação.

Compilado como hyavpn-setup.exe (via PyInstaller, --uac-admin), então já
pede elevação de administrador sozinho ao abrir — não precisa "executar
como administrador" manualmente.
"""

import os, sys, subprocess, shutil, urllib.request, ssl, json, zipfile, tempfile, winreg
import tkinter as tk
from tkinter import ttk
import threading

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_REPO = "HyaFranch/hyavpn-themed-lain"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DIST_ASSET_NAME = "hyavpn-dist.zip"   # asset publicado em cada Release (exe + assets/ + audio/)

INSTALL_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "hyavpn")
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", "."), "hyavpn")
EXE_NAME    = "hyavpn.exe"

# OpenVPN installer (versão community, silenciosa)
OPENVPN_URL = "https://swupdate.openvpn.org/community/releases/OpenVPN-2.6.9-I001-amd64.msi"
OPENVPN_MSI = os.path.join(tempfile.gettempdir(), "openvpn-setup.msi")

DIST_ZIP_TMP = os.path.join(tempfile.gettempdir(), "hyavpn-dist.zip")

PINK     = "#ff2d78"
PINK_DIM = "#8a0038"
BLACK    = "#000000"
PANEL    = "#0a0005"
GREEN    = "#00ff41"
DIM      = "#3a1a28"
RED      = "#ff0033"


# ── Titlebar customizada (mesmo estilo/técnica do app principal — ver
# _draw_titlebar_dots / _make_draggable / _setup_native_window em app.py) ──
def _draw_titlebar_dots(canvas, x, on_close, on_minimize=None):
    close = canvas.create_oval(x, 11, x + 14, 25, fill=PINK, outline="")
    canvas.tag_bind(close, "<Button-1>", lambda e: on_close())
    canvas.tag_bind(close, "<Enter>", lambda e: canvas.itemconfig(close, fill=RED))
    canvas.tag_bind(close, "<Leave>", lambda e: canvas.itemconfig(close, fill=PINK))
    x += 22
    if on_minimize:
        mini = canvas.create_oval(x, 11, x + 14, 25, fill="", outline=PINK_DIM, width=2)
        canvas.tag_bind(mini, "<Button-1>", lambda e: on_minimize())
        canvas.tag_bind(mini, "<Enter>", lambda e: canvas.itemconfig(mini, outline=PINK))
        canvas.tag_bind(mini, "<Leave>", lambda e: canvas.itemconfig(mini, outline=PINK_DIM))
        x += 22
    return x


def _make_draggable(win, widgets):
    drag = {"x": 0, "y": 0}

    def _start(event):
        drag["x"], drag["y"] = event.x, event.y

    def _do_move(event):
        x = win.winfo_pointerx() - drag["x"]
        y = win.winfo_pointery() - drag["y"]
        win.geometry(f"+{x}+{y}")

    for w in widgets:
        w.bind("<ButtonPress-1>", _start)
        w.bind("<B1-Motion>", _do_move)


def resource_path(relative_path):
    """Resolve um recurso (ícone) tanto rodando como script quanto compilado
    com PyInstaller --onefile (extraído em sys._MEIPASS em runtime).

    Quando compilado, tudo fica embutido na raiz do pacote (_MEIPASS), então
    o caminho relativo funciona direto. Quando rodando como script, porém,
    este arquivo mora em installer/, mas a pasta icons/ está um nível acima,
    na raiz do repo — por isso tentamos ambos os locais nesse caso."""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, relative_path)

    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, relative_path)
    if os.path.exists(candidate):
        return candidate

    parent_candidate = os.path.join(os.path.dirname(here), relative_path)
    return parent_candidate


ICON_ICO = resource_path(os.path.join("icons", "icon.ico"))


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("hyavpn setup")
        self.geometry("500x436")
        self.configure(bg=BLACK)
        self.resizable(False, False)
        self._release_info = None

        # Mesma técnica do app principal: tira só os bits de estilo da
        # titlebar nativa via WinAPI (em vez de overrideredirect), pra não
        # ter o flash branco e pra bater visualmente com o app instalado.
        if sys.platform == "win32":
            self.withdraw()
            self.after(10, self._setup_native_window)
        else:
            self.overrideredirect(True)

        try:
            if os.path.exists(ICON_ICO):
                self.iconbitmap(ICON_ICO)
        except Exception:
            pass
        self._build()

    def _setup_native_window(self):
        import ctypes
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
        WS_MINIMIZEBOX, WS_SYSMENU = 0x00020000, 0x00080000
        WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = 0x00040000, 0x00000080
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x0002, 0x0001, 0x0004, 0x0020
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = (style & ~(WS_CAPTION | WS_THICKFRAME)) | WS_MINIMIZEBOX | WS_SYSMENU
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            exstyle = (exstyle & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception:
            self.overrideredirect(True)
        self.deiconify()

    def _minimize(self):
        self.iconify()

    def _build(self):
        titlebar = tk.Frame(self, bg=PANEL, height=36)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        dots = tk.Canvas(titlebar, width=52, height=36, bg=PANEL, highlightthickness=0)
        dots.pack(side="left", padx=(12, 0))
        _draw_titlebar_dots(dots, 0, on_close=self.destroy, on_minimize=self._minimize)

        tb_label = tk.Label(titlebar, text="hyavpn setup", font=("Courier New", 9),
                             fg=DIM, bg=PANEL)
        tb_label.pack(side="left", padx=8)

        _make_draggable(self, [titlebar, tb_label])

        tk.Label(self, text="hyavpn", font=("Courier New", 28, "bold"),
                 fg=PINK, bg=BLACK).pack(pady=(20, 2))
        tk.Label(self, text="by hyafranch  //  installer",
                 font=("Courier New", 9), fg=DIM, bg=BLACK).pack()

        tk.Frame(self, bg=PINK, height=1).pack(fill="x", padx=30, pady=16)

        self.status = tk.Label(self, text="ready to install.",
                               font=("Courier New", 10), fg=GREEN, bg=BLACK)
        self.status.pack(pady=4)

        self.log_box = tk.Text(self, bg="#0a0005", fg=GREEN, font=("Courier New", 8),
                                bd=0, highlightthickness=0, state="disabled",
                                height=10, width=58)
        self.log_box.pack(padx=24, pady=8)
        self.log_box.tag_config("pink",  foreground=PINK)
        self.log_box.tag_config("green", foreground=GREEN)
        self.log_box.tag_config("red",   foreground="#ff0033")
        self.log_box.tag_config("dim",   foreground=DIM)

        self.progress = ttk.Progressbar(self, length=440, mode="determinate")
        self.progress.pack(padx=30, pady=4)

        self.btn = tk.Button(self, text="[ INSTALL ]",
                             font=("Courier New", 12, "bold"),
                             fg=PINK, bg="#150008", activeforeground=BLACK,
                             activebackground=PINK, bd=0, pady=8, padx=20,
                             cursor="hand2", command=self._start)
        self.btn.pack(pady=12)

    def _log(self, msg, tag="dim"):
        self.log_box.configure(state="normal")
        import time
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update()

    def _set_status(self, msg, color=GREEN):
        self.status.configure(text=msg, fg=color)
        self.update()

    def _start(self):
        self.btn.configure(state="disabled")
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        steps = [
            ("creating directories",        self._step_dirs,             8),
            ("checking latest release",     self._step_fetch_release,   20),
            ("downloading hyavpn",          self._step_download_dist,   45),
            ("installing files",            self._step_extract_dist,    58),
            ("checking openvpn",            self._step_openvpn,         72),
            ("installing openvpn",          self._step_openvpn_install, 88),
            ("creating shortcut",           self._step_shortcut,        98),
            ("done",                        None,                      100),
        ]
        for label, fn, pct in steps:
            self._set_status(f"// {label}...")
            self._log(label, "pink")
            self.progress["value"] = pct
            self.update()
            if fn:
                try:
                    fn()
                except Exception as e:
                    self._log(f"error: {e}", "red")
                    self._set_status("installation failed.", PINK)
                    self.btn.configure(state="normal", text="[ RETRY ]")
                    return

        self._log("installation complete.", "green")
        self._set_status("// INSTALLED SUCCESSFULLY", GREEN)
        self.btn.configure(state="normal", text="[ CLOSE ]",
                           command=self.destroy)

    # ── Passos ─────────────────────────────────────────────────────────────────
    def _step_dirs(self):
        os.makedirs(INSTALL_DIR, exist_ok=True)
        os.makedirs(APPDATA_DIR, exist_ok=True)
        self._log(f"install dir: {INSTALL_DIR}", "dim")

    def _step_fetch_release(self):
        """Consulta o último Release publicado no GitHub e localiza o asset de distribuição."""
        ctx = ssl.create_default_context()
        req = urllib.request.Request(GITHUB_API_LATEST, headers={"User-Agent": "hyavpn-installer"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = json.loads(r.read())

        tag = data.get("tag_name", "unknown")
        asset_url = None
        for a in data.get("assets", []):
            if a.get("name") == DIST_ASSET_NAME:
                asset_url = a.get("browser_download_url")
                break

        if not asset_url:
            raise RuntimeError(
                f"release {tag} found, but no '{DIST_ASSET_NAME}' asset attached. "
                f"check github.com/{GITHUB_REPO}/releases"
            )

        self._release_info = {"tag": tag, "asset_url": asset_url}
        self._log(f"latest version: {tag}", "green")

    def _step_download_dist(self):
        url = self._release_info["asset_url"]
        self._log(f"downloading {DIST_ASSET_NAME}...", "dim")
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "hyavpn-installer"})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r, open(DIST_ZIP_TMP, "wb") as f:
            shutil.copyfileobj(r, f)
        self._log("download complete.", "green")

    def _step_extract_dist(self):
        # Limpa uma instalação anterior (menos configs/certs, que ficam em APPDATA)
        if os.path.exists(INSTALL_DIR):
            for item in os.listdir(INSTALL_DIR):
                p = os.path.join(INSTALL_DIR, item)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                except Exception:
                    pass

        with zipfile.ZipFile(DIST_ZIP_TMP) as z:
            z.extractall(INSTALL_DIR)

        exe_path = os.path.join(INSTALL_DIR, EXE_NAME)
        if not os.path.exists(exe_path):
            raise RuntimeError(f"{EXE_NAME} not found after extracting — check the release package.")

        self._log(f"installed to {INSTALL_DIR}", "green")

    def _step_openvpn(self):
        if os.path.exists(r"C:\Program Files\OpenVPN\bin\openvpn.exe"):
            self._log("openvpn already installed, skipping download.", "dim")
            self._skip_openvpn_install = True
            return
        self._skip_openvpn_install = False
        self._log("downloading openvpn...", "dim")
        ctx = ssl.create_default_context()
        urllib.request.urlretrieve(OPENVPN_URL, OPENVPN_MSI)
        self._log("download complete.", "green")

    def _step_openvpn_install(self):
        if getattr(self, "_skip_openvpn_install", False):
            self._log("openvpn already installed.", "dim")
            return
        self._log("installing openvpn silently (requires admin)...", "pink")
        subprocess.run(
            ["msiexec", "/i", OPENVPN_MSI, "/quiet", "/norestart", "ADDLOCAL=OpenVPN"],
            check=True
        )
        self._log("openvpn installed.", "green")

    def _get_desktop_path(self):
        """Resolve o caminho REAL da pasta Desktop (compatível com Desktop
        redirecionado pelo OneDrive — Known Folder Move)."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
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

        desktop = self._get_desktop_path()
        os.makedirs(desktop, exist_ok=True)
        lnk_path = os.path.join(desktop, "hyavpn.lnk")

        ps_cmd = f"""
$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut("{lnk_path}")
$SC.TargetPath = "{exe_path}"
$SC.WorkingDirectory = "{INSTALL_DIR}"
$SC.IconLocation = "{exe_path}"
$SC.Description = "hyavpn by hyafranch"
$SC.Save()
"""
        r = subprocess.run(["powershell", "-Command", ps_cmd],
                           check=False, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(lnk_path):
            self._log(f"shortcut created: {lnk_path}", "green")
        else:
            err = (r.stderr or r.stdout).strip()
            self._log(f"shortcut creation failed: {err[-200:] if err else 'unknown error'}", "red")


if __name__ == "__main__":
    app = Installer()
    app.mainloop()
