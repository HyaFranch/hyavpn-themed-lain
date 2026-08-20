"""
hyavpn — by hyafranch
Estética: Accela / Serial Experiments Lain
Preto + rosa/magenta, terminal verde, personagem sketch
"""

import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageSequence
import threading
import time
import subprocess
import psutil
import os
import sys
import math
import random
import json
import shutil
import socket
import tempfile
import zipfile

# ── Versão / Auto-update ─────────────────────────────────────────────────────
__version__ = "1.0.0"
GITHUB_REPO = "HyaFranch/hyavpn-themed-lain"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_ASSET_NAME = "hyavpn-dist.zip"   # nome do asset publicado em cada Release

# ── Instância única (evita 2 VPNs abertas ao mesmo tempo) ───────────────────
_SINGLE_INSTANCE_PORT = 51737  # porta local fixa, usada só como "lock", nunca escuta de verdade
_single_instance_socket = None  # precisa ficar viva enquanto o app roda


def resource_path(relative_path):
    """Resolve um caminho de recurso (ícone, asset) tanto rodando como script
    quanto compilado com PyInstaller --onefile (que extrai tudo pra uma pasta
    temporária apontada por sys._MEIPASS em tempo de execução)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


ICON_ICO = resource_path(os.path.join("icons", "icon.ico"))

# ── Audio ─────────────────────────────────────────────────────────────────────
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    AUDIO = True
except Exception:
    AUDIO = False

# ── Tema Accela ───────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")

# Workaround para um bug conhecido do customtkinter no Windows: a função
# interna que pinta a titlebar nativa de escuro (_windows_set_titlebar_color)
# pode falhar com "TypeError: 'str' object is not callable" em certas
# combinações de versão do Windows/customtkinter, ao tentar restaurar o foco
# depois de repintar a janela -- a pintura em si (a parte que interessa)
# já aconteceu antes desse erro, só o "restaurar foco" no final é que quebra.
# Em vez de desligar a titlebar escura (o que deixaria a barra branca padrão
# do Windows), envolvemos o método original num try/except: a cor escura
# continua sendo aplicada normalmente, e só ignoramos o erro que sobra.
def _wrap_titlebar_color_safe(cls):
    original = cls._windows_set_titlebar_color

    def _safe(self, color_mode):
        try:
            original(self, color_mode)
        except Exception:
            pass

    cls._windows_set_titlebar_color = _safe

_wrap_titlebar_color_safe(ctk.CTk)
try:
    _wrap_titlebar_color_safe(ctk.CTkToplevel)
except AttributeError:
    pass

C = {
    "bg":      "#000000",
    "panel":   "#0a0005",
    "border":  "#3d0028",
    "pink":    "#ff2d78",
    "pink2":   "#c4005a",
    "pink_dim":"#5a0030",
    "green":   "#00ff41",
    "green2":  "#00b32c",
    "white":   "#f0d0dc",
    "grey":    "#3a1a28",
    "dim":     "#4a2535",
    "red":     "#ff0033",
}

FM = ("Courier New", 9)
FT = ("Courier New", 18, "bold")
FS = ("Courier New", 10)
FB = ("Courier New", 12, "bold")
FX = ("Courier New", 8)


def acquire_single_instance_lock():
    """Tenta se ligar numa porta fixa em localhost como trava.
    Se a porta já estiver ocupada, já existe uma instância do app rodando —
    isso evita abrir 2 túneis VPN concorrentes (e 2 janelas brigando pelo
    processo do OpenVPN/Discord)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None

