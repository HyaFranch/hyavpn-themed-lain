# hyavpn — notas de desenvolvimento (pywebview edition)

Documentação técnica pra quem for mexer no código, compilar manualmente
ou publicar uma versão nova. Se você só quer usar o app, veja o [README.md](README.md).

---

## Mudanças em relação à versão customtkinter

A UI foi reescrita completamente usando **pywebview** no lugar de customtkinter.

| Aspecto | customtkinter (antigo) | pywebview (atual) |
|---|---|---|
| Renderer | Tkinter/GDI+ | WebView2/Chromium (Windows) |
| Arrasto de janela | Hack via WinAPI (`WS_EX_COMPOSITED`, `WS_NCLBUTTONDOWN`) | CSS `-webkit-app-region: drag` nativo |
| Titlebar flash | Exigia workaround com `_strip_native_decorations` | Resolvido nativamente com `frameless=True` |
| Estilo | Python (paleta `C = {...}`, widgets CTk) | HTML/CSS (variáveis CSS, transições, animações) |
| Personagem GIF | PIL + `ImageSequence` rodando em timer Tkinter | `<img src="...gif">` — o browser anima |
| Performance scroll | Nenhuma | GPU composited pelo Chromium |
| Fundo animado | Canvas Tkinter + `after(50ms)` | Canvas Web + `requestAnimationFrame` |

A lógica Python (VPNManager, flow, auto-update, single instance, admin elevation)
foi mantida inteiramente — só a UI mudou.

---

## Estrutura do repositório

```
hyavpn/
├── app.py                    # app principal (pywebview)
├── requirements.txt          # deps de build/dev
├── ui/
│   └── index.html            # interface HTML/CSS/JS completa
├── assets/                   # gifs/pngs do personagem (idle/connecting/connected)
├── audio/                    # sons (connecting/connected/success)
├── icons/                    # icon.ico, icon.png
├── installer/
│   └── setup.py              # bootstrapper — única coisa que o usuário baixa
├── .github/workflows/
│   └── release.yml           # build automático do .exe a cada tag
├── README.md
└── DEV.md                    # este arquivo
```

---

## Rodando localmente (dev)

```
pip install -r requirements.txt
python app.py
# ou com devtools do WebView2 abertos:
python app.py --debug
```

**Nota:** No Windows, o pywebview usa WebView2 (já incluído no Windows 11).
No Windows 10, instale o runtime: https://developer.microsoft.com/webview2

---

## Como funciona o drag (pywebview)

A titlebar tem CSS `-webkit-app-region: drag` — isso diz ao WebView2 que
aquela região é a área de arrasto da janela. Os botões (dots) têm
`-webkit-app-region: no-drag` pra excluí-los do arrasto. Zero código Python
necessário, zero hacks de WinAPI, zero bug de janela crescendo em telas
com escala >100%.

---

## Como funciona a UI (fluxo Python → JS)

```
Python (app.py)          JS (ui/index.html)
──────────────           ──────────────────
JsApi._js(expr)   ──→    window.evaluate_js()
                          └─ window.hyavpn.setState('connecting')
                          └─ window.hyavpn.addLog('...', 'pink')
                          └─ window.hyavpn.showUpdateBadge()

JS click           ──→    pywebview.api.start_bypass()
                   ──→    pywebview.api.set_split_tunnel(true)
                   ──→    pywebview.api.close_window()
```

---

## Build (PyInstaller)

```bash
# App principal
pyinstaller --onefile --windowed --name hyavpn \
  --icon icons/icon.ico \
  --add-data "icons;icons" \
  --add-data "assets;assets" \
  --add-data "audio;audio" \
  --add-data "ui;ui" \
  --uac-admin \
  app.py

# Instalador
pyinstaller --onefile --windowed --name hyavpn-setup \
  --icon icons/icon.ico \
  --add-data "icons;icons" \
  --uac-admin \
  installer/setup.py
```

O `--add-data "ui;ui"` é o novo item em relação à versão antiga —
o HTML da interface precisa ir junto no bundle.

O CI (`.github/workflows/release.yml`) faz esse build automaticamente
a cada tag `vX.Y.Z`. Atualize `__version__` em `app.py`, crie a tag,
e o GitHub Actions publica os assets.

---

## Publicando nova versão

1. Atualize `__version__` em `app.py` (ex: `"1.1.0"`).
2. Commit e push.
3. Crie e envie a tag:
   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```

---

## Personagem

Coloque em `assets/` (fundo transparente):

| Arquivo | Expressão | Tamanho sugerido |
|---|---|---|
| `idle.gif` / `idle.png` | Neutra, em espera | 220×220 |
| `connecting.gif` / `connecting.png` | Séria/focada | 220×220 |
| `connected.gif` / `connected.png` | Satisfeita/feliz | 220×220 |

GIF é exibido nativamente pelo browser (sem código Python de animação).
Durante o estado "connecting", um filtro CSS de glitch é aplicado sobre
o `<img>` — `hue-rotate`, `saturate`, `translate` em `@keyframes`.

---

## Áudio

Em `audio/`:

| Arquivo | Quando toca |
|---|---|
| `connecting.mp3` | Enquanto conecta |
| `connected.mp3` | Ao conectar na VPN |
| `success.mp3` | "Pode transmitir agora" |

---

## Como funciona o bypass (fluxo técnico)

1. Clica **AUTO BYPASS** → JS chama `pywebview.api.start_bypass()`
2. Python: busca config do Riseup, gera `.ovpn`
3. Python: sobe OpenVPN, aguarda "Initialization Sequence Completed"
4. Python: mata o Discord, espera `discord_delay_s` segundos, reabre
5. Python: aguarda processo do Discord subir
6. Python: desconecta VPN, chama `hyavpn.setState('success')` via JS
7. JS: exibe overlay animado "STREAM ENABLED"
