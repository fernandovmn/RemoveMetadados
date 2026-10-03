/**
 * ZeroMeta AI - Mobile App Core (PWA)
 * Pure Client-Side Binary Stripper for Android & iOS
 * Removes C2PA (OpenAI / ChatGPT / Midjourney / Adobe), EXIF, GPS and Prompts.
 * Works 100% offline, zero server required.
 */

// ==========================================
// 1. SERVICE WORKER REGISTRATION (OFFLINE)
// ==========================================
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js')
      .then(reg => console.log('ZeroMeta ServiceWorker registrado:', reg.scope))
      .catch(err => console.warn('ServiceWorker aviso:', err));
  });
}

// ==========================================
// 2. BINARY STRIPPING ENGINE
// ==========================================

function bufferToBinaryString(buffer, start = 0, length = null) {
  const bytes = new Uint8Array(buffer, start, length ?? (buffer.byteLength - start));
  let str = '';
  const len = Math.min(bytes.length, 120000);
  for (let i = 0; i < len; i++) {
    str += String.fromCharCode(bytes[i]);
  }
  return str;
}

// Inspect image metadata
async function inspectMetadata(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const ext = file.name.split('.').pop().toLowerCase();

  const result = {
    fileName: file.name,
    fileSize: file.size,
    fileType: file.type || ext.toUpperCase(),
    hasC2PA: false,
    c2paDetails: null,
    hasExif: false,
    hasGps: false,
    hasAiPrompt: false,
    prompts: [],
    badges: [],
  };

  const textSample = bufferToBinaryString(buffer, 0, Math.min(buffer.byteLength, 150000));

  // A. JPEG Inspection
  if (bytes[0] === 0xFF && bytes[1] === 0xD8) {
    let pos = 2;
    const len = bytes.length;

    while (pos < len) {
      if (bytes[pos] !== 0xFF) { pos++; continue; }
      const marker = bytes[pos + 1];

      if (marker === 0xDA || marker === 0xD9) break;
      if (pos + 4 > len) break;

      const markerLength = view.getUint16(pos + 2);

      // APP11 = 0xEB (C2PA JUMBF Manifest)
      if (marker === 0xEB) {
        result.hasC2PA = true;
        let snippet = bufferToBinaryString(buffer, pos + 4, Math.min(markerLength, 2000));
        let agent = "Assinatura C2PA de IA";
        if (snippet.includes("OpenAI") || snippet.includes("ChatGPT")) {
          agent = "OpenAI (ChatGPT / DALL-E)";
        } else if (snippet.includes("Midjourney")) {
          agent = "Midjourney C2PA";
        } else if (snippet.includes("Adobe") || snippet.includes("Firefly")) {
          agent = "Adobe Firefly C2PA";
        } else if (snippet.includes("Google") || snippet.includes("Imagen")) {
          agent = "Google Imagen C2PA";
        }
        result.c2paDetails = agent;
        result.badges.push(`🤖 C2PA: ${agent}`);
      }

      // APP1 = 0xE1 (EXIF / XMP)
      if (marker === 0xE1) {
        result.hasExif = true;
        let snippet = bufferToBinaryString(buffer, pos + 4, Math.min(markerLength, 500));
        if (snippet.includes("GPS") || snippet.includes("GPSInfo")) {
          result.hasGps = true;
          result.badges.push("📍 Localização GPS");
        } else if (!result.badges.includes("📷 Dados EXIF")) {
          result.badges.push("📷 Dados EXIF");
        }
      }

      // COM = 0xFE (Comments / Prompts)
      if (marker === 0xFE) {
        let comment = bufferToBinaryString(buffer, pos + 4, markerLength - 2);
        if (/prompt|dall-e|ai|midjourney|steps:/i.test(comment)) {
          result.hasAiPrompt = true;
          result.prompts.push(comment.trim());
          if (!result.badges.includes("🧠 Prompt IA")) result.badges.push("🧠 Prompt IA");
        }
      }

      pos += 2 + markerLength;
    }
  }

  // B. PNG Inspection
  else if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E && bytes[3] === 0x47) {
    let pos = 8;
    const len = bytes.length;

    while (pos + 8 <= len) {
      const chunkLength = view.getUint32(pos);
      const chunkType = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);

      if (chunkType === 'caPX' || chunkType === 'c2pa') {
        result.hasC2PA = true;
        result.c2paDetails = "C2PA Manifest Box (caPX)";
        result.badges.push("🤖 C2PA / Content Credentials");
      }

      if (['tEXt', 'zTXt', 'iTXt'].includes(chunkType)) {
        let chunkText = bufferToBinaryString(buffer, pos + 8, Math.min(chunkLength, 4000));
        if (/parameters|prompt|workflow|Software.*ChatGPT|DALL-E/i.test(chunkText)) {
          result.hasAiPrompt = true;
          result.prompts.push(chunkText.slice(0, 150));
          if (!result.badges.includes("🧠 Prompt IA")) result.badges.push("🧠 Prompt IA");
        }
      }

      if (chunkType === 'eXIf') {
        result.hasExif = true;
        if (!result.badges.includes("📷 EXIF")) result.badges.push("📷 EXIF");
      }

      pos += 12 + chunkLength;
      if (chunkType === 'IEND') break;
    }
  }

  // C. Fallback binary scan
  if (!result.hasC2PA && /urn:c2pa:|OpenAI Media Service|trainedAlgorithmicMedia/i.test(textSample)) {
    result.hasC2PA = true;
    result.c2paDetails = "OpenAI C2PA Manifest";
    result.badges.push("🤖 C2PA (OpenAI)");
  }

  if (result.badges.length === 0) {
    result.badges.push("Nenhum metadado detectado");
  }

  return result;
}

