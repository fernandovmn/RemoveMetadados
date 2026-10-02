"""
Inspector module to detect metadata, especially AI (C2PA / Content Credentials),
prompts, EXIF (GPS, Camera, Dates), IPTC, and XMP in images.
"""
import os
import json
from typing import Dict, Any, List, Optional
from PIL import Image, ExifTags

try:
    import c2pa
    HAS_C2PA = True
except ImportError:
    HAS_C2PA = False


def _convert_gps_coords(coord_tuple, ref):
    """Convert EXIF GPS coordinates (degrees, minutes, seconds) to decimal."""
    try:
        deg = float(coord_tuple[0])
        minute = float(coord_tuple[1])
        sec = float(coord_tuple[2])
        dec = deg + (minute / 60.0) + (sec / 3600.0)
        if ref in ['S', 'W']:
            dec = -dec
        return round(dec, 6)
    except Exception:
        return None


def inspect_image_metadata(file_path: str) -> Dict[str, Any]:
    """
    Inspects an image file and extracts metadata summary:
    - C2PA manifest (OpenAI, ChatGPT, Adobe, etc.)
    - AI Prompts (Stable Diffusion, Midjourney, ComfyUI, ChatGPT)
    - EXIF (Camera, Dates, Lens)
    - GPS Coordinates
    - IPTC / XMP tags
    """
    result = {
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        "has_c2pa": False,
        "c2pa_data": None,
        "c2pa_summary": None,
        "has_exif": False,
        "exif_summary": {},
        "has_gps": False,
        "gps_coords": None,
        "has_ai_prompt": False,
        "ai_prompts": {},
        "has_xmp": False,
        "has_iptc": False,
        "badges": [],
        "raw_text_chunks": {},
    }

    # 1. C2PA Inspection (Content Credentials)
    if HAS_C2PA:
        try:
            reader = c2pa.Reader.try_create(file_path)
            if reader:
                raw_json = reader.json()
                parsed = json.loads(raw_json)
                result["has_c2pa"] = True
                result["c2pa_data"] = parsed

                active_man = parsed.get("active_manifest")
                manifests = parsed.get("manifests", {})
                active_obj = manifests.get(active_man, {}) if active_man else {}

                generators = []
                for gen in active_obj.get("claim_generator_info", []):
                    name = gen.get("name")
                    if name:
                        generators.append(name)

                # Check assertions for software agent
                software_agents = []
                for assertion in active_obj.get("assertions", []):
                    data = assertion.get("data", {})
                    if isinstance(data, dict):
                        for action in data.get("actions", []):
                            agent = action.get("softwareAgent", {})
                            agent_name = agent.get("name")
                            if agent_name and agent_name not in software_agents:
                                software_agents.append(agent_name)

                sig_info = active_obj.get("signature_info", {})
                issuer = sig_info.get("issuer") or sig_info.get("common_name")

                summary_str = ""
                if software_agents:
                    summary_str = f"IA: {', '.join(software_agents)}"
                elif generators:
                    summary_str = f"IA: {', '.join(generators)}"
                elif issuer:
                    summary_str = f"C2PA: {issuer}"
                else:
                    summary_str = "C2PA Manifesto Presente"

                result["c2pa_summary"] = {
                    "generators": generators,
                    "software_agents": software_agents,
                    "issuer": issuer,
                    "title": active_obj.get("title", ""),
                    "validation_state": parsed.get("validation_state", ""),
                    "display": summary_str
                }
                result["badges"].append(f"C2PA ({summary_str})")
        except Exception:
            pass

    # 2. Pillow Inspection (EXIF, GPS, PNG text chunks, Prompts)
    try:
        with Image.open(file_path) as img:
            result["image_format"] = img.format
            result["dimensions"] = f"{img.width}x{img.height}"
            result["mode"] = img.mode

            # PNG text metadata
            if hasattr(img, "text") and img.text:
                for k, v in img.text.items():
                    result["raw_text_chunks"][k] = v
                    k_lower = k.lower()
                    if k_lower in ("prompt", "parameters", "workflow", "prompt_text", "sd-metadata"):
                        result["has_ai_prompt"] = True
                        result["ai_prompts"][k] = v
                    elif "prompt" in k_lower or "seed" in k_lower:
                        result["has_ai_prompt"] = True
                        result["ai_prompts"][k] = v

            # Info dictionary metadata
            if hasattr(img, "info") and img.info:
                if "XML:com.adobe.xmp" in img.info or "xmp" in img.info:
                    result["has_xmp"] = True
                if "photoshop" in img.info or "icc_profile" in img.info:
                    result["has_iptc"] = True

                # Check comment
                if "comment" in img.info:
                    comm = str(img.info["comment"])
                    result["raw_text_chunks"]["Comment"] = comm
                    if any(w in comm.lower() for w in ["prompt", "ai", "dall-e", "midjourney", "steps:"]):
                        result["has_ai_prompt"] = True
                        result["ai_prompts"]["Comment"] = comm

            # EXIF inspection
            exif_obj = img.getexif()
            if exif_obj and len(exif_obj) > 0:
                result["has_exif"] = True
                exif_data = {}
                for tag_id, val in exif_obj.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    exif_data[tag_name] = str(val)

                # Camera & Software
                make = exif_data.get("Make")
                model = exif_data.get("Model")
                if make or model:
                    cam = f"{make or ''} {model or ''}".strip()
                    result["exif_summary"]["camera"] = cam

                soft = exif_data.get("Software")
                if soft:
                    result["exif_summary"]["software"] = soft
                    if any(w in soft.lower() for w in ["chatgpt", "openai", "midjourney", "stable diffusion"]):
                        result["has_ai_prompt"] = True
                        result["ai_prompts"]["Software"] = soft

                dt = exif_data.get("DateTime") or exif_data.get("DateTimeOriginal")
                if dt:
                    result["exif_summary"]["date"] = dt

                # GPS inspection (Tag 34853 = 0x8825)
                gps_info_raw = exif_obj.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(exif_obj, "get_ifd") else None
                if not gps_info_raw and hasattr(exif_obj, "get"):
                    gps_info_raw = exif_obj.get(34853)

                if gps_info_raw and isinstance(gps_info_raw, dict):
                    lat = gps_info_raw.get(2)
                    lat_ref = gps_info_raw.get(1)
                    lon = gps_info_raw.get(4)
                    lon_ref = gps_info_raw.get(3)
                    if lat and lon and lat_ref and lon_ref:
                        dec_lat = _convert_gps_coords(lat, lat_ref)
                        dec_lon = _convert_gps_coords(lon, lon_ref)
                        if dec_lat is not None and dec_lon is not None:
                            result["has_gps"] = True
                            result["gps_coords"] = {"lat": dec_lat, "lon": dec_lon}
                            result["badges"].append(f"GPS ({dec_lat}, {dec_lon})")

                if result["exif_summary"].get("camera"):
                    result["badges"].append(f"Câmera: {result['exif_summary']['camera']}")

    except Exception:
        pass

    if result["has_ai_prompt"] and not any("C2PA" in b for b in result["badges"]):
        result["badges"].append("Prompt IA Encontrado")

    if result["has_xmp"] and "XMP" not in [b[:3] for b in result["badges"]]:
        result["badges"].append("Metadados XMP")

    if not result["badges"]:
        if result["has_exif"] or result["raw_text_chunks"]:
            result["badges"].append("Metadados Básicos")
        else:
            result["badges"].append("Sem Metadados Detectados")

    return result
