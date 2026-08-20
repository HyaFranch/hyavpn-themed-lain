# hyavpn
**by hyafranch**
Estética: Accela / Serial Experiments Lain

---

## Como funciona (visão geral)

Esse repositório é o **código-fonte**. O usuário final nunca clona o repo
nem instala Python — ele baixa **só o `hyavpn-setup.exe`** (compilado,
sem depender de nada instalado na máquina) e ele cuida do resto:

**Link fixo, sempre aponta pra versão mais nova (não muda a cada release):**
```
https://github.com/HyaFranch/hyavpn-themed-lain/releases/latest/download/hyavpn-setup.exe
```

O que o `hyavpn-setup.exe` faz ao abrir:

1. Já pede elevação de administrador sozinho (UAC), sem precisar de
   "executar como administrador" manual — está compilado com `--uac-admin`.
2. Consulta o **último Release no GitHub** (`/releases/latest`).
3. Baixa o asset `hyavpn-dist.zip` desse release — que contém o `hyavpn.exe`
   já compilado, mais as pastas `assets/`, `audio/` e `icons/`.
4. Extrai tudo em `C:\Program Files\hyavpn`.
5. Instala o OpenVPN (se ainda não tiver).
6. Cria o atalho no Desktop apontando direto pro `hyavpn.exe`, com o ícone certo.

Ou seja: **o usuário baixa o `hyavpn-setup.exe` uma única vez**. Tudo mais
(app, assets, áudios, updates futuros) vem do GitHub Releases.

Tanto o `hyavpn.exe` (app) quanto o `hyavpn-setup.exe` (instalador) são
**buildados automaticamente** pelo GitHub Actions
(`.github/workflows/release.yml`) toda vez que você cria uma tag `vX.Y.Z` —
não precisa compilar nada na mão.

---

## Publicando uma nova versão

1. Atualize `__version__` em `app.py` (ex: `"1.1.0"`).
2. Commit e push.
3. Crie e envie a tag:
   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```
4. O GitHub Actions builda o `hyavpn.exe` (app) e o `hyavpn-setup.exe`
   (instalador), empacota `hyavpn-dist.zip` (exe + assets + audio + icons)
   e publica os dois como assets do Release automaticamente.

Pronto — o instalador (pra quem for instalar do zero) e o próprio app
(pra quem já tem instalado, via checagem de update) já vão enxergar essa
versão nova.

---

## Auto-update

O app checa a versão mais recente no GitHub automaticamente ao abrir
(sem travar a UI) e também tem um botão **[ CHECK FOR UPDATES ]** nas
Settings. Se achar uma versão nova:

- Baixa o `hyavpn-dist.zip` do release mais recente.
- Extrai numa pasta temporária.
- Agenda a substituição dos arquivos via um script auxiliar que espera o
  processo atual fechar (o Windows não deixa sobrescrever um `.exe` rodando),
  copia os arquivos novos por cima, e reabre o app.

Configs/certificados da VPN ficam em `%APPDATA%\hyavpn`, fora da pasta de
instalação — então um update nunca apaga sua config atual.

---

## Instância única

O app usa uma trava local (bind numa porta fixa em `127.0.0.1`) pra impedir
abrir uma segunda instância — evita rodar duas VPNs/túneis OpenVPN ao mesmo
tempo, brigando entre si.

---

## Split tunneling

Nas Settings dá pra ligar/desligar split tunneling. Quando **ligado**, só o
tráfego dos domínios do Discord (`discord.com`, `gateway.discord.gg`,
`cdn.discordapp.com`, etc.) passa pela VPN — o resto da sua internet segue
pela conexão normal. Quando **desligado**, é full tunnel (tudo pela VPN).

Como é baseado em resolver IPs de CDN (que rotacionam), a cobertura não é
100% garantida pra toda mídia/voz em tempo real — mas cobre bem API/gateway,
que é o essencial pro bypass funcionar. Pode eventualmente falhar/bugar
dependendo de qual IP de CDN caiu na hora; se acontecer, é só rodar de novo
ou desligar o split tunneling temporariamente.

---

## Estrutura do repositório

```
hyavpn-themed-lain/
├── app.py                    # app principal (fonte)
├── requirements.txt          # deps de build/dev (não pro usuário final)
├── assets/                   # gifs/pngs do personagem (idle/connecting/connected)
├── audio/                    # sons (connecting/connected/success)
├── installer/
│   └── setup.py              # bootstrapper -- única coisa que o usuário baixa
├── .github/workflows/
│   └── release.yml           # build automático do .exe a cada tag
└── README.md
```

---

## Rodando localmente (dev)

```
pip install -r requirements.txt
python app.py
```

Pra gerar os exes manualmente (sem esperar o CI):
```
pyinstaller --onefile --windowed --name hyavpn --icon icons/icon.ico --add-data "icons;icons" app.py
pyinstaller --onefile --windowed --name hyavpn-setup --icon icons/icon.ico --add-data "icons;icons" --uac-admin installer/setup.py
```

---

## Ícone

Fica em `icons/icon.ico` (usado no `.exe`, na janela do app e no atalho do
Desktop). Já vem um placeholder no estilo Accela/Lain — pra trocar pelo seu:

1. Gere um `.ico` de verdade, multi-resolução: **16, 32, 48, 256px**
   (dá pra fazer com o próprio Pillow: `Image.save("icon.ico", sizes=[(16,16),(32,32),(48,48),(256,256)])`
   ou qualquer conversor online de PNG → ICO).
2. Substitua `icons/icon.ico` (mantendo esse nome/caminho).
3. Se quiser trocar também a versão usada em README/preview, atualize
   `icons/icon.png`.
4. Não precisa mexer em mais nada — o build (`release.yml`) já embute
   `icons/icon.ico` no `.exe` automaticamente na próxima tag publicada.

---

## Personagem

Coloque em `assets/` (fundo transparente, 220x220):
| Arquivo | Expressão |
|---|---|
| `idle.gif` / `idle.png` | Neutra, em espera |
| `connecting.gif` / `connecting.png` | Séria/focada |
| `connected.gif` / `connected.png` | Satisfeita/feliz |

GIF tem prioridade sobre PNG; se nenhum existir, cai num sketch placeholder
gerado por código.

---

## Áudio

Em `audio/`:
| Arquivo | Quando toca |
|---|---|
| `connecting.mp3` | Enquanto conecta |
| `connected.mp3` | Ao conectar na VPN |
| `success.mp3` | "Pode transmitir agora" |

---

## Como funciona o bypass

1. Clica **AUTO BYPASS**
2. App busca config do Riseup (`https://riseup.net/provider.json`)
3. Conecta OpenVPN nos servidores do Riseup (full tunnel ou só Discord,
   dependendo do split tunneling)
4. Mata o Discord e reabre
5. Aguarda o Discord iniciar
6. Desconecta a VPN
7. Mostra overlay "STREAM ENABLED"

O Discord reconecta com o IP da VPN já liberado — a restrição é contornada.

---

## Créditos
By hyafranch
Servers by riseup.net (free, no logs, no account needed)
Inspired by Serial Experiments Lain
