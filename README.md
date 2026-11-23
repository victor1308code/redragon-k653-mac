# Redragon K653 Control para macOS

Aplicativo nativo e interface web local para configurar a iluminação RGB e perfis do teclado mecânico **Redragon K653-RGB-PRO (3 modos: Cabo USB-C, 2.4G e Bluetooth)** diretamente no **macOS**, sem Windows, VM ou dependências externas de Python.

Construído com comunicação direta via **IOKit.framework / CoreFoundation** (USB HID nativo do macOS) e protocolo HID reconstruído por engenharia reversa a partir do instalador oficial Windows (`Redragon K653-RGB-PRO Setup V1.6.6 20230505.exe` → `KeyboardDrv.exe` + `Cfg.ini`), inspirado na metodologia [morluto/rea](https://github.com/morluto/rea).

---

## Recursos

- **Aplicativo nativo no macOS (`/Applications/Redragon K653 Control.app`)** com visual escuro, plug-and-play e zero termos técnicos na interface.
- **Todos os 22 modos de iluminação oficiais**:
  - Cor Fixa, Respiração, Arco-Íris, Rastro ao Digitar, Gotas de Chuva, Roda Arco-Íris, Ondas ao Toque, Estrelas Cintilantes, Sombra Desvanecendo, Serpente Retrô, Fluxo Neon, Reação Instantânea, Onda Senoidal, Varredura, Catavento Giratório, Cascata Colorida, Desabrochar, Tempestade Giratória, Colisão, Espectro Suave, **Personalizado por Tecla** e **Desligado**.
- **Mapa interativo de 96 teclas**: clique e pinte cada tecla individualmente no modo **Personalizado por Tecla**, com pré-visualização RGB ao vivo no teclado (via cabo USB-C) e 5 slots de customização.
- **3 Perfis salvos independentes (Perfil 1, 2 e 3)**: alterne rapidamente entre configurações completas de modo, brilho, velocidade, direção, paleta de 7 cores e mapa por tecla.
- **Detecção automática dos 3 modos de conexão**:
  - **Cabo USB-C (`0x258A:0x0049`)**: leitura e gravação imediata de RGB, paleta, matriz por tecla e perfis.
  - **Receptor 2.4G (`0x25A7:0xFA70`)**: detecção segura somente-leitura (nunca envia comandos não suportados ao dongle Compx).
  - **Bluetooth**: leitura nativa de bateria quando exposta pelo macOS (`IORegistry` / `SPBluetoothDataType`).
- **Sincronização automática**: você pode editar seus efeitos mesmo sem o cabo; assim que plugar o USB-C, as configurações são gravadas automaticamente no teclado.
- **Zero dependências externas de Python**: usa apenas o `python3` nativo do macOS + frameworks do sistema (`IOKit`, `CoreFoundation`, `Cocoa`, `WebKit`).

---

## Hardware e Modos de Conexão

| Modo | VID:PID | Chipset / Interface | O que funciona |
| :--- | :--- | :--- | :--- |
| **Cabo USB-C** *(chave do teclado em OFF/USB)* | `0x258A:0x0049` | BY Tech / Sinowealth (`MaxFeature=1032B`) | Configuração completa de RGB, perfis, paleta, matriz por tecla e pré-visualização ao vivo |
| **Sem Fio 2.4G** *(chave em 2.4G)* | `0x25A7:0xFA70` | Compx 2.4G Wireless Receiver | Detecção de status conectado (assim como no software Windows, o dongle 2.4G não aceita gravação de RGB nem envia `%` de bateria) |
| **Bluetooth** *(chave em BT, `FN + 1/2/3`)* | Nativo macOS | Bluetooth HID | Detecção de status conectado e leitura de bateria caso reportada pelo firmware ao macOS |

> **Nota sobre bateria no Redragon K653-RGB-PRO:** o hardware desse modelo não envia porcentagem numérica (`%`) pelo cabo USB-C nem pelo receptor 2.4G (nem no software oficial de Windows). A indicação física de carga ocorre pelo LED `M` do próprio teclado (vermelho ao carregar / piscando vermelho quando a bateria está baixa).

---

## Requisitos

- **macOS 12 (Monterey) ou superior** (Apple Silicon ou Intel)
- **Python 3.9+** (nativo do macOS em `/usr/bin/python3`)
- **Xcode Command Line Tools** (necessário apenas para compilar o `.app` nativo):
  ```bash
  xcode-select --install
  ```

---

## Como instalar e usar

### 1. Clonar o repositório

```bash
git clone https://github.com/victor1308code/redragon-k653-mac.git
cd redragon-k653-mac
```

### 2. Opção A — Instalar como Aplicativo nativo no macOS (Recomendado)

Compile e instale diretamente em `/Applications/Redragon K653 Control.app`:

```bash
python3 build_macos_app.py
```

Depois abra pelo **Spotlight**, **Launchpad**, pasta **Aplicativos** ou terminal:

```bash
open "/Applications/Redragon K653 Control.app"
```

> O app inicia automaticamente o backend local em `http://127.0.0.1:18493` e encerra o processo de forma limpa quando fechado.

### 3. Opção B — Rodar direto no navegador (sem compilar `.app`)

```bash
python3 server.py
```

Abra no navegador: **http://127.0.0.1:18493**

---

## Resumo do Protocolo HID (`0x258A:0x0049`)

Reconstruído diretamente da desmontagem de `KeyboardDrv.exe` e verificado em hardware real:

- **Report `0x05` (6 bytes, Feature):**
  - `GetPassword`: `[05 05 81 00 00 00]` → retorna `[05 01 <PSD 6B>]` (`PSD = 02 00 00 00 01 23`)
  - `GetProfile`: `[05 83 C6 00 00 00]` → seguido de `GET_FEATURE` no Report `0x06`
- **Report `0x06` (1032 bytes / `0x408`, Feature):**
  - `SetProfile`: `[06 03 C6 00 00 00 00 00 <136B profile>]` — `prof[0]` sempre `0x00`, `pro1[4]` = `1` se modo Personalizado (`0` nos demais), `pro1[5]` = código `hw` (`1..20`, `21` Personalizado, `0` Desligado), parâmetros de cor/direção/velocidade/brilho em `pro1[0x16..0x3D]` e assinatura `5A A5` em `pro1[0x3E..0x3F]`.
  - `SetLedRgbTab`: `[06 08 C8 00 40 00 00 00]` + 21 bytes zero + 20 modos × 7 cores RGB.
  - `SetLedMatrix`: 2 páginas (`[06 09 CC 00 40 ...]` e `[06 09 D0 00 40 ...]`) com 5 slots de 3 × 126 bytes planares (R, G, B) mapeados pelos `led_idx` das 96 teclas de `Cfg.ini`.
- **Report `0x08` (382 bytes / `0x17E`, Feature):**
  - `SendMusicRGB`: `[08 0A 7A 01 <378B RGB planar>]` para pré-visualização instantânea por tecla.

---

## Estrutura do Projeto

```text
redragon-k653-mac/
├── build_macos_app.py              # Compila e instala /Applications/Redragon K653 Control.app
├── macos_app.swift                 # Wrapper nativo Cocoa + WKWebView
├── server.py                       # Servidor HTTP local (127.0.0.1:18493)
├── device_manager.py               # Gerenciador plug-and-play, 3 perfis (~/.redragon_k653_mac/state.json) e auto-sync
├── hid_bridge.py                   # Bridge nativo IOKit/CoreFoundation + detecção 2.4G/BT
├── protocols/
│   └── k653_protocol.py            # Protocolo byte-exato (Reports 0x05, 0x06 e 0x08)
├── ui/
│   └── index.html                  # Interface gráfica moderna com mapa interativo de 96 teclas
├── assets/
│   ├── Cfg.ini                     # Mapeamento oficial de teclas e modos (extraído do instalador)
│   ├── text.xml                    # Nomes oficiais dos modos
│   ├── keyimg.png / main_nr.png    # Imagens do teclado para o app e ícone
│   └── k653_rea_dump.json          # Metadados extraídos do instalador oficial
├── tests/
│   └── test_k653_protocol.py       # Testes unitários byte-a-byte do protocolo
└── extract_k653_with_rea.py        # Extrator Inno Setup 5.3.3 (LZMA + CallInstructionOptimize)
```

---

## Testes

Execute a suíte de testes unitários (sem precisar do teclado conectado):

```bash
python3 -m unittest discover -s tests -v
```

---

## Permissão no macOS (Monitoramento de Entrada)

Na primeira execução, o macOS pode solicitar permissão em **Ajustes do Sistema → Privacidade e Segurança → Monitoramento de Entrada** para liberar a comunicação HID USB com o teclado. Basta aprovar e reabrir o app.

---

## Projetos relacionados

- Mouse Attack Shark para macOS: [victor1308code/attack-shark-mac](https://github.com/victor1308code/attack-shark-mac)

---

## Créditos e Aviso Legal

- Engenharia reversa inspirada em [morluto/rea](https://github.com/morluto/rea).
- Projeto independente e open-source sem afiliação oficial com a Redragon. Use por sua conta e risco.
- Licença: [MIT](LICENSE).