// Lossless JPEG Stripping
function stripJpegLossless(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(arrayBuffer);
  const len = bytes.length;

  if (bytes[0] !== 0xFF || bytes[1] !== 0xD8) {
    throw new Error("Não é um JPEG válido");
  }

  const outputChunks = [bytes.subarray(0, 2)];
  let pos = 2;

  while (pos < len) {
    if (bytes[pos] !== 0xFF) { pos++; continue; }
    while (bytes[pos] === 0xFF && pos < len) { pos++; }
    if (pos >= len) break;

    const marker = bytes[pos];
    pos++;

    if (marker === 0xD8 || marker === 0xD9) continue;
    if (marker >= 0xD0 && marker <= 0xD7) {
      outputChunks.push(new Uint8Array([0xFF, marker]));
      continue;
    }

    if (marker === 0xDA) { // SOS - Start of Scan
      outputChunks.push(new Uint8Array([0xFF, 0xDA]));
      outputChunks.push(bytes.subarray(pos));
      break;
    }

    if (pos + 2 > len) break;
    const length = view.getUint16(pos);
    const chunkTotal = length;

    // Discard APP1..APP15 and COM (0xFE)
    const isDiscard = (marker >= 0xE1 && marker <= 0xEF) || (marker === 0xFE);

    if (!isDiscard) {
      outputChunks.push(new Uint8Array([0xFF, marker]));
      outputChunks.push(bytes.subarray(pos, pos + chunkTotal));
    }

    pos += chunkTotal;
  }

  return new Blob(outputChunks, { type: 'image/jpeg' });
}

// Lossless PNG Stripping
function stripPngLossless(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(arrayBuffer);
  const len = bytes.length;

  if (bytes[0] !== 0x89 || bytes[1] !== 0x50 || bytes[2] !== 0x4E || bytes[3] !== 0x47) {
    throw new Error("Não é um PNG válido");
  }

  const keepChunks = new Set(['IHDR', 'PLTE', 'tRNS', 'IDAT', 'IEND']);
  const outputParts = [bytes.subarray(0, 8)];
  let pos = 8;

  while (pos + 8 <= len) {
    const chunkLength = view.getUint32(pos);
    const chunkType = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
    const chunkTotalLen = 12 + chunkLength;

    if (pos + chunkTotalLen > len) break;

    if (keepChunks.has(chunkType)) {
      outputParts.push(bytes.subarray(pos, pos + chunkTotalLen));
    }

    pos += chunkTotalLen;
    if (chunkType === 'IEND') break;
  }

  return new Blob(outputParts, { type: 'image/png' });
}

// Canvas Fallback
async function cleanWithCanvas(file, format = 'image/jpeg', quality = 0.95) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || img.width;
      canvas.height = img.naturalHeight || img.height;

      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);

      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Falha ao exportar imagem via canvas"));
      }, format, quality);
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Erro ao carregar imagem para canvas"));
    };

    img.src = url;
  });
}

