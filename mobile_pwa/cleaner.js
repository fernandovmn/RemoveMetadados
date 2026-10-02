/**
 * ZeroMeta Client-Side Binary Metadata Cleaner
 * Strips C2PA (OpenAI / ChatGPT / Midjourney / Adobe), EXIF, GPS, Prompts and IPTC
 * completely inside the browser without sending photos to any server.
 */

// Helper: Convert ArrayBuffer to string safely
function bufferToBinaryString(buffer, start = 0, length = null) {
  const bytes = new Uint8Array(buffer, start, length ?? (buffer.byteLength - start));
  let str = '';
  const len = Math.min(bytes.length, 100000); // cap scan for speed
  for (let i = 0; i < len; i++) {
    str += String.fromCharCode(bytes[i]);
  }
  return str;
}

// 1. INSPECT METADATA IN BROWSER
export async function inspectMetadata(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const ext = file.name.split('.').pop().toLowerCase();

  const result = {
    fileName: file.name,
    fileSize: file.size,
    fileType: file.type || ext,
    hasC2PA: false,
    c2paDetails: null,
    hasExif: false,
    hasGps: false,
    hasAiPrompt: false,
    prompts: [],
    badges: [],
  };

  const textSample = bufferToBinaryString(buffer, 0, Math.min(buffer.byteLength, 200000));

  // A. JPEG Inspection
  if (bytes[0] === 0xFF && bytes[1] === 0xD8) {
    let pos = 2;
    const len = bytes.length;

    while (pos < len) {
      if (bytes[pos] !== 0xFF) { pos++; continue; }
      const marker = bytes[pos + 1];

      if (marker === 0xDA || marker === 0xD9) break; // SOS or EOI
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
        } else {
          result.badges.push("📷 Dados EXIF");
        }
      }

      // COM = 0xFE (Comments / Prompts)
      if (marker === 0xFE) {
        let comment = bufferToBinaryString(buffer, pos + 4, markerLength - 2);
        if (/prompt|dall-e|ai|midjourney|steps:/i.test(comment)) {
          result.hasAiPrompt = true;
          result.prompts.push(comment.trim());
          result.badges.push("🧠 Prompt IA");
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
          if (!result.badges.includes("🧠 Prompt IA")) {
            result.badges.push("🧠 Prompt IA");
          }
        }
      }

      if (chunkType === 'eXIf') {
        result.hasExif = true;
        result.badges.push("📷 EXIF");
      }

      pos += 12 + chunkLength;
      if (chunkType === 'IEND') break;
    }
  }

  // C. WebP Inspection
  else if (textSample.startsWith("RIFF") && textSample.includes("WEBP")) {
    if (textSample.includes("EXIF")) {
      result.hasExif = true;
      result.badges.push("📷 EXIF");
    }
    if (textSample.includes("XMP ")) {
      result.badges.push("Metadados XMP");
    }
    if (textSample.includes("c2pa") || textSample.includes("OpenAI")) {
      result.hasC2PA = true;
      result.badges.push("🤖 C2PA IA");
    }
  }

  // Fallback check in binary text
  if (!result.hasC2PA && /urn:c2pa:|OpenAI Media Service|trainedAlgorithmicMedia/i.test(textSample)) {
    result.hasC2PA = true;
    result.c2paDetails = "OpenAI / C2PA Provenance";
    result.badges.push("🤖 C2PA (OpenAI)");
  }

  if (result.badges.length === 0) {
    result.badges.push("Nenhum metadado detectado");
  }

  return result;
}

// 2. LOSSLESS JPEG STRIPPER
export function stripJpegLossless(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(arrayBuffer);
  const len = bytes.length;

  if (bytes[0] !== 0xFF || bytes[1] !== 0xD8) {
    throw new Error("Não é um JPEG válido");
  }

  // Discard markers APP1..APP15 (0xE1..0xEF) and COM (0xFE)
  // Keep APP0 (0xE0 - JFIF), SOF, DHT, DQT, DRI, SOS
  const outputChunks = [bytes.subarray(0, 2)]; // Start with FF D8
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
      // Remainder of file is image data
      outputChunks.push(new Uint8Array([0xFF, 0xDA]));
      outputChunks.push(bytes.subarray(pos));
      break;
    }

    if (pos + 2 > len) break;
    const length = view.getUint16(pos);
    const chunkTotal = length;

    // Filter out APP1-APP15 (0xE1..0xEF) and COM (0xFE)
    const isDiscard = (marker >= 0xE1 && marker <= 0xEF) || (marker === 0xFE);

    if (!isDiscard) {
      outputChunks.push(new Uint8Array([0xFF, marker]));
      outputChunks.push(bytes.subarray(pos, pos + chunkTotal));
    }

    pos += chunkTotal;
  }

  // Combine
  return new Blob(outputChunks, { type: 'image/jpeg' });
}

// 3. LOSSLESS PNG STRIPPER
export function stripPngLossless(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(arrayBuffer);
  const len = bytes.length;

  if (bytes[0] !== 0x89 || bytes[1] !== 0x50 || bytes[2] !== 0x4E || bytes[3] !== 0x47) {
    throw new Error("Não é um PNG válido");
  }

  const keepChunks = new Set(['IHDR', 'PLTE', 'tRNS', 'IDAT', 'IEND']);
  const outputParts = [bytes.subarray(0, 8)]; // PNG Signature
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

// 4. CANVAS PIXEL RE-RENDER (FALLBACK / ABSOLUTE CLEANSE)
export async function cleanWithCanvas(file, format = 'image/jpeg', quality = 0.95) {
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
      reject(new Error("Não foi possível carregar a imagem para renderização"));
    };

    img.src = url;
  });
}

// 5. MASTER CLEANER PIPELINE
export async function cleanImage(file, forceCanvas = false) {
  const originalSize = file.size;
  const ext = file.name.split('.').pop().toLowerCase();
  const infoBefore = await inspectMetadata(file);

  let cleanBlob = null;
  let method = 'lossless';

  if (!forceCanvas) {
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
      console.warn("Lossless falhou, usando canvas fallback:", err);
    }
  }

  // Fallback to canvas
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
  };
}
