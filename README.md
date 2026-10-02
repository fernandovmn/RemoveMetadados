# ZeroMeta AI 🛡️
### Removedor Completo de Metadados, Manifestos C2PA (IA) e EXIF para Fotos (PC Desktop & Celular Android)

**ZeroMeta** é uma solução completa disponível tanto para **Windows (Desktop/CLI)** quanto para **Android (Aplicativo PWA Instalável & Offline)** projetada especificamente para **eliminar todos os metadados** de fotografias e imagens digitais, com foco primordial em **assinaturas e credenciais de Inteligência Artificial (C2PA / Content Credentials da OpenAI, ChatGPT, Midjourney, Adobe Firefly, Google Imagen)**, além de dados EXIF, coordenadas de GPS, modelos de câmera e prompts de geração.

---

## 📱 Como Usar no Celular (Android)

O aplicativo para celular foi desenvolvido como um **Progressive Web App (PWA)** de última geração:
- **100% Privado e Seguro:** As fotos são limpas diretamente na memória RAM/CPU do seu celular via JavaScript binário de alta performance. Nenhuma foto é enviada para a internet ou servidores externos.
- **Instalável na Tela Inicial:** Funciona como um aplicativo nativo do Android, com ícone próprio, tela cheia e sem barra de navegação do browser.
- **Funciona 100% Offline:** Graças ao Service Worker pré-configurado, você pode usá-lo em qualquer lugar, até mesmo no modo avião.
- **Download em Lote (ZIP):** Limpe várias fotos da galeria ao mesmo tempo e baixe todas compactadas com 1 toque.

### Passo a passo para abrir e instalar no Android:
1. Conecte seu celular no mesmo Wi-Fi do seu computador.
2. No seu computador, dê um duplo clique no arquivo:
   ```bat
   Iniciar_App_Celular.bat
   ```
   *(Ou abra o app no PC e clique no botão **"📱 Usar no Celular"** no topo).*
3. Aponte a câmera do seu Android para o **QR Code** exibido na tela (ou digite o endereço IP mostrado no Google Chrome do celular).
4. Ao abrir a página no Chrome do celular:
   - Toque no menu de 3 pontinhos do Chrome e selecione **"Instalar aplicativo"** ou **"Adicionar à tela inicial"**.
5. Pronto! O ícone do **ZeroMeta** estará na sua lista de aplicativos do Android.

---

## 💻 Como Usar no Computador (Windows Desktop)

### 1. Interface Gráfica
Dê um duplo clique no arquivo:
```bat
Iniciar_ZeroMeta.bat
```
*(Ou execute no terminal: `python main.py`)*

Na interface:
1. Clique em **"📂 Selecionar Pasta"** (ou escolha uma foto avulsa).
2. Marque/desmarque a opção de varrer subpastas.
3. Escolha se quer salvar na subpasta `_fotos_limpas` ou sobrescrever os originais (com backup `.bak`).
4. Clique em **"🚀 INICIAR LIMPEZA DE METADADOS"**.

---

### 2. Modo Linha de Comando (CLI)
Para scripts automatizados ou tarefas em lote no terminal:

```bash
# Limpar uma pasta inteira e subpastas (gera pasta _fotos_limpas):
python cli.py "C:\Caminho\Das\Fotos"

# Auditar primeiro (mostra quais fotos possuem IA/C2PA sem alterar nada):
python cli.py "C:\Caminho\Das\Fotos" --audit

# Sobrescrever direto os arquivos originais com backup:
python cli.py "C:\Caminho\Das\Fotos" --overwrite

# Especificar pasta de saída personalizada:
python cli.py "C:\Caminho\Das\Fotos" --output "C:\FotosLimpas"
```

---

## ✨ Tecnologias & O que é removido:
- **C2PA / Content Credentials:** Marcador JPEG `0xFFEB` (APP11 JUMBF) e chunks PNG `caPX`/`c2pa` (OpenAI Media Service, ChatGPT `gpt-image`, Midjourney, Adobe Firefly).
- **Prompts de IA:** Textos ocultos e metadados de geração em PNG e JPEG (Stable Diffusion, ComfyUI, DALL-E).
- **EXIF & GPS:** Coordenadas de localização (Latitude, Longitude), câmera, data e softwares de edição.
- **Sem Perda de Qualidade (Lossless):** Remoção cirúrgica de metadados binários sem recomprimir pixels.