// Master Cleaner
async function cleanImage(file) {
  const originalSize = file.size;
  const ext = file.name.split('.').pop().toLowerCase();
  const infoBefore = await inspectMetadata(file);

  let cleanBlob = null;
  let method = 'lossless';

  try {
    const buffer = await file.arrayBuffer();

    if (['jpg', 'jpeg', 'jfif'].includes(ext) || file.type === 'image/jpeg') {
      cleanBlob = stripJpegLossless(buffer);
      method = 'lossless_jpeg';
    } else if (ext === 'png' || file.type === 'image/png') {
      cleanBlob = stripPngLossless(buffer);
      method = 'lossless_png';
    }
  } catch (err) {
    console.warn("Lossless falhou, fallback para canvas:", err);
  }

  if (!cleanBlob) {
    const targetType = (ext === 'png' || file.type === 'image/png') ? 'image/png' : 'image/jpeg';
    cleanBlob = await cleanWithCanvas(file, targetType, 0.96);
    method = 'canvas_reconstruction';
  }

  const newSize = cleanBlob.size;
  const bytesSaved = Math.max(0, originalSize - newSize);

  return {
    cleanBlob,
    fileName: file.name,
    originalSize,
    newSize,
    bytesSaved,
    method,
    infoBefore,
    realPath: file.realPath || null,
    uri: file.uri || null,
  };
}


// ==========================================
// 3. UI CONTROLLER & EVENT LISTENERS
// ==========================================

let selectedFiles = [];
let processedResults = [];
let deferredInstallPrompt = null;

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnCleanAll = document.getElementById('btn-clean-all');
const btnDownloadAll = document.getElementById('btn-download-all');
const postCleanPanel = document.getElementById('post-clean-panel');
const btnSaveAll = document.getElementById('btn-save-all');
const btnShareAll = document.getElementById('btn-share-all');
const imageList = document.getElementById('image-list');
const progressCard = document.getElementById('progress-card');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const statTotal = document.getElementById('stat-total');
const statC2pa = document.getElementById('stat-c2pa');
const statSaved = document.getElementById('stat-saved');
const installBanner = document.getElementById('install-banner');
const btnInstall = document.getElementById('btn-install');
const detailModal = document.getElementById('detail-modal');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const btnCloseModal = document.getElementById('btn-close-modal');

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// PWA Install Detection
const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
if (isStandalone && installBanner) {
  installBanner.style.display = 'none';
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  if (installBanner) installBanner.style.display = 'flex';
});

if (btnInstall) {
  btnInstall.addEventListener('click', async () => {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      const { outcome } = await deferredInstallPrompt.userChoice;
      if (outcome === 'accepted') {
        installBanner.style.display = 'none';
      }
      deferredInstallPrompt = null;
    } else {
      // Guide user with step-by-step modal
      showInstallGuideModal();
    }
  });
}

function showInstallGuideModal() {
  if (!detailModal || !modalTitle || !modalBody) return;
  modalTitle.textContent = "📱 Como Instalar o ZeroMeta";
  
  let html = `
    <div style="font-size:0.9rem; line-height:1.6; color:#e2e8f0;">
      <p style="margin-bottom:12px;">Para ter o app fixado na tela inicial do seu Android com ícone próprio e funcionamento offline:</p>
      
      <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:12px; border-left:3px solid var(--accent-cyan);">
        <strong>Passo 1:</strong> Se você abriu pelo leitor de QR Code ou Câmera, toque no menu ou no ícone de bússola/navegador e selecione <strong>"Abrir no Chrome"</strong>.
      </div>

      <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:12px; border-left:3px solid var(--accent-green);">
        <strong>Passo 2:</strong> No Google Chrome, toque nos <strong>3 pontinhos</strong> (canto superior direito).
      </div>

      <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:14px; border-left:3px solid #f59e0b);">
        <strong>Passo 3:</strong> Escolha <strong>"Instalar aplicativo"</strong> ou <strong>"Adicionar à tela inicial"</strong>.
      </div>

      <div style="text-align:center; margin-top:14px;">
        <button id="btn-copy-url" style="background:var(--accent-blue); color:white; border:none; padding:10px 16px; border-radius:6px; font-weight:600; cursor:pointer; width:100%;">
          📋 Copiar Link para abrir no Chrome
        </button>
      </div>
    </div>
  `;
  modalBody.innerHTML = html;
  detailModal.style.display = 'flex';

  setTimeout(() => {
    const btnCopy = document.getElementById('btn-copy-url');
    if (btnCopy) {
      btnCopy.onclick = () => {
        navigator.clipboard.writeText(window.location.href);
        btnCopy.textContent = "✅ Link Copiado! Cole no Chrome";
        setTimeout(() => { btnCopy.textContent = "📋 Copiar Link para abrir no Chrome"; }, 3000);
      };
    }
  }, 100);
}


