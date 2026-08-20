# hyavpn
**by hyafranch**
Estética: Accela / Serial Experiments Lain

---

## O que é

App de VPN pra Windows que conecta nos servidores do Riseup e reinicia o
Discord com um novo IP — contorna restrições de stream/vídeo que dependem
de geolocalização.

---

## Instalação

1. Baixe o instalador:
   ```
   https://github.com/HyaFranch/hyavpn-themed-lain/releases/latest/download/hyavpn-setup.exe
   ```
2. Abra o `hyavpn-setup.exe`. Ele já pede permissão de administrador
   sozinho (é normal, precisa disso pra instalar o OpenVPN).
3. Clique em **[ INSTALL ]** e aguarde. Ele baixa o app, instala o
   OpenVPN (se você ainda não tiver) e cria um atalho no Desktop.
4. Pronto — abra pelo atalho `hyavpn` que apareceu no Desktop.

Não precisa instalar Python nem nada além disso — é só esse único arquivo.

---

## Como usar

1. Abra o `hyavpn`.
2. Clique em **AUTO BYPASS**.
3. O app conecta na VPN, reinicia o Discord automaticamente e desconecta
   a VPN assim que o Discord volta.
4. Quando aparecer **"STREAM ENABLED"**, é só usar o Discord normalmente
   — o vídeo/stream já deve funcionar sem a restrição.

### Split tunneling

Nas **Settings**, dá pra escolher:
- **Ligado**: só o tráfego do Discord passa pela VPN — o resto da sua
  internet (jogos, navegador, etc.) continua na conexão normal.
- **Desligado**: tudo passa pela VPN (full tunnel) enquanto o bypass roda.

Se em algum momento o bypass não funcionar direito com split tunneling
ligado, tente rodar de novo ou desligar essa opção temporariamente.

### Atualizações

O app confere sozinho se tem uma versão nova toda vez que abre, e também
tem um botão **[ CHECK FOR UPDATES ]** nas Settings. Quando encontra uma
atualização, baixa e substitui os arquivos automaticamente — você não
precisa baixar o instalador de novo.

Suas configurações e certificados da VPN ficam salvos separado da pasta
de instalação, então uma atualização nunca apaga isso.

---

## Perguntas comuns

**Precisa de conta em algum lugar?**
Não. Os servidores são do Riseup (riseup.net) — gratuitos, sem conta e
sem logs.

**Consigo abrir duas janelas do app ao mesmo tempo?**
Não, e é proposital — evita abrir duas VPNs brigando entre si.

**O instalador é seguro?**
O código-fonte inteiro está público neste repositório. O `.exe` é
compilado automaticamente pelo GitHub a partir desse mesmo código (via
GitHub Actions) — não é montado manualmente por ninguém.

---

## Créditos
By hyafranch
Servers by riseup.net (free, no logs, no account needed)
Inspired by Serial Experiments Lain

---

Quer mexer no código, compilar você mesmo ou publicar uma versão nova?
Veja [DEV.md](DEV.md).
