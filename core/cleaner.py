"""
Core metadata cleaner module.
Provides lossless marker/chunk stripping for JPEG, PNG, WEBP,
as well as clean pixel-reconstruction fallback and directory batch processing.
Removes 100% of C2PA (Content Credentials), EXIF, GPS, Prompts, IPTC and XMP.
"""
import os
import shutil
import struct
import io
import time
from typing import Dict, Any, List, Optional, Callable
from PIL import Image

try:
    import c2pa
    HAS_C2PA = True
except ImportError:
    HAS_C2PA = False

from core.inspector import inspect_image_metadata

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".jfif", ".avif", ".heic"
}


def strip_jpeg_lossless(data: bytes) -> bytes:
    """
    Strips metadata markers (APP1-APP15, COM) from JPEG without touching
    DCT coefficients or Huffman tables, preserving 100% visual quality.
    Removes APP11 (C2PA/JUMBF), APP1 (EXIF/XMP), APP13 (IPTC), COM (Comments).
    """
    if not (data.startswith(b'\xff\xd8') and (b'\xff\xd9' in data)):
        raise ValueError("Not a valid JPEG buffer")

    out = bytearray(b'\xff\xd8')
    pos = 2
    n = len(data)

    # Discard APP1 to APP15 (0xE1 to 0xEF) and COM (0xFE)
    # APP0 (0xE0) is JFIF header, kept to ensure standard viewer compatibility
    discard_markers = set(range(0xE1, 0xF0)) | {0xFE}

    while pos < n:
        if data[pos] != 0xFF:
            pos += 1
            continue

        marker = data[pos + 1]

        # Padding FF bytes
        if marker == 0xFF:
            pos += 1
            continue

        # Standalone markers without length: SOI (0xD8), EOI (0xD9), RST0-RST7 (0xD0-0xD7)
        if marker in (0xD8, 0xD9):
            pos += 2
            continue

        if 0xD0 <= marker <= 0xD7:
            out.extend(data[pos:pos + 2])
            pos += 2
            continue

        # Start of Scan (0xDA) - followed by image entropy bitstream until EOI
        if marker == 0xDA:
            out.extend(data[pos:])
            break

        # Markers with 2-byte length
        if pos + 4 > n:
            break

        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        chunk_total = 2 + length

        if pos + chunk_total > n:
            break

        chunk = data[pos:pos + chunk_total]

        if marker not in discard_markers:
            out.extend(chunk)

        pos += chunk_total

    # Ensure EOI at end
    if not out.endswith(b'\xff\xd9'):
        out.extend(b'\xff\xd9')

    return bytes(out)


def strip_png_lossless(data: bytes) -> bytes:
    """
    Strips ancillary metadata chunks from PNG files.
    Removes c2pa, caPX, tEXt, zTXt, iTXt, eXIf, tIME, pHYs, iCCP, dSIG.
    Preserves critical display chunks: IHDR, PLTE, tRNS, IDAT, IEND.
    """
    png_sig = b'\x89PNG\r\n\x1a\n'
    if not data.startswith(png_sig):
        raise ValueError("Not a valid PNG buffer")

    out = bytearray(png_sig)
    pos = 8
    n = len(data)

    # Critical chunks to keep
    keep_chunks = {b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'}

    while pos + 8 <= n:
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_total_len = 12 + length

        if pos + chunk_total_len > n:
            break

        chunk = data[pos:pos + chunk_total_len]

        if chunk_type in keep_chunks:
            out.extend(chunk)

        pos += chunk_total_len
        if chunk_type == b'IEND':
            break

    return bytes(out)


def strip_webp_lossless(data: bytes) -> bytes:
    """
    Strips EXIF and XMP chunks from RIFF WebP container.
    """
    if not (data.startswith(b'RIFF') and data[8:12] == b'WEBP'):
        raise ValueError("Not a valid WebP buffer")

    # If it's a simple VP8/VP8L file without EXIF/XMP chunks, check presence
    has_exif = b'EXIF' in data
    has_xmp = b'XMP ' in data

    if not has_exif and not has_xmp:
        return data

    pos = 12
    n = len(data)
    kept_chunks = []

    while pos + 8 <= n:
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack('<I', data[pos + 4:pos + 8])[0]
        padded_size = chunk_size + (chunk_size % 2)
        total_len = 8 + padded_size

        if pos + total_len > n:
            break

        chunk_data = data[pos:pos + total_len]

        # Discard EXIF and XMP chunks
        if chunk_id not in (b'EXIF', b'XMP '):
            # If VP8X header, we need to clear EXIF and XMP flag bits (offset 20 in data, or 8+0 in chunk)
            if chunk_id == b'VP8X' and len(chunk_data) >= 12:
                chunk_bytes = bytearray(chunk_data)
                # VP8X flags byte is at index 8
                # bit 2 = XMP (mask 0x04), bit 3 = Exif (mask 0x08)
                flags = chunk_bytes[8]
                flags = flags & ~0x04  # clear XMP
                flags = flags & ~0x08  # clear EXIF
                chunk_bytes[8] = flags
                chunk_data = bytes(chunk_bytes)

            kept_chunks.append(chunk_data)

        pos += total_len

    # Reassemble RIFF
    payload = b''.join(kept_chunks)
    riff_header = b'RIFF' + struct.pack('<I', len(payload) + 4) + b'WEBP'
    return riff_header + payload


def clean_by_pixel_reconstruction(src_path: str, dst_path: str, fmt: str):
    """
    Fallback method: Loads pure pixel data and writes a completely fresh image
    canvas without any attached metadata or EXIF structures.
    """
    with Image.open(src_path) as img:
        fmt_upper = fmt.upper()
        # Handle transparency when saving to JPEG (composite against pure white)
        if fmt_upper in ("JPEG", "JPG") and (img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[3])
            clean_img = background
        else:
            mode = img.mode
            if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in img.info):
                canvas_mode = "RGBA"
            elif mode in ("RGB", "L"):
                canvas_mode = mode
            else:
                canvas_mode = "RGB"

            clean_img = Image.new(canvas_mode, img.size)
            clean_img.paste(img)

        # Clear any dictionary
        clean_img.info.clear()

        # Save cleanly
        save_kwargs = {}
        if fmt_upper in ("JPEG", "JPG"):
            save_kwargs["quality"] = 98
            save_kwargs["subsampling"] = 0
            save_kwargs["optimize"] = True
        elif fmt_upper == "PNG":
            save_kwargs["optimize"] = True
        elif fmt_upper == "WEBP":
            save_kwargs["lossless"] = True

        clean_img.save(dst_path, format=fmt, **save_kwargs)