# ── Personagem placeholder (substitua por GIF/PNG real em assets/) ─────────────
# Prioridade de carregamento: assets/{expr}.gif (animado) > assets/{expr}.png (estático) > sketch gerado
def make_char(w, h, expr="idle"):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Tenta carregar PNG real
    path = os.path.join("assets", f"{expr}.png")
    if os.path.exists(path):
        real = Image.open(path).convert("RGBA").resize((w, h))
        return ImageTk.PhotoImage(real)

    # Placeholder sketch estilo Lain
    pink = C["pink"]
    # cabeça
    d.ellipse([w//4, 8, 3*w//4, h//2+10], outline=pink, width=2)
    # corpo
    d.polygon([(w//2, h//2+10), (w//4, h-10), (3*w//4, h-10)], outline=pink, width=2)
    # olhos por expressão
    ey = h//4 + 8
    if expr == "idle":
        d.line([w//3, ey, w//3+12, ey], fill=pink, width=2)
        d.line([w*2//3-12, ey, w*2//3, ey], fill=pink, width=2)
    elif expr == "connecting":
        d.ellipse([w//3-2, ey-4, w//3+10, ey+8], outline=pink, width=2)
        d.ellipse([w*2//3-10, ey-4, w*2//3+2, ey+8], outline=pink, width=2)
    elif expr == "connected":
        d.arc([w//3, ey, w//3+12, ey+10], 180, 0, fill=pink, width=2)
        d.arc([w*2//3-12, ey, w*2//3, ey+10], 180, 0, fill=pink, width=2)
    # ruído/glitch
    for _ in range(20):
        x = random.randint(0, w)
        y = random.randint(0, h)
        d.line([x, y, x + random.randint(3, 12), y], fill=(255, 45, 120, 60), width=1)
    # scanlines
    for y in range(0, h, 3):
        d.line([0, y, w, y], fill=(0, 0, 0, 40), width=1)
    return ImageTk.PhotoImage(img)


def make_success_frame(w, h, t):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    for ring in range(4):
        r = int(20 + ring * 18 + 10 * abs(math.sin(t + ring * 0.5)))
        alpha = int(200 - ring * 40)
        color = (255, 45, 120, alpha)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    for i in range(12):
        angle = (i / 12) * math.pi * 2 + t
        r1, r2 = 55, 70
        x1 = cx + int(r1 * math.cos(angle))
        y1 = cy + int(r1 * math.sin(angle))
        x2 = cx + int(r2 * math.cos(angle))
        y2 = cy + int(r2 * math.sin(angle))
        d.line([x1, y1, x2, y2], fill=(255, 45, 120, 180), width=2)
    return ImageTk.PhotoImage(img)


KANA = "アイウエオカキクケコサシスセソタチ01ﾊﾋﾌﾍﾎｦｧ"

def glitch(text, rate=0.18):
    return "".join(random.choice(KANA) if c != " " and random.random() < rate else c for c in text)


# ── Titlebar customizada (estilo Linux/GNOME, tema Accela/Lain) ─────────────
# A titlebar nativa do Windows só vem branca, não dá pra pintar no tema do
# app -- por isso as janelas rodam com overrideredirect(True) (sem decoração
# nativa) e desenham a própria barra, com "dots" no estilo dos temas clássicos
# do Linux (Ubuntu Ambiance etc) no lugar dos botões de fechar/minimizar.
def _draw_titlebar_dots(canvas, x, on_close, on_minimize=None):
    """Desenha os dots (fechar + minimizar opcional) num Canvas já
    posicionado na titlebar, com hover, ligados aos callbacks passados.
    Retorna o x seguinte, caso queira desenhar mais alguma coisa depois."""
    close = canvas.create_oval(x, 16, x + 14, 30, fill=C["pink"], outline="")
    canvas.tag_bind(close, "<Button-1>", lambda e: on_close())
    canvas.tag_bind(close, "<Enter>", lambda e: canvas.itemconfig(close, fill=C["red"]))
    canvas.tag_bind(close, "<Leave>", lambda e: canvas.itemconfig(close, fill=C["pink"]))
    x += 22

    if on_minimize:
        mini = canvas.create_oval(x, 16, x + 14, 30, fill="", outline=C["pink_dim"], width=2)
        canvas.tag_bind(mini, "<Button-1>", lambda e: on_minimize())
        canvas.tag_bind(mini, "<Enter>", lambda e: canvas.itemconfig(mini, outline=C["pink"]))
        canvas.tag_bind(mini, "<Leave>", lambda e: canvas.itemconfig(mini, outline=C["pink_dim"]))
        x += 22

    return x


def _strip_native_decorations(win, appwindow=False):
    """Remove a titlebar/moldura nativa de UMA JANELA do Windows via WinAPI,
    sem NUNCA usar overrideredirect. overrideredirect destrói e recria a
    HWND por baixo dos panos -- é isso que causa o flash branco (no
    minimizar/restaurar/alt-tab) e também pode deixar uma janela dona num
    estado sem repaint quando uma filha overrideredirect+grab é fechada
    (a janela "some" mesmo com o processo continuando vivo). Usada tanto
    na janela principal quanto na de settings, pra tirar overrideredirect
    do app inteiro.

    appwindow=True dá um botão próprio na barra de tarefas + minimizar
    (usado só na janela principal). Janelas modais (settings) ficam com o
    comportamento padrão de "dona/filha" do Windows, sem botão próprio.

    Também liga WS_EX_COMPOSITED: sem WS_CAPTION, o Windows já não tem
    mais a rotina nativa de "redesenhar a janela toda de uma vez só" que
    uma titlebar normal aciona ao mover -- cada widget filho (canvas do
    personagem, botões, labels, cada um sua própria sub-repintura GDI)
    podia repintar em momentos ligeiramente diferentes durante o arrasto,
    e por isso ficar "atrasado"/"bugado" visualmente enquanto a janela já
    tinha se movido. WS_EX_COMPOSITED manda o Windows compor a janela
    inteira (e todos os filhos) num buffer único fora da tela antes de
    mostrar, então tudo aparece sincronizado em cada frame -- efeito de
    double buffering nativo, sem custo nenhum de código nosso."""
    import ctypes
    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
    WS_MINIMIZEBOX, WS_SYSMENU = 0x00020000, 0x00080000
    WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = 0x00040000, 0x00000080
    WS_EX_COMPOSITED = 0x02000000
    SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x0002, 0x0001, 0x0004, 0x0020
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())

        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style = (style & ~(WS_CAPTION | WS_THICKFRAME)) | WS_SYSMENU
        if appwindow:
            style |= WS_MINIMIZEBOX
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        exstyle |= WS_EX_COMPOSITED
        if appwindow:
            exstyle = (exstyle & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle)

        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        )
        return True
    except Exception:
        return False


def _make_draggable(win, widgets):
    """Liga os widgets passados (normalmente a barra e o título) pra
    arrastar a janela pelo mouse -- perdido junto com a decoração nativa
    quando a janela roda sem titlebar nativa.

    Arrasto manual: só reposiciona (+x+y), NUNCA toca em largura/altura.

    Antes isso entregava o arrasto pro SO via ReleaseCapture() +
    SendMessageW(WM_NCLBUTTONDOWN, HTCAPTION) pra ganhar performance (o
    compositor do Windows move a janela sem o Python no meio do caminho a
    cada frame). O problema: combinado com a titlebar nativa removida via
    SetWindowLongW (ver _strip_native_decorations) num processo que não se
    declara "DPI aware", isso faz o Windows reescalar a janela em tempo
    real durante o arrasto em telas com escala >100% (125%/150%, comum em
    notebook) -- e ela cresce pros lados a cada frame que você arrasta.

    Agora o Python nunca chama geometry() com largura/altura durante o
    drag -- só "+x+y" -- então é fisicamente impossível a janela crescer
    aqui, não importa o que o Windows faça de escala por baixo. Os
    eventos de <B1-Motion> são coalescidos (só a última posição pendente
    é aplicada) pra não enfileirar updates. `win._dragging` fica True
    durante o arrasto pra pausar redraws pesados (GIF, etc. -- ver uso
    logo abaixo em _draw_frame / _update_title)."""
    drag = {"x": 0, "y": 0}
    pending = {"x": None, "y": None, "scheduled": False}

    def _apply_move():
        pending["scheduled"] = False
        if pending["x"] is not None:
            win.geometry(f"+{pending['x']}+{pending['y']}")

    def _start(event):
        win._dragging = True
        drag["x"], drag["y"] = event.x, event.y

    def _do_move(event):
        pending["x"] = event.x_root - drag["x"]
        pending["y"] = event.y_root - drag["y"]
        if not pending["scheduled"]:
            pending["scheduled"] = True
            win.after(1, _apply_move)

    def _end(event):
        win._dragging = False

    for w in widgets:
        w.bind("<ButtonPress-1>", _start)
        w.bind("<B1-Motion>", _do_move)
        w.bind("<ButtonRelease-1>", _end)


def _set_dpi_aware():
    """Declara o processo como DPI-aware (Per-Monitor V2, com fallback pra
    versões mais antigas do Windows). PRECISA rodar antes de qualquer
    janela Tk ser criada -- é a causa raiz do bug de janela crescendo ao
    arrastar em telas com escala: sem isso o Windows "virtualiza" o DPI do
    processo e reescala a janela por conta própria, inclusive durante o
    SetWindowPos(SWP_FRAMECHANGED) que tira a titlebar nativa."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback Windows 7/8
    except Exception:
        pass


# ── Split tunneling ──────────────────────────────────────────────────────────
# Domínios cujo tráfego é roteado pela VPN quando split tunneling está ativo.
# Cobre API/gateway (essencial para o bypass) e CDN/mídia do Discord.
# Obs: são endereços de CDN (Cloudflare/GCP) que rotacionam, então a lista de
# IPs é resolvida de novo a cada conexão — não é 100% garantido cobrir toda
# a mídia/voz, mas cobre o essencial para o app "reconhecer" o novo IP.
SPLIT_TUNNEL_DOMAINS = [
    "discord.com",
    "discordapp.com",
    "discord.gg",
    "gateway.discord.gg",
    "cdn.discordapp.com",
    "media.discordapp.net",
]


# ── Auto-update ───────────────────────────────────────────────────────────────
def _version_tuple(v):
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def check_for_update():
    """Consulta o último Release no GitHub. Retorna dict ou None em caso de erro."""
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(GITHUB_API_LATEST, headers={"User-Agent": "hyavpn-updater"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = json.loads(r.read())
        tag = data.get("tag_name", "")
        asset_url = None
        for a in data.get("assets", []):
            if a.get("name") == UPDATE_ASSET_NAME:
                asset_url = a.get("browser_download_url")
                break
        return {
            "tag": tag,
            "has_update": _version_tuple(tag) > _version_tuple(__version__),
            "asset_url": asset_url,
            "notes": (data.get("body") or "").strip()[:300],
        }
    except Exception as e:
        return {"error": str(e)}


# ── VPN Manager ───────────────────────────────────────────────────────────────
class VPNManager:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "hyavpn")
    OVPN_FILE  = os.path.join(CONFIG_DIR, "hyavpn.ovpn")
    CA_FILE    = os.path.join(CONFIG_DIR, "ca.crt")
    SPLIT_OVPN_FILE = os.path.join(CONFIG_DIR, "hyavpn_split.ovpn")
    SETTINGS_FILE   = os.path.join(CONFIG_DIR, "settings.json")

    PROVIDER_URL = "https://riseup.net/provider.json"

    def __init__(self, log_fn):
        self.log = log_fn
        self._proc = None
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        self.split_tunnel = self._load_split_tunnel_pref()

    # ── Preferência de split tunneling ────────────────────────────────────────
    def _load_split_tunnel_pref(self):
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("split_tunnel", False))
        except Exception:
            return False

    def _ovpn_is_stale(self):
        """True se o hyavpn.ovpn em disco é de uma versão antiga (gerada
        antes do fix de path com barra invertida) e precisa ser regerado.

        setup() só roda quando o arquivo ainda NÃO existe -- então quem já
        tinha um .ovpn salvo de antes desse fix ficava preso pra sempre com
        um config quebrado (ca/cert/key com "C:\\Users\\..." cru), o que o
        próprio OpenVPN acusa como "Bad backslash ('\\') usage" e nunca
        completa o handshake (tunnel timeout), mesmo com o gerador atual
        já correto. Aqui a gente detecta esse caso específico e invalida
        o arquivo velho pra forçar uma regeneração limpa."""
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

    def set_split_tunnel(self, enabled):
        self.split_tunnel = bool(enabled)
        try:
            data = {}
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["split_tunnel"] = self.split_tunnel
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            self.log(f"failed to save settings: {e}", "red")

    def setup(self):
        """Baixa configs do Riseup e gera .ovpn. Retorna True se ok."""
        import urllib.request, ssl
        ctx = ssl.create_default_context()

        self.log("fetching provider.json...", "pink")
        try:
            with urllib.request.urlopen(self.PROVIDER_URL, context=ctx, timeout=10) as r:
                provider = json.loads(r.read())
        except Exception as e:
            self.log(f"provider fetch failed: {e}", "red")
            return False

        api_uri    = provider.get("api_uri", "https://api.black.riseup.net")
        ca_uri     = provider.get("ca_cert_uri", "https://black.riseup.net/ca.crt")
        api_ver    = provider.get("api_version", "3")

        self.log(f"api: {api_uri}", "dim")

        # CA cert
        self.log("fetching CA certificate...", "pink")
        try:
            with urllib.request.urlopen(ca_uri, context=ctx, timeout=10) as r:
                ca_data = r.read()
            with open(self.CA_FILE, "wb") as f:
                f.write(ca_data)
        except Exception as e:
            self.log(f"ca fetch failed: {e}", "red")
            return False

        # EIP (gateways)
        eip_url = f"{api_uri}/{api_ver}/config/eip-service.json"
        self.log("fetching gateway list...", "pink")
        try:
            # Riseup usa cert próprio — desativa verificação só pra API deles
            ctx2 = ssl.create_default_context()
            ctx2.check_hostname = False
            ctx2.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(eip_url, context=ctx2, timeout=10) as r:
                eip = json.loads(r.read())
        except Exception as e:
            self.log(f"eip fetch failed: {e}", "red")
            return False

        gateways = eip.get("gateways", [])
        if not gateways:
            self.log("no gateways found.", "red")
            return False

        # Pega o primeiro gateway com UDP disponível
        gw = None
        for g in gateways:
            caps = g.get("capabilities", {})
            for t in caps.get("transport", []):
                if t.get("type") == "openvpn":
                    ports = t.get("ports", ["1194"])
                    proto = t.get("protocols", ["udp"])
                    gw = {"ip": g["ip_address"], "port": ports[0], "proto": proto[0]}
                    break
            if gw:
                break

        if not gw:
            self.log("no openvpn gateway available.", "red")
            return False

        self.log(f"gateway: {gw['ip']}:{gw['port']}/{gw['proto']}", "green")

        # Client cert (anônimo)
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

        # Gera .ovpn
        ovpn_cfg = eip.get("openvpn_configuration", {})
        cipher = ovpn_cfg.get("cipher", "AES-256-CBC")
        auth   = ovpn_cfg.get("auth",   "SHA256")
        tls_cipher = ovpn_cfg.get("tls-cipher", "")

        # OpenVPN trata "\" como caractere de escape dentro de strings entre
        # aspas no .ovpn -- um caminho do Windows colado direto (com \Users,
        # \Roaming etc.) vira "Bad backslash ('\\') usage" no parser e os
        # caminhos de ca/cert/key saem corrompidos, o que impede o túnel de
        # subir (timeout). O próprio OpenVPN aceita "/" no lugar de "\" em
        # caminhos no Windows, então convertemos antes de montar o config.
        ca_path   = self.CA_FILE.replace("\\", "/")
        cert_path = cert_file.replace("\\", "/")

        ovpn = f"""client
dev tun
proto {gw['proto']}
remote {gw['ip']} {gw['port']}
resolv-retry infinite
nobind
persist-key
persist-tun
ca "{ca_path}"
cert "{cert_path}"
key "{cert_path}"
cipher {cipher}
auth {auth}
verb 1
mute 3
script-security 1
"""
        if tls_cipher:
            ovpn += f"tls-cipher {tls_cipher}\n"

        with open(self.OVPN_FILE, "w", encoding="utf-8") as f:
            f.write(ovpn)

        self.log("config ready.", "green")
        return True

    def _build_split_tunnel_config(self):
        """Gera uma .ovpn temporária que só roteia o tráfego do Discord pela VPN.
        Usa route-nopull pra ignorar o full-tunnel que o servidor normalmente empurra,
        e adiciona rotas /32 pros IPs resolvidos dos domínios do Discord."""
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

        lines = [
            base_cfg, "",
            "# -- split tunneling: somente trafego do discord pela vpn --",
            "route-nopull",
        ]
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

    def connect(self):
        """Conecta via OpenVPN. Retorna True se iniciou."""
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
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            self.log(f"openvpn started (pid {self._proc.pid})", "green")
            return True
        except Exception as e:
            self.log(f"failed to start openvpn: {e}", "red")
            return False

    def wait_connected(self, timeout=30):
        """Aguarda OpenVPN reportar 'Initialization Sequence Completed'."""
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
        # Mata qualquer openvpn restante
        for p in psutil.process_iter(["name"]):
            try:
                if "openvpn" in p.info["name"].lower():
                    p.terminate()
            except Exception:
                pass
        self.log("vpn disconnected.", "dim")

    def _find_openvpn(self):
        # Primeiro verifica na pasta do app (instalado pelo setup)
        local = os.path.join(os.path.dirname(sys.executable), "openvpn", "openvpn.exe")
        if os.path.exists(local):
            return local
        # Program Files
        for p in [
            r"C:\Program Files\OpenVPN\bin\openvpn.exe",
            r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
            os.path.join(self.CONFIG_DIR, "openvpn", "openvpn.exe"),
        ]:
            if os.path.exists(p):
                return p
        return shutil.which("openvpn")


# ── Main App ──────────────────────────────────────────────────────────────────
class HyaVPN(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("hyavpn")
        self.geometry("440x640")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])

        # Tira a decoração nativa do Windows (a titlebar branca) pra usar a
        # barra customizada desenhada em _build_ui. Ver _setup_native_window
        # pra entender por que isso NÃO usa overrideredirect(True) no Windows.
        if sys.platform == "win32":
            self.withdraw()  # escondida até tirarmos a decoração nativa (evita o flash já no boot)
            self.after(10, self._setup_native_window)
        else:
            self.overrideredirect(True)

        try:
            if os.path.exists(ICON_ICO):
                self.iconbitmap(ICON_ICO)
        except Exception:
            pass  # .ico ausente ou inválido não deve impedir o app de abrir

        self._state = "idle"
        self._t      = 0.0
        self._scan_y = 0
        self._glitch = False
        self._anim_overlay = False
        self._success_frame_ref = None

        self._char_gif_cache = {}   # expr -> (frames, duration_ms)
        self._gif_anim_job = None
        self._gif_frame_idx = 0

        self._update_info = None  # resultado do último check_for_update()

        self.vpn = VPNManager(self._log)
        self._build_ui()
        self._tick()

        # checa update em background, sem travar a UI, um pouco depois de abrir
        self.after(1500, lambda: threading.Thread(target=self._check_update_bg, daemon=True).start())

    # ── Titlebar customizada: minimizar/restaurar/taskbar (Windows) ─────────────
    def _setup_native_window(self):
        """Tira a titlebar/moldura nativa via WinAPI em vez de usar
        overrideredirect(True) (que era o método antigo).

        O bug do flash branco (no minimizar E no alt-tab) era causado pelo
        overrideredirect: no Windows, ligar/desligar o overrideredirect
        DESTRÓI E RECRIA a HWND da janela por baixo dos panos. O código
        antigo fazia isso toda vez que minimizava (overrideredirect(False)
        -> iconify()) e toda vez que restaurava (overrideredirect(True) nos
        no <Map>) -- cada recriação faz o Windows desenhar por uma fração de
        segundo a janela "nova" com a decoração branca padrão antes do
        conteúdo customizado repintar. É exatamente esse frame branco que
        aparece no minimizar e no alt-tab.
        A recriação da HWND também derrubava o WS_EX_APPWINDOW aplicado no
        boot (o antigo _ensure_taskbar_icon rodava só uma vez), o que
        explica o app sumindo/agindo estranho na barra de tarefas depois do
        primeiro ciclo de minimizar/restaurar -- e também é a explicação
        mais provável pro bug de fechar a janela de settings e a janela
        principal sumir junto (a settings, modal + overrideredirect + owner
        window com HWND instável, ao fechar podia deixar a dona num estado
        sem repaint -- processo continuava vivo, só a janela desaparecia).

        A correção: nunca tocar em overrideredirect, nem aqui nem na janela
        de settings (ver _strip_native_decorations). Só tiramos os bits de
        estilo da titlebar nativa via SetWindowLongW, mantendo a mesma HWND
        viva o tempo todo -- minimizar/restaurar/alt-tab passam a ser 100%
        nativos do Windows (o DWM cuida da animação), sem flash e sem
        nenhuma janela "sumindo" ao fechar uma filha.
        """
        if not _strip_native_decorations(self, appwindow=True):
            # se der ruim (versão do Windows, permissão etc.), cai pro
            # método antigo em vez de deixar a janela sem decoração e sem abrir
            self.overrideredirect(True)
        self.deiconify()

    def _minimize(self):
        # Agora é só isso -- sem tocar em overrideredirect, o Windows
        # minimiza/restaura pela HWND real, sem flash e sem perder o estilo
        # de taskbar aplicado em _setup_native_window.
        self.iconify()

    def _on_close_request(self):
        """Fecha de verdade. Antes, o dot de fechar ia direto pro
        self.destroy() -- então se você fechasse o app CONECTADO, o
        processo do openvpn.exe continuava rodando sozinho em segundo
        plano (sem nenhuma janela associada, "invisível"): a GUI sumia mas
        a VPN e o processo real não fechavam. Aqui a gente desconecta
        (mata o processo do openvpn, ver VPNManager.disconnect) antes de
        destruir a janela, então fechar o app garante que nada fica
        rodando escondido depois."""
        try:
            self.vpn.disconnect()
        except Exception:
            pass
        self.destroy()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Background canvas
        self.bg = tk.Canvas(self, bg=C["bg"], highlightthickness=0, width=440, height=640)
        self.bg.place(x=0, y=0)

        # Header bar / titlebar customizada
        self.hdr = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0, height=46)
        self.hdr.place(x=0, y=0, relwidth=1)

        # Dots estilo Linux (Ubuntu/GNOME) no lugar dos botões nativos --
        # fechar (rosa cheio) e minimizar (rosa contorno).
        dots = tk.Canvas(self.hdr, width=52, height=46, bg=C["panel"], highlightthickness=0)
        dots.place(x=12, y=0)
        _draw_titlebar_dots(dots, 0, on_close=self._on_close_request, on_minimize=self._minimize)

        self.title_lbl = ctk.CTkLabel(
            self.hdr, text="hyavpn",
            font=FT, text_color=C["pink"]
        )
        self.title_lbl.place(x=78, y=8)

        self.version_lbl = ctk.CTkLabel(
            self.hdr, text=f"v{__version__} // by hyafranch",
            font=FX, text_color=C["dim"]
        )
        self.version_lbl.place(x=80, y=30)

        gear = ctk.CTkButton(
            self.hdr, text="⚙", width=36, height=36,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["pink_dim"], font=("Courier New", 16),
            corner_radius=2, command=self._open_settings
        )
        gear.place(x=394, y=5)

        # Arrastar a janela pela barra (perdido junto com a titlebar nativa)
        _make_draggable(self, [self.hdr, self.title_lbl, self.version_lbl])

        # Personagem
        self.char_canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0,
                                      width=220, height=220)
        self.char_canvas.place(x=110, y=54)
        self._char_img = None
        self._set_char("idle")

        # Status pill
        sf = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=4,
                           border_width=1, border_color=C["border"],
                           width=408, height=54)
        sf.place(x=16, y=284)

        self.dot = tk.Canvas(sf, width=10, height=10, bg=C["panel"], highlightthickness=0)
        self.dot.place(x=12, y=21)
        self.dot.create_oval(0, 0, 10, 10, fill=C["grey"], tags="d")

        self.status_lbl = ctk.CTkLabel(sf, text="STANDBY // NOT CONNECTED",
                                        font=FS, text_color=C["dim"], anchor="w")
        self.status_lbl.place(x=30, y=10)

        self.sub_lbl = ctk.CTkLabel(sf, text="", font=FX, text_color=C["grey"], anchor="w")
        self.sub_lbl.place(x=30, y=30)

        # Botão principal
        self.btn = ctk.CTkButton(
            self, text="[ AUTO BYPASS ]",
            width=408, height=60,
            fg_color=C["panel"], hover_color="#150008",
            border_width=1, border_color=C["pink"],
            text_color=C["pink"], font=FB,
            corner_radius=2, command=self._on_bypass
        )
        self.btn.place(x=16, y=350)

        # Terminal
        tf = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=2,
                           border_width=1, border_color=C["border"],
                           width=408, height=192)
        tf.place(x=16, y=426)

        ctk.CTkLabel(tf, text="// SYSTEM LOG", font=FX,
                     text_color=C["pink_dim"], anchor="w").place(x=8, y=4)

        self.term = tk.Text(
            tf, bg=C["panel"], fg=C["green"], font=FM,
            bd=0, highlightthickness=0, state="disabled",
            cursor="none", wrap="word", insertbackground=C["green"]
        )
        self.term.place(x=8, y=20, width=392, height=166)
        self.term.tag_config("pink",  foreground=C["pink"])
        self.term.tag_config("green", foreground=C["green"])
        self.term.tag_config("red",   foreground=C["red"])
        self.term.tag_config("dim",   foreground=C["dim"])
        self.term.tag_config("white", foreground=C["white"])

        self._log("hyavpn initialised.", "green")
        self._log("press AUTO BYPASS to start.", "dim")

    # ── Char ───────────────────────────────────────────────────────────────────
    def _load_gif(self, expr):
        """Carrega (e cacheia) os frames de assets/{expr}.gif. Retorna (frames, duration_ms) ou None."""
        if expr in self._char_gif_cache:
            return self._char_gif_cache[expr]

        path = os.path.join("assets", f"{expr}.gif")
        if not os.path.exists(path):
            return None

        try:
            src = Image.open(path)
            frames = []
            duration = 100
            for frame in ImageSequence.Iterator(src):
                f = frame.convert("RGBA").resize((220, 220))
                frames.append(ImageTk.PhotoImage(f))
                duration = frame.info.get("duration", duration) or duration
            if not frames:
                return None
            data = (frames, duration)
            self._char_gif_cache[expr] = data
            return data
        except Exception as e:
            msg = f"gif load failed ({expr}.gif): {e}"
            if hasattr(self, "term"):
                self._log(msg, "red")
            else:
                print(msg)
            return None

    def _set_char(self, expr):
        # cancela qualquer animação de gif em andamento
        if self._gif_anim_job:
            self.after_cancel(self._gif_anim_job)
            self._gif_anim_job = None

        gif_data = self._load_gif(expr)
        if gif_data:
            self._gif_frame_idx = 0
            self._animate_gif(gif_data[0], gif_data[1])
            return

        # sem gif -> cai pro PNG estático ou sketch placeholder
        self.char_canvas.delete("all")
        img = make_char(220, 220, expr)
        self._char_img = img
        self.char_canvas.create_image(110, 110, image=img)

    def _animate_gif(self, frames, duration):
        # Pausa a repintura do personagem enquanto a janela está sendo
        # arrastada (ver _make_draggable) -- senão esse redraw a cada
        # frame do gif competia com o reposicionamento da janela e era
        # parte do conteúdo "bugando" durante o drag. Só pula o desenho;
        # o timer do gif continua agendado normalmente.
        if not getattr(self, "_dragging", False):
            self.char_canvas.delete("all")
            frame = frames[self._gif_frame_idx]
            self._char_img = frame  # segura referência p/ não ser coletada pelo GC
            self.char_canvas.create_image(110, 110, image=frame)
        self._gif_frame_idx = (self._gif_frame_idx + 1) % len(frames)
        self._gif_anim_job = self.after(max(duration, 20), lambda: self._animate_gif(frames, duration))

    # ── Log ────────────────────────────────────────────────────────────────────
    def _log(self, msg, tag="dim"):
        """Thread-safe: _flow, _check_update_bg e _apply_update rodam em
        threads de background e chamam isso direto. Tkinter só permite
        mexer em widgets na main thread -- chamar daqui de outra thread
        derrubava com 'RuntimeError: main thread is not in main loop'
        (mais rígido a partir do Python 3.13/3.14). Se não estamos na main
        thread, reagenda a própria chamada via self.after(0, ...) em vez
        de tocar no widget direto."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, lambda: self._log(msg, tag))
            return
        ts = time.strftime("%H:%M:%S")
        self.term.configure(state="normal")
        self.term.insert("end", f"[{ts}] {msg}\n", tag)
        self.term.see("end")
        self.term.configure(state="disabled")

    # ── Audio ──────────────────────────────────────────────────────────────────
    def _play(self, name):
        if not AUDIO:
            return
        path = os.path.join("audio", f"{name}.mp3")
        if os.path.exists(path):
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
            except Exception:
                pass

    # ── Bypass flow ────────────────────────────────────────────────────────────
    def _on_bypass(self):
        if self._state != "idle":
            return
        threading.Thread(target=self._flow, daemon=True).start()

    def _flow(self):
        self._set_state("connecting")
        self._play("connecting")
        self._log("initiating bypass...", "pink")

        # Setup config se necessário (arquivo ausente OU de versão antiga
        # com paths quebrados -- ver VPNManager._ovpn_is_stale)
        if not os.path.exists(self.vpn.OVPN_FILE) or self.vpn._ovpn_is_stale():
            self._log("fetching riseup config...", "dim")
            if not self.vpn.setup():
                self._log("setup failed.", "red")
                self._set_state("idle")
                return

        # Conecta VPN
        self._log("connecting to vpn...", "pink")
        if not self.vpn.connect():
            self._set_state("idle")
            return

        self._log("waiting for tunnel...", "dim")
        ok = self.vpn.wait_connected(timeout=40)
        if not ok:
            self._log("tunnel timeout.", "red")
            self.vpn.disconnect()
            self._set_state("idle")
            return

        self._set_state("connected")
        self._log("tunnel active.", "green")
        self._play("connected")
        time.sleep(1.5)

        # Reinicia Discord
        self._log("killing discord...", "dim")
        self._kill_discord()
        time.sleep(2)
        self._log("relaunching discord...", "dim")
        self._open_discord()

        # Aguarda Discord
        self._log("waiting for discord...", "dim")
        disc_ok = self._wait_discord(25)
        if disc_ok:
            self._log("discord is up.", "green")
        else:
            self._log("discord took too long.", "red")

        time.sleep(3)

        # Desconecta VPN
        self._log("releasing tunnel...", "dim")
        self.vpn.disconnect()

        # Sucesso
        self._set_state("success")
        self._play("success")
        self.after(0, self._show_success)

    # ── Discord ────────────────────────────────────────────────────────────────
    def _kill_discord(self):
        for p in psutil.process_iter(["name"]):
            try:
                if "discord" in p.info["name"].lower():
                    p.terminate()
            except Exception:
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

    def _wait_discord(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            for p in psutil.process_iter(["name"]):
                try:
                    if "discord" in p.info["name"].lower():
                        return True
                except Exception:
                    pass
            time.sleep(1)
        return False

    # ── State ──────────────────────────────────────────────────────────────────
    def _set_state(self, state):
        self._state = state
        self.after(0, self._apply_state)

    def _apply_state(self):
        s = self._state
        dot_colors = {"idle": C["grey"], "connecting": C["pink"], "connected": C["green"], "success": C["green"]}
        self.dot.itemconfig("d", fill=dot_colors.get(s, C["grey"]))

        if s == "idle":
            self.status_lbl.configure(text="STANDBY // NOT CONNECTED", text_color=C["dim"])
            self.sub_lbl.configure(text="")
            self.btn.configure(state="normal", border_color=C["pink"], text_color=C["pink"])
            self._glitch = False
            self._set_char("idle")

        elif s == "connecting":
            self.status_lbl.configure(text="CONNECTING // ESTABLISHING TUNNEL", text_color=C["pink"])
            mode = "split tunnel: only discord" if self.vpn.split_tunnel else "full tunnel"
            self.sub_lbl.configure(text=f"routing through riseup servers ({mode})")
            self.btn.configure(state="disabled", border_color=C["grey"], text_color=C["grey"])
            self._glitch = True
            self._set_char("connecting")

        elif s == "connected":
            self.status_lbl.configure(text="TUNNEL ACTIVE // RESTARTING DISCORD", text_color=C["pink"])
            self.sub_lbl.configure(text="changing ip context...")
            self._set_char("connected")

        elif s == "success":
            self.status_lbl.configure(text="BYPASS COMPLETE // STREAM ENABLED", text_color=C["green"])
            self.sub_lbl.configure(text="go live on discord")
            self._glitch = False
            self._set_char("connected")

    # ── Success overlay ────────────────────────────────────────────────────────
    def _show_success(self):
        self.ov = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0,
                                width=440, height=594)
        self.ov.place(x=0, y=46, relwidth=1)

        self.ov_canvas = tk.Canvas(self.ov, bg=C["bg"], highlightthickness=0, width=440, height=240)
        self.ov_canvas.pack(pady=(24, 0))

        ctk.CTkLabel(self.ov, text="// STREAM ENABLED //",
                     font=("Courier New", 20, "bold"), text_color=C["pink"]).pack(pady=(8, 4))
        ctk.CTkLabel(self.ov,
                     text="vpn disconnected. your ip changed context.\nyou can now go live on discord.",
                     font=FS, text_color=C["white"], justify="center").pack(pady=(0, 20))
        ctk.CTkButton(self.ov, text="[ OK ]", width=140, height=40,
                      fg_color=C["panel"], border_width=1, border_color=C["green"],
                      text_color=C["green"], font=FB, corner_radius=2,
                      command=self._close_overlay).pack()

        self._anim_overlay = True
        self._anim_ov()

    def _anim_ov(self):
        if not self._anim_overlay:
            return
        self._t += 0.06
        self.ov_canvas.delete("all")
        img = make_success_frame(440, 240, self._t)
        self._success_frame_ref = img
        self.ov_canvas.create_image(220, 120, image=img)
        self.after(50, self._anim_ov)

    def _close_overlay(self):
        self._anim_overlay = False
        self.ov.destroy()
        self._set_state("idle")

    # ── Background animation ───────────────────────────────────────────────────
    def _tick(self):
        self._t += 0.035
        self._scan_y = (self._scan_y + 3) % 640
        # Enquanto a janela está sendo arrastada (ver _make_draggable),
        # pula a repintura do fundo -- é essa repintura em loop brigando
        # com o drag, quadro a quadro, que causava o "gaguejar" visual.
        # O timer continua rodando, só a repintura fica em pausa.
        if not getattr(self, "_dragging", False):
            self._draw_bg()
        if self._glitch:
            txt = glitch("hyavpn", 0.25)
            self.title_lbl.configure(text=txt)
        else:
            self.title_lbl.configure(text="hyavpn")
        self.after(50, self._tick)

    def _draw_bg(self):
        c = self.bg
        c.delete("all")
        t = self._t
        # Grade
        for x in range(0, 440, 44):
            c.create_line(x, 0, x, 640, fill="#1a0010", width=1)
        for y in range(0, 640, 44):
            c.create_line(0, y, 440, y, fill="#1a0010", width=1)
        # Scanline rosa
        sy = self._scan_y
        c.create_rectangle(0, sy, 440, sy + 2, fill=C["pink"], stipple="gray12")
        # Partículas
        for i in range(8):
            px = int((i * 55 + 30 * math.sin(t * 0.8 + i)) % 440)
            py = int((i * 80 + 25 * math.cos(t * 0.6 + i * 1.3)) % 640)
            sz = 1 + int(abs(math.sin(t + i)) * 2)
            col = C["pink"] if i % 2 == 0 else C["pink2"]
            c.create_oval(px - sz, py - sz, px + sz, py + sz, fill=col, outline="")

    # ── Auto-update ────────────────────────────────────────────────────────────
    def _check_update_bg(self):
        info = check_for_update()
        self._update_info = info
        if not info:
            return
        if info.get("error"):
            self._log(f"update check failed: {info['error']}", "dim")
            return
        if info.get("has_update"):
            self._log(f"update available: {info['tag']} (current v{__version__})", "pink")
        else:
            self._log("hyavpn is up to date.", "dim")

    def _manual_check_update(self):
        self._log("checking for updates...", "pink")
        def run():
            info = check_for_update()
            self._update_info = info
            self.after(0, lambda: self._on_manual_check_done(info))
        threading.Thread(target=run, daemon=True).start()

    def _on_manual_check_done(self, info):
        if not info or info.get("error"):
            self._log(f"update check failed: {info.get('error') if info else 'unknown error'}", "red")
            return
        if not info.get("has_update"):
            self._log(f"already on the latest version (v{__version__}).", "green")
            return
        if not info.get("asset_url"):
            self._log(f"update {info['tag']} found, but no installable asset — check github releases.", "dim")
            return
        self._log(f"update {info['tag']} available. downloading...", "pink")
        threading.Thread(target=lambda: self._apply_update(info), daemon=True).start()

    def _apply_update(self, info):
        """Baixa a nova versão publicada como Release no GitHub e agenda a troca
        via um script auxiliar que espera este processo fechar antes de sobrescrever
        os arquivos — necessário pois o Windows não deixa sobrescrever um .exe rodando."""
        import urllib.request, ssl

        asset_url = info["asset_url"]
        tmp_zip = os.path.join(tempfile.gettempdir(), "hyavpn_update.zip")
        tmp_dir = os.path.join(tempfile.gettempdir(), "hyavpn_update_extract")

        try:
            ctx = ssl.create_default_context()
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

        # Diretório onde o app está rodando de fato (funciona tanto rodando
        # como .exe compilado quanto como script .py)
        if getattr(sys, "frozen", False):
            install_dir = os.path.dirname(sys.executable)
            exe_name = os.path.basename(sys.executable)
        else:
            install_dir = os.path.dirname(os.path.abspath(__file__))
            exe_name = None  # rodando como script, não tem exe pra reabrir sozinho

        pid = os.getpid()
        bat_path = os.path.join(tempfile.gettempdir(), "hyavpn_updater.bat")

        if exe_name:
            relaunch = f'start "" "{os.path.join(install_dir, exe_name)}"'
        else:
            relaunch = "rem rodando via script .py — reabra manualmente"

        bat = f"""@echo off
:wait
tasklist /fi "PID eq {pid}" | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
xcopy /y /e /i "{tmp_dir}\\*" "{install_dir}\\" >nul
{relaunch}
del "%~f0"
"""
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat)
            self._log(f"update {info['tag']} ready — restarting...", "green")
            subprocess.Popen(["cmd", "/c", bat_path],
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            self.after(600, self.destroy)
        except Exception as e:
            self._log(f"failed to schedule update: {e}", "red")

    # ── Settings ───────────────────────────────────────────────────────────────
    def _open_settings(self):
        w = ctk.CTkToplevel(self)
        w.title("settings")
        w.geometry("340x560")
        w.configure(fg_color=C["bg"])
        w.resizable(False, False)

        # Mesma titlebar customizada da janela principal, só que com dot de
        # fechar apenas (é uma janela modal, não faz sentido minimizar).
        # NÃO usa overrideredirect (ver _strip_native_decorations) -- era
        # essa a causa mais provável de fechar a settings derrubar a janela
        # principal junto (some da tela, processo continua no gerenciador
        # de tarefas).
        w.withdraw()

        try:
            if os.path.exists(ICON_ICO):
                w.after(150, lambda: w.iconbitmap(ICON_ICO))  # CTkToplevel precisa de um delay no windows
        except Exception:
            pass

        def _finish_open():
            if not _strip_native_decorations(w, appwindow=False):
                w.overrideredirect(True)
            w.deiconify()
            w.grab_set()

        w.after(10, _finish_open)

        w_hdr = ctk.CTkFrame(w, fg_color=C["panel"], corner_radius=0, height=36)
        w_hdr.place(x=0, y=0, relwidth=1)

        w_dots = tk.Canvas(w_hdr, width=30, height=36, bg=C["panel"], highlightthickness=0)
        w_dots.place(x=12, y=0)
        _draw_titlebar_dots(w_dots, 0, on_close=w.destroy)

        w_title = ctk.CTkLabel(w_hdr, text="settings", font=FS, text_color=C["pink_dim"])
        w_title.place(x=54, y=9)

        _make_draggable(w, [w_hdr, w_title])

        # CTkScrollableFrame em vez de um CTkFrame comum: o conteúdo
        # empilhado abaixo (slider, switch, botões, créditos) passava da
        # altura fixa da janela e, sem scroll, os últimos widgets --
        # [ REFRESH VPN CONFIG ], [ CHECK FOR UPDATES ], créditos, [ CLOSE ]
        # -- ficavam empurrados pra fora da área visível (janela não é
        # redimensionável), como se tivessem "sumido" ao abrir a settings.
        content = ctk.CTkScrollableFrame(w, fg_color="transparent", width=320, height=520,
                                          scrollbar_button_color=C["border"],
                                          scrollbar_button_hover_color=C["pink_dim"])
        content.place(x=0, y=36, width=340, height=520)

        ctk.CTkLabel(content, text="// SETTINGS", font=FT, text_color=C["pink"]).pack(pady=(20, 4))
        ctk.CTkFrame(content, fg_color=C["border"], height=1).pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(content, text="discord restart delay (s)", font=FX, text_color=C["dim"]).pack(anchor="w", padx=24)
        sl = ctk.CTkSlider(content, from_=2, to=30, number_of_steps=28,
                           button_color=C["pink"], progress_color=C["pink_dim"])
        sl.set(10)
        sl.pack(fill="x", padx=24, pady=(0, 16))

        ctk.CTkFrame(content, fg_color=C["border"], height=1).pack(fill="x", padx=20, pady=8)

        st_row = ctk.CTkFrame(content, fg_color="transparent")
        st_row.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(st_row, text="split tunneling", font=FS, text_color=C["white"]).pack(side="left")

        def _on_split_toggle():
            self.vpn.set_split_tunnel(bool(st_var.get()))
            self._log(
                "split tunneling ON — only discord goes through the vpn." if self.vpn.split_tunnel
                else "split tunneling OFF — full tunnel.",
                "pink"
            )

        st_var = ctk.BooleanVar(value=self.vpn.split_tunnel)
        st_switch = ctk.CTkSwitch(st_row, text="", variable=st_var, width=40,
                                   progress_color=C["pink"], button_color=C["white"],
                                   command=_on_split_toggle)
        st_switch.pack(side="right")

        ctk.CTkLabel(content, text="only discord's traffic uses the tunnel;\neverything else stays on your normal connection.",
                     font=FX, text_color=C["dim"], justify="left").pack(anchor="w", padx=24, pady=(0, 12))

        ctk.CTkFrame(content, fg_color=C["border"], height=1).pack(fill="x", padx=20, pady=8)

        ctk.CTkButton(content, text="[ REFRESH VPN CONFIG ]", width=200, height=36,
                      fg_color=C["panel"], border_width=1, border_color=C["pink_dim"],
                      text_color=C["pink_dim"], font=FB, corner_radius=2,
                      command=lambda: threading.Thread(target=self.vpn.setup, daemon=True).start()
                      ).pack(pady=8)

        ctk.CTkButton(content, text="[ CHECK FOR UPDATES ]", width=200, height=36,
                      fg_color=C["panel"], border_width=1, border_color=C["green2"],
                      text_color=C["green2"], font=FB, corner_radius=2,
                      command=self._manual_check_update
                      ).pack(pady=(0, 8))

        ctk.CTkFrame(content, fg_color=C["border"], height=1).pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(content, text="// CREDITS", font=("Courier New", 12, "bold"),
                     text_color=C["pink"]).pack(pady=(4, 4))
        ctk.CTkLabel(content,
                     text="hyavpn\nby hyafranch\n\nservers by riseup.net\ninspired by serial experiments lain\n\n\"no matter where you go,\neveryone is connected.\"",
                     font=FX, text_color=C["white"], justify="center").pack()

        ctk.CTkButton(content, text="[ CLOSE ]", width=100, height=32,
                      fg_color=C["panel"], border_width=1, border_color=C["grey"],
                      text_color=C["grey"], font=FB, corner_radius=2,
                      command=w.destroy).pack(pady=16)


def _ensure_admin():
    """OpenVPN precisa de privilégio de administrador pra criar/configurar
    o adaptador TAP e mexer nas rotas (netsh) no Windows -- sem isso, a
    conexão sobe até abrir o tun mas trava em erros tipo:

        TUN: Setting IPv4 mtu failed: Acesso negado.
        NETSH: ... ERROR: command failed: returned error code 1
        Exiting due to fatal error

    O instalador (installer/setup.py) já pede elevação (--uac-admin), mas
    o app em si nunca pedia -- só o hyavpn-setup.exe. Isso deixava
    QUALQUER conexão falhando (com timeout) pra quem não abrisse o app já
    "Executar como administrador" manualmente. Aqui a gente checa e, se
    não estiver elevado, relança o próprio processo com elevação (prompt
    do UAC) e fecha a instância sem privilégio."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = True  # não trava o app se a checagem falhar por algum motivo
    if is_admin:
        return

    try:
        if getattr(sys, "frozen", False):
            # rodando como .exe compilado (PyInstaller) -- relança o próprio exe
            target, params = sys.executable, ""
        else:
            # rodando via "python app.py" (dev) -- relança o python com o
            # script e os mesmos argumentos
            target = sys.executable
            params = subprocess.list2cmdline([os.path.abspath(__file__)] + sys.argv[1:])

        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
        if rc > 32:  # ShellExecuteW retorna >32 em sucesso
            sys.exit(0)
        # rc <= 32 -- usuário cancelou o UAC ou falhou; segue sem elevação
        # em vez de travar o app, só o AUTO BYPASS vai falhar de novo depois
    except Exception:
        pass


if __name__ == "__main__":
    _set_dpi_aware()
    _ensure_admin()
    _single_instance_socket = acquire_single_instance_lock()
    if _single_instance_socket is None:
        # já existe uma instância rodando — não deixa abrir uma segunda vpn
        try:
            import tkinter.messagebox as messagebox
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showwarning(
                "hyavpn",
                "hyavpn já está em execução.\n\n"
                "só é permitida uma instância por vez, pra evitar\n"
                "abrir duas conexões vpn ao mesmo tempo."
            )
            _r.destroy()
        except Exception:
            pass
        sys.exit(0)

    app = HyaVPN()
    app.mainloop()