// File Select Handlers
const isNativeApp = !!(window.AndroidBridge && typeof window.AndroidBridge.isNative === 'function' && window.AndroidBridge.isNative());
if (isNativeApp && installBanner) {
  installBanner.style.display = 'none';
}

if (dropZone && fileInput) {
  dropZone.addEventListener('click', () => {
    if (window.AndroidBridge && typeof window.AndroidBridge.pickPhotosNative === 'function') {
      window.AndroidBridge.pickPhotosNative();
    } else {
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    await handleSelectedFiles(files);
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--accent-cyan)';
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = 'rgba(56, 189, 248, 0.35)';
  });
  dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'rgba(56, 189, 248, 0.35)';
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length) await handleSelectedFiles(files);
  });
}

// Global Callback for Native Android Photo Picker
window.onNativePhotosPicked = async function(items) {
  if (!items || !items.length) return;
  const files = [];

  for (const item of items) {
    try {
      let base64 = null;
      if (window.AndroidBridge && window.AndroidBridge.readPhotoBase64ByUri && item.uri) {
        base64 = window.AndroidBridge.readPhotoBase64ByUri(item.uri);
      } else if (window.AndroidBridge && window.AndroidBridge.readPhotoBase64 && item.realPath) {
        base64 = window.AndroidBridge.readPhotoBase64(item.realPath);
      }

      if (base64) {
        const bin = atob(base64);
        const u8 = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
          u8[i] = bin.charCodeAt(i);
        }
        const mime = (item.name && item.name.toLowerCase().endsWith('.png')) ? 'image/png' : 'image/jpeg';
        const file = new File([u8], item.name, { type: mime });
        file.realPath = item.realPath || null;
        file.uri = item.uri || null;
        files.push(file);
      }
    } catch (err) {
      console.error("Erro ao carregar foto nativa selecionada:", err);
    }
  }

  if (files.length > 0) {
    await handleSelectedFiles(files);
  }
};

async function handleSelectedFiles(files) {
  selectedFiles = files;
  processedResults = [];
  imageList.innerHTML = '';
  if (postCleanPanel) postCleanPanel.style.display = 'none';
  if (btnDownloadAll) btnDownloadAll.style.display = 'none';
  btnCleanAll.disabled = false;

  statTotal.textContent = files.length;
  statC2pa.textContent = '0';
  statSaved.textContent = '0 KB';

  let c2paCount = 0;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const info = await inspectMetadata(file);
    if (info.hasC2PA) c2paCount++;

    const card = renderFileCard(file, info, i);
    imageList.appendChild(card);
  }

  statC2pa.textContent = c2paCount;
}

function renderFileCard(file, info, index) {
  const card = document.createElement('div');
  card.className = 'image-item';
  card.id = `card-${index}`;

  const thumbUrl = URL.createObjectURL(file);

  const badgesHtml = info.badges.map(b => {
    let cls = 'badge-clean';
    if (b.includes('C2PA')) cls = 'badge-c2pa';
    else if (b.includes('GPS') || b.includes('EXIF')) cls = 'badge-exif';
    else if (b.includes('Prompt')) cls = 'badge-prompt';
    return `<span class="badge ${cls}">${b}</span>`;
  }).join(' ');

  card.innerHTML = `
    <img src="${thumbUrl}" class="item-thumb" alt="thumb">
    <div class="item-info">
      <div class="item-name">${file.name}</div>
      <div class="item-badges" id="badges-${index}">${badgesHtml}</div>
      <div class="item-meta" id="meta-${index}">Tamanho: ${formatBytes(file.size)}</div>
    </div>
    <div id="action-${index}">
      <button class="btn-item-dl" style="opacity: 0.7;" onclick="window.inspectDetails(${index})">Ver</button>
    </div>
  `;

  return card;
}