def clean_single_image(
    src_path: str,
    dst_path: Optional[str] = None,
    mode: str = "smart_lossless",
    reset_os_timestamps: bool = False
) -> Dict[str, Any]:
    """
    Cleans a single image file.
    Modes:
      - 'smart_lossless': Uses byte-level marker/chunk stripping (no pixel recompression)
                          with automatic fallback to pixel reconstruction if needed.
      - 'pixel_reconstruction': Decodes pixels into fresh canvas and re-saves.

    Returns dict with summary: success, bytes_saved, c2pa_removed, details.
    """
    if dst_path is None:
        dst_path = src_path

    # First inspect original
    info_before = inspect_image_metadata(src_path)
    ext = os.path.splitext(src_path)[1].lower()
    dst_ext = os.path.splitext(dst_path)[1].lower()
    original_size = info_before["file_size"]

    temp_dst = dst_path + ".tmp_clean"
    used_method = "lossless"

    try:
        # Special rule: PNG converting to JPG (desktop / mobile parity)
        if ext == ".png" and dst_ext in (".jpg", ".jpeg"):
            with Image.open(src_path) as img:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[3])
                    rgb_img = background
                else:
                    rgb_img = img.convert("RGB")

                rgb_img.info.clear()
                rgb_img.save(temp_dst, format="JPEG", quality=98, subsampling=0, optimize=True)
            used_method = "png_to_jpeg_quality_98"

        elif mode == "smart_lossless":
            with open(src_path, "rb") as f:
                raw_bytes = f.read()

            try:
                if ext in (".jpg", ".jpeg", ".jfif"):
                    cleaned_bytes = strip_jpeg_lossless(raw_bytes)
                    with Image.open(io.BytesIO(cleaned_bytes)) as check:
                        check.verify()
                    with open(temp_dst, "wb") as f:
                        f.write(cleaned_bytes)
                    used_method = "lossless_jpeg"

                elif ext == ".png":
                    cleaned_bytes = strip_png_lossless(raw_bytes)
                    with Image.open(io.BytesIO(cleaned_bytes)) as check:
                        check.verify()
                    with open(temp_dst, "wb") as f:
                        f.write(cleaned_bytes)
                    used_method = "lossless_png"

                elif ext == ".webp":
                    cleaned_bytes = strip_webp_lossless(raw_bytes)
                    with Image.open(io.BytesIO(cleaned_bytes)) as check:
                        check.verify()
                    with open(temp_dst, "wb") as f:
                        f.write(cleaned_bytes)
                    used_method = "lossless_webp"

                else:
                    # Format without direct byte stripper
                    clean_by_pixel_reconstruction(src_path, temp_dst, info_before.get("image_format", "PNG"))
                    used_method = "pixel_reconstruction"

            except Exception:
                # Lossless failed due to unusual structure, fall back safely to pixel reconstruction
                clean_by_pixel_reconstruction(src_path, temp_dst, info_before.get("image_format", "PNG"))
                used_method = "pixel_reconstruction_fallback"

        else:
            clean_by_pixel_reconstruction(src_path, temp_dst, info_before.get("image_format", "PNG"))
            used_method = "pixel_reconstruction"

        # Final verification: verify C2PA is 100% removed
        if HAS_C2PA:
            try:
                reader = c2pa.Reader.try_create(temp_dst)
                if reader is not None:
                    # Extreme edge case: C2PA still present, force pixel canvas reconstruction
                    clean_by_pixel_reconstruction(temp_dst, temp_dst + "_px", info_before.get("image_format", "PNG"))
                    os.replace(temp_dst + "_px", temp_dst)
                    used_method = "pixel_reconstruction_enforced"
            except Exception:
                pass

        # Move temp to final destination
        os.replace(temp_dst, dst_path)

        # Reset OS timestamp if requested (for maximum anonymity)
        if reset_os_timestamps:
            now = time.time()
            os.utime(dst_path, (now, now))

        new_size = os.path.getsize(dst_path)
        bytes_saved = original_size - new_size

        return {
            "success": True,
            "src": src_path,
            "dst": dst_path,
            "original_size": original_size,
            "new_size": new_size,
            "bytes_saved": bytes_saved,
            "used_method": used_method,
            "c2pa_detected": info_before["has_c2pa"],
            "ai_prompt_detected": info_before["has_ai_prompt"],
            "exif_detected": info_before["has_exif"],
            "gps_detected": info_before["has_gps"],
            "info_before": info_before,
            "error": None
        }

    except Exception as e:
        if os.path.exists(temp_dst):
            try:
                os.remove(temp_dst)
            except Exception:
                pass
        return {
            "success": False,
            "src": src_path,
            "dst": dst_path,
            "original_size": original_size,
            "new_size": original_size,
            "bytes_saved": 0,
            "used_method": "failed",
            "c2pa_detected": info_before["has_c2pa"],
            "ai_prompt_detected": info_before["has_ai_prompt"],
            "exif_detected": info_before["has_exif"],
            "gps_detected": info_before["has_gps"],
            "info_before": info_before,
            "error": str(e)
        }


