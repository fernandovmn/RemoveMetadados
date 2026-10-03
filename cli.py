"""
Command-line interface (CLI) for ZeroMeta.
Run automated batch cleaning or audits directly from terminal or scripts.
"""
import os
import sys
import argparse
import json
from typing import Dict, Any

from core.cleaner import (
    process_directory,
    clean_single_image,
    scan_directory_images
)
from core.inspector import inspect_image_metadata


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"


def main():
    parser = argparse.ArgumentParser(
        description="ZeroMeta AI - Removedor de Metadados e Manifestos C2PA (OpenAI, ChatGPT, Midjourney, etc.)"
    )
    parser.add_argument("path", help="Caminho do diretório ou arquivo de imagem a processar")
    parser.add_argument("-o", "--output", help="Diretório de saída para as imagens limpas (padrão: <dir>/_fotos_limpas)")
    parser.add_argument("-r", "--recursive", action="store_true", default=True, help="Varrer subpastas recursivamente (padrão: ativo)")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Não varrer subpastas")
    parser.add_argument("--overwrite", action="store_true", help="Sobrescrever os arquivos originais")
    parser.add_argument("--no-backup", action="store_true", help="Não criar backup .bak ao sobrescrever")
    parser.add_argument("--reset-timestamps", action="store_true", default=True, help="Resetar data/hora dos arquivos no Windows para agora")
    parser.add_argument("--audit", action="store_true", help="Apenas auditar e listar metadados sem modificar nenhum arquivo")
    parser.add_argument("--json", action="store_true", help="Imprimir relatório final em formato JSON")

    args = parser.parse_args()

    target = os.path.abspath(args.path)
    if not os.path.exists(target):
        print(f"[ERRO] Caminho não encontrado: {target}", file=sys.stderr)
        sys.exit(1)

    is_file = os.path.isfile(target)

    # 1. AUDIT MODE
    if args.audit:
        print("=" * 60)
        print(" MODO AUDITORIA - ZEROMETA AI")
        print("=" * 60)

        targets = [target] if is_file else scan_directory_images(target, recursive=args.recursive)
        print(f"Fotos encontradas para auditoria: {len(targets)}\n")

        results = []
        c2pa_found = 0
        exif_found = 0

        for f in targets:
            info = inspect_image_metadata(f)
            results.append(info)
            if info["has_c2pa"]:
                c2pa_found += 1
            if info["has_exif"] or info["has_gps"]:
                exif_found += 1

            badges_str = " | ".join(info["badges"]) if info["badges"] else "Limpo"
            print(f"• {os.path.basename(f)} [{info.get('image_format', 'IMG')}]: {badges_str}")

        print("\n" + "=" * 60)
        print(f"Resumo da Auditoria:")
        print(f"• Total analisado: {len(targets)}")
        print(f"• Com IA / C2PA:   {c2pa_found}")
        print(f"• Com EXIF / GPS:  {exif_found}")
        print("=" * 60)

        if args.json:
            print("\nJSON:")
            print(json.dumps(results, indent=2, default=str))

        sys.exit(0)

    # 2. CLEANING MODE
    print("=" * 60)
    print(" INICIANDO LIMPEZA DE METADADOS - ZEROMETA AI")
    print("=" * 60)

    if is_file:
        src_ext = os.path.splitext(target)[1].lower()
        if src_ext == ".png":
            dst = os.path.splitext(target)[0] + ".jpg" if args.overwrite else (args.output or os.path.splitext(target)[0] + "_limpo.jpg")
        else:
            dst = target if args.overwrite else (args.output or target.replace(".", "_limpo."))
        if args.overwrite and not args.no_backup and src_ext != ".png":
            import shutil
            bak = target + ".bak"
            shutil.copy2(target, bak)
            print(f"[Backup] Criado: {bak}")

        res = clean_single_image(
            src_path=target,
            dst_path=dst,
            mode="smart_lossless",
            reset_os_timestamps=args.reset_timestamps
        )

        if res["success"]:
            print(f"[OK] Limpeza concluída: {dst}")
            print(f"     C2PA/IA removido: {res['c2pa_detected']}")
            print(f"     EXIF removido:    {res['exif_detected']}")
            print(f"     Tamanho: {format_bytes(res['original_size'])} -> {format_bytes(res['new_size'])} (Economia: {format_bytes(res['bytes_saved'])})")
        else:
            print(f"[FALHA] Erro ao limpar {target}: {res['error']}", file=sys.stderr)
            sys.exit(1)

    else:
        def on_progress(cur, total, item):
            fname = os.path.basename(item["src"])
            tag = "C2PA REMOVIDO" if item["c2pa_detected"] else ("LIMPO" if item["success"] else "ERRO")
            print(f"[{cur}/{total}] {tag} - {fname}")

        stats = process_directory(
            input_dir=target,
            output_dir=args.output,
            recursive=args.recursive,
            mode="smart_lossless",
            overwrite=args.overwrite,
            make_backup=not args.no_backup,
            reset_os_timestamps=args.reset_timestamps,
            progress_callback=on_progress
        )

        print("\n" + "=" * 60)
        print(" RELATÓRIO FINAL:")
        print("=" * 60)
        print(f"• Total de fotos processadas:    {stats['processed']}")
        print(f"• Limpas com sucesso:             {stats['success_count']}")
        print(f"• Manifestos C2PA / IA removidos: {stats['c2pa_removed_count']}")
        print(f"• EXIF / Câmera / GPS removidos:  {stats['exif_removed_count']}")
        print(f"• Prompts textuais removidos:     {stats['ai_prompts_removed_count']}")
        print(f"• Espaço total recuperado:        {format_bytes(stats['total_bytes_saved'])}")
        print("=" * 60)

        if args.json:
            print("\nJSON:")
            print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