// Clean All Action
if (btnCleanAll) {
  btnCleanAll.addEventListener('click', async () => {
    if (!selectedFiles.length) return;

    btnCleanAll.disabled = true;
    progressCard.style.display = 'block';
    if (postCleanPanel) postCleanPanel.style.display = 'none';

    let totalSaved = 0;
    let c2paRemoved = 0;

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      progressText.textContent = `Limpando [${i + 1}/${selectedFiles.length}]: ${file.name}`;
      progressFill.style.width = `${((i + 1) / selectedFiles.length) * 100}%`;

      const res = await cleanImage(file);
      processedResults.push(res);

      totalSaved += res.bytesSaved;
      if (res.infoBefore.hasC2PA) c2paRemoved++;

      const badgesEl = document.getElementById(`badges-${i}`);
      const metaEl = document.getElementById(`meta-${i}`);
      const actionEl = document.getElementById(`action-${i}`);

      if (badgesEl) {
        badgesEl.innerHTML = `<span class="badge badge-clean">✅ 100% Limpo (Sem Metadados)</span>`;
      }
      if (metaEl) {
        metaEl.textContent = `${formatBytes(res.originalSize)} ➔ ${formatBytes(res.newSize)} (Economizou ${formatBytes(res.bytesSaved)})`;
      }
      if (actionEl) {
        actionEl.innerHTML = `<button class="btn-item-dl" style="opacity:0.85; padding:6px 10px;" title="Baixar esta foto avulsa" onclick="window.downloadSingle(${i})">⬇️</button>`;
      }
    }

    statSaved.textContent = formatBytes(totalSaved);
    statC2pa.textContent = c2paRemoved;

    progressText.textContent = `Concluído! ${selectedFiles.length} fotos limpas.`;
    btnCleanAll.disabled = false;

    // Show the master action panel to save all or share all
    if (postCleanPanel) {
      postCleanPanel.style.display = 'block';
      postCleanPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
}

function getCleanFileName(originalName) {
  const mode = document.querySelector('input[name="naming-mode"]:checked')?.value || 'exact';
  if (mode === 'exact') {
    return originalName; // Preserves exact original filename to replace/overwrite
  } else if (mode === 'prefix') {
    return `[LIMPA]_${originalName}`;
  }
  return originalName;
}

// Native Overwrite and Save Helpers
async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result;
      const base64 = dataUrl.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function saveOrOverwriteItem(item, index) {
  const mode = document.querySelector('input[name="naming-mode"]:checked')?.value || 'exact';
  const ext = (item.fileName || '').split('.').pop().toLowerCase();
  const isJpg = ['jpg', 'jpeg', 'jfif'].includes(ext) || (item.cleanBlob && item.cleanBlob.type === 'image/jpeg');
  const isPng = ext === 'png' || (item.cleanBlob && item.cleanBlob.type === 'image/png');

  // Regra solicitada:
  // Se for JPG: tenta salvar por cima do original.
  // Se for PNG: NUNCA grava por cima; cria sempre um arquivo novo no mesmo local da galeria!
  let targetFileName = item.fileName;
  if (isPng) {
    if (!targetFileName.startsWith('[LIMPA]_')) {
      targetFileName = `[LIMPA]_${targetFileName}`;
    }
  } else {
    targetFileName = getCleanFileName(item.fileName);
  }

  if (window.AndroidBridge) {
    try {
      const base64 = await blobToBase64(item.cleanBlob);

      // Apenas JPG tenta sobrescrever diretamente o arquivo original
      if (isJpg && mode === 'exact') {
        let overwritten = false;
        if (item.realPath && window.AndroidBridge.overwritePhoto) {
          overwritten = window.AndroidBridge.overwritePhoto(item.realPath, base64);
        }
        if (!overwritten && item.uri && window.AndroidBridge.overwritePhotoByUri) {
          overwritten = window.AndroidBridge.overwritePhotoByUri(item.uri, base64);
        }
        if (overwritten) {
          return { success: true, mode: 'overwritten', name: item.fileName, isJpg: true };
        }
      }

      // Se for PNG (ou JPG que não pôde ser sobrescrito):
      // Salva como novo arquivo na Galeria NO MESMO LOCAL / PASTA da foto original!
      if (window.AndroidBridge.savePhotoToGallery) {
        const saved = window.AndroidBridge.savePhotoToGallery(targetFileName, base64, item.realPath || "");
        if (saved) {
          return { success: true, mode: 'saved_gallery', name: targetFileName, isPng: isPng, isJpg: isJpg };
        }
      }
    } catch (e) {
      console.warn("Falha ao salvar no storage nativo:", e);
    }
  }

  // Fallback para navegador web (PWA / desktop)
  const url = URL.createObjectURL(item.cleanBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = targetFileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { success: true, mode: 'downloaded', name: targetFileName, isPng: isPng };
}

// Batch Save All Photos
if (btnSaveAll) {
  btnSaveAll.addEventListener('click', async () => {
    if (!processedResults.length) return;

    btnSaveAll.disabled = true;
    btnSaveAll.innerHTML = `<span>⏳</span> Salvando ${processedResults.length} Foto(s)...`;

    let overwrittenJpgCount = 0;
    let newPngCount = 0;
    let savedGalleryCount = 0;
    let downloadedCount = 0;

    for (let i = 0; i < processedResults.length; i++) {
      const res = await saveOrOverwriteItem(processedResults[i], i);
      if (res.mode === 'overwritten') {
        overwrittenJpgCount++;
      } else if (res.mode === 'saved_gallery') {
        if (res.isPng) newPngCount++;
        else savedGalleryCount++;
      } else {
        downloadedCount++;
      }
      await new Promise(r => setTimeout(r, 150));
    }

    if (overwrittenJpgCount > 0 && newPngCount > 0) {
      const msg = `✅ ${overwrittenJpgCount} JPG(s) sobrescrito(s) e ${newPngCount} novo(s) PNG(s) salvo(s) na Galeria!`;
      if (window.AndroidBridge && typeof window.AndroidBridge.showToast === 'function') {
        window.AndroidBridge.showToast(msg);
      }
      btnSaveAll.innerHTML = `<span>✅</span> Fotos Salvas na Galeria!`;
    } else if (overwrittenJpgCount > 0) {
      const msg = `✅ ${overwrittenJpgCount} JPG(s) original(is) sobrescrito(s) na Galeria!`;
      if (window.AndroidBridge && typeof window.AndroidBridge.showToast === 'function') {
        window.AndroidBridge.showToast(msg);
      }
      btnSaveAll.innerHTML = `<span>✅</span> ${overwrittenJpgCount} JPG(s) Sobrescrito(s)!`;
    } else if (newPngCount > 0) {
      const msg = `✅ ${newPngCount} novo(s) PNG(s) limpo(s) criado(s) no mesmo local da Galeria!`;
      if (window.AndroidBridge && typeof window.AndroidBridge.showToast === 'function') {
        window.AndroidBridge.showToast(msg);
      }
      btnSaveAll.innerHTML = `<span>✅</span> ${newPngCount} Novo(s) PNG(s) Salvo(s)!`;
    } else if (savedGalleryCount > 0) {
      const msg = `✅ ${savedGalleryCount} foto(s) limpa(s) salva(s) na Galeria!`;
      if (window.AndroidBridge && typeof window.AndroidBridge.showToast === 'function') {
        window.AndroidBridge.showToast(msg);
      }
      btnSaveAll.innerHTML = `<span>✅</span> ${savedGalleryCount} Foto(s) Salva(s)!`;
    } else {
      btnSaveAll.innerHTML = `<span>✅</span> ${processedResults.length} Foto(s) Salva(s) com Sucesso!`;
    }

    setTimeout(() => {
      btnSaveAll.innerHTML = `<span>💾</span> Salvar Todas as Fotos`;
      btnSaveAll.disabled = false;
    }, 3500);
  });
}

// Batch Share All Photos (WhatsApp, Instagram, Files)
if (btnShareAll) {
  btnShareAll.addEventListener('click', async () => {
    if (!processedResults.length) return;

    btnShareAll.disabled = true;
    btnShareAll.innerHTML = `<span>⏳</span> Preparando Envio...`;

    try {
      const filesToShare = processedResults.map(item => {
        const cleanName = getCleanFileName(item.fileName);
        return new File([item.cleanBlob], cleanName, { type: item.cleanBlob.type || 'image/jpeg' });
      });

      if (navigator.canShare && navigator.canShare({ files: filesToShare })) {
        await navigator.share({
          files: filesToShare,
          title: 'Fotos Limpas',
          text: `${filesToShare.length} fotos limpas (sem metadados nem C2PA)`
        });
      } else {
        alert("Seu navegador não suporta envio simultâneo de múltiplos arquivos. Vamos salvá-las na sua galeria!");
        if (btnSaveAll) btnSaveAll.click();
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.warn("Erro ao compartilhar lote:", err);
      }
    } finally {
      btnShareAll.innerHTML = `<span>📤</span> Enviar / Compartilhar Todas`;
      btnShareAll.disabled = false;
    }
  });
}

// Download Handlers
window.downloadSingle = async function(index) {
  const item = processedResults[index];
  if (!item) return;

  const res = await saveOrOverwriteItem(item, index);
  if (window.AndroidBridge && typeof window.AndroidBridge.showToast === 'function') {
    if (res.mode === 'overwritten') {
      window.AndroidBridge.showToast("✅ JPG original sobrescrito na Galeria!");
    } else if (res.isPng) {
      window.AndroidBridge.showToast("✅ Novo PNG limpo salvo no mesmo local da Galeria!");
    } else if (res.mode === 'saved_gallery') {
      window.AndroidBridge.showToast("✅ Foto salva na Galeria!");
    }
  }
};

// Native Mobile Share Handler (WhatsApp, Instagram, Files)
window.shareSingle = async function(index) {
  const item = processedResults[index];
  if (!item) return;

  const cleanName = getCleanFileName(item.fileName);
  try {
    const file = new File([item.cleanBlob], cleanName, { type: item.cleanBlob.type || 'image/jpeg' });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({
        files: [file],
        title: cleanName,
        text: 'Foto limpa (sem metadados nem C2PA)'
      });
      return;
    }
  } catch (err) {
    if (err.name === 'AbortError') return;
  }
  window.downloadSingle(index);
};

if (btnDownloadAll) {
  btnDownloadAll.addEventListener('click', async () => {
    if (!processedResults.length) return;

    if (typeof JSZip === 'undefined') {
      alert("Compactador ZIP carregando, aguarde...");
      return;
    }

    btnDownloadAll.textContent = 'Compactando ZIP...';
    btnDownloadAll.disabled = true;

    const zip = new JSZip();

    processedResults.forEach((item) => {
      const cleanName = getCleanFileName(item.fileName);
      zip.file(cleanName, item.cleanBlob);
    });

    const zipBlob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(zipBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fotos_limpas_zerometa.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 3000);

    btnDownloadAll.innerHTML = '<span>📦</span> Baixar Todas (ZIP)';
    btnDownloadAll.disabled = false;
  });
}

// Modal Details Inspector
window.inspectDetails = async function(index) {
  const file = selectedFiles[index];
  if (!file) return;

  const info = await inspectMetadata(file);
  modalTitle.textContent = file.name;

  let html = `<p><strong>Formato:</strong> ${info.fileType}</p>`;
  html += `<p><strong>Tamanho Original:</strong> ${formatBytes(file.size)}</p><hr style="border:0; border-top:1px solid rgba(255,255,255,0.1); margin:10px 0;">`;

  if (info.hasC2PA) {
    html += `<div style="background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.3); border-radius:6px; padding:10px; margin-bottom:10px;">
      <strong style="color:var(--accent-cyan);">🤖 Manifesto C2PA Encontrado!</strong>
      <p style="margin-top:4px;">Emissor / Agente: <strong>${info.c2paDetails || 'OpenAI / C2PA'}</strong></p>
      <p style="font-size:0.75rem; margin-top:4px; color:#cbd5e1;">Esta imagem possui carimbo de proveniência de Inteligência Artificial. A limpeza remove totalmente este bloco JUMBF/caPX.</p>
    </div>`;
  } else {
    html += `<p>✅ Nenhum manifesto C2PA detectado.</p>`;
  }

  if (info.prompts.length) {
    html += `<div style="margin-top:10px;"><strong>🧠 Prompts / Textos Ocultos:</strong>`;
    info.prompts.forEach(p => {
      html += `<pre style="background:#1e293b; padding:8px; border-radius:4px; overflow-x:auto; margin-top:4px; font-size:0.75rem;">${p}</pre>`;
    });
    html += `</div>`;
  }

  if (info.hasGps) {
    html += `<p style="margin-top:10px; color:#f59e0b;"><strong>📍 Coordenadas de GPS:</strong> Presentes no cabeçalho EXIF.</p>`;
  }

  modalBody.innerHTML = html;
  detailModal.style.display = 'flex';
};

if (btnCloseModal) {
  btnCloseModal.addEventListener('click', () => {
    detailModal.style.display = 'none';
  });
}

if (detailModal) {
  detailModal.addEventListener('click', (e) => {
    if (e.target === detailModal) detailModal.style.display = 'none';
  });
}