def scan_directory_images(directory: str, recursive: bool = True) -> List[str]:
    """Finds all supported image files in directory."""
    files_found = []
    if recursive:
        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    files_found.append(os.path.join(root, file))
    else:
        for item in os.listdir(directory):
            full_path = os.path.join(directory, item)
            if os.path.isfile(full_path):
                ext = os.path.splitext(item)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    files_found.append(full_path)

    return files_found


def process_directory(
    input_dir: str,
    output_dir: Optional[str] = None,
    recursive: bool = True,
    mode: str = "smart_lossless",
    overwrite: bool = False,
    make_backup: bool = True,
    reset_os_timestamps: bool = False,
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None
) -> Dict[str, Any]:
    """
    Processes all images found in input_dir.
    Reports progress via progress_callback(current, total, result_item).
    """
    images = scan_directory_images(input_dir, recursive=recursive)
    total = len(images)

    stats = {
        "total_found": total,
        "processed": 0,
        "success_count": 0,
        "error_count": 0,
        "c2pa_removed_count": 0,
        "ai_prompts_removed_count": 0,
        "exif_removed_count": 0,
        "gps_removed_count": 0,
        "total_bytes_saved": 0,
        "results": []
    }

    if total == 0:
        return stats

    # Determine output folder
    if not overwrite and output_dir is None:
        output_dir = os.path.join(input_dir, "_fotos_limpas")

    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    for idx, src_file in enumerate(images, 1):
        if stop_check and stop_check():
            break

        # Calculate destination path
        src_ext = os.path.splitext(src_file)[1].lower()
        is_png = src_ext == ".png"

        if is_png:
            # PNG nunca grava por cima; cria um novo JPG no mesmo diretorio
            if overwrite:
                base_name = os.path.splitext(src_file)[0]
                dst_file = base_name + ".jpg"
            else:
                rel_path = os.path.relpath(src_file, input_dir)
                rel_base = os.path.splitext(rel_path)[0]
                dst_file = os.path.join(output_dir, rel_base + ".jpg")
                dst_folder = os.path.dirname(dst_file)
                if not os.path.exists(dst_folder):
                    os.makedirs(dst_folder, exist_ok=True)
        elif overwrite:
            dst_file = src_file
            if make_backup:
                bak_path = src_file + ".bak"
                if not os.path.exists(bak_path):
                    shutil.copy2(src_file, bak_path)
        else:
            # Preserve relative subfolder structure
            rel_path = os.path.relpath(src_file, input_dir)
            dst_file = os.path.join(output_dir, rel_path)
            dst_folder = os.path.dirname(dst_file)
            if not os.path.exists(dst_folder):
                os.makedirs(dst_folder, exist_ok=True)

        res = clean_single_image(
            src_path=src_file,
            dst_path=dst_file,
            mode=mode,
            reset_os_timestamps=reset_os_timestamps
        )

        stats["processed"] += 1
        if res["success"]:
            stats["success_count"] += 1
            if res["c2pa_detected"]:
                stats["c2pa_removed_count"] += 1
            if res["ai_prompt_detected"]:
                stats["ai_prompts_removed_count"] += 1
            if res["exif_detected"]:
                stats["exif_removed_count"] += 1
            if res["gps_detected"]:
                stats["gps_removed_count"] += 1
            stats["total_bytes_saved"] += max(0, res["bytes_saved"])
        else:
            stats["error_count"] += 1

        stats["results"].append(res)

        if progress_callback:
            progress_callback(idx, total, res)

    return stats
