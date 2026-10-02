"""
Modern GUI for ZeroMeta - Metadata & C2PA Remover.
Built with CustomTkinter.
"""
import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Any, List, Optional

import customtkinter as ctk

from core.cleaner import (
    process_directory,
    scan_directory_images,
    clean_single_image,
    SUPPORTED_EXTENSIONS
)
from core.inspector import inspect_image_metadata

# Set theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MetadataDetailDialog(ctk.CTkToplevel):
    """Modal window to inspect detailed metadata before and after."""
    def __init__(self, parent, file_info: Dict[str, Any]):
        super().__init__(parent)
        self.title(f"Inspeção de Metadados - {file_info.get('file_name', '')}")
        self.geometry("750x550")
        self.transient(parent)
        self.grab_set()

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")

        title_lbl = ctk.CTkLabel(
            header,
            text=f"📄 {file_info.get('file_name', '')}",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_lbl.pack(anchor="w")

        path_lbl = ctk.CTkLabel(
            header,
            text=file_info.get("file_path", ""),
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        path_lbl.pack(anchor="w")

        # Tabview for sections
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")

        self.tab_c2pa = self.tabview.add("Credenciais C2PA / IA")
        self.tab_prompts = self.tabview.add("Prompts & Textos")
        self.tab_exif = self.tabview.add("EXIF & GPS")
        self.tab_raw = self.tabview.add("JSON Bruto")

        # Tab 1: C2PA
        self._populate_c2pa_tab(file_info)

        # Tab 2: Prompts
        self._populate_prompts_tab(file_info)

        # Tab 3: EXIF
        self._populate_exif_tab(file_info)

        # Tab 4: Raw JSON
        self._populate_raw_tab(file_info)

        # Close button
        btn_close = ctk.CTkButton(self, text="Fechar", width=120, command=self.destroy)
        btn_close.grid(row=2, column=0, pady=(5, 15))

    def _populate_c2pa_tab(self, info: Dict[str, Any]):
        txt = ctk.CTkTextbox(self.tab_c2pa, font=ctk.CTkFont(family="Consolas", size=12))
        txt.pack(fill="both", expand=True, padx=5, pady=5)

        if info.get("has_c2pa"):
            c2pa_sum = info.get("c2pa_summary", {})
            out = []
            out.append("==================================================")
            out.append("  CREDENCIAIS C2PA / CONTENT PROVENANCE ENCONTRADAS")
            out.append("==================================================\n")
            out.append(f"• Emissor / Entidade: {c2pa_sum.get('issuer', 'N/A')}")
            out.append(f"• Agentes de Software (IA): {', '.join(c2pa_sum.get('software_agents', [])) or 'N/A'}")
            out.append(f"• Geradores de Reivindicação: {', '.join(c2pa_sum.get('generators', [])) or 'N/A'}")
            out.append(f"• Título do Manifesto: {c2pa_sum.get('title', 'N/A')}")
            out.append(f"• Estado de Validação: {c2pa_sum.get('validation_state', 'N/A')}\n")
            out.append("Aviso: Esta foto possui assinatura criptográfica da IA.")
            out.append("A limpeza do ZeroMeta remove totalmente este manifesto.\n")
            txt.insert("1.0", "\n".join(out))
        else:
            txt.insert("1.0", "Nenhum manifesto C2PA ou Content Credentials detectado nesta imagem.\n(Ela não possui assinatura C2PA ou já foi limpa).")

        txt.configure(state="disabled")

    def _populate_prompts_tab(self, info: Dict[str, Any]):
        txt = ctk.CTkTextbox(self.tab_prompts, font=ctk.CTkFont(family="Consolas", size=12))
        txt.pack(fill="both", expand=True, padx=5, pady=5)

        prompts = info.get("ai_prompts", {})
        chunks = info.get("raw_text_chunks", {})
        if prompts or chunks:
            out = ["--- TEXTOS E PROMPTS DE IA DETECTADOS ---\n"]
            for k, v in {**prompts, **chunks}.items():
                out.append(f"[{k}]:\n{v}\n")
            txt.insert("1.0", "\n".join(out))
        else:
            txt.insert("1.0", "Nenhum prompt ou metadado textual encontrado.")
        txt.configure(state="disabled")

    def _populate_exif_tab(self, info: Dict[str, Any]):
        txt = ctk.CTkTextbox(self.tab_exif, font=ctk.CTkFont(family="Consolas", size=12))
        txt.pack(fill="both", expand=True, padx=5, pady=5)

        out = []
        if info.get("has_gps"):
            coords = info.get("gps_coords", {})
            out.append(f"📍 LOCALIZAÇÃO GPS:\nLatitude: {coords.get('lat')}\nLongitude: {coords.get('lon')}\n")

        exif = info.get("exif_summary", {})
        if exif:
            out.append("📷 DADOS DA CÂMERA & SISTEMA:")
            for k, v in exif.items():
                out.append(f"• {k.capitalize()}: {v}")
            out.append("")

        if not out:
            out.append("Nenhum dado EXIF ou GPS sensível encontrado.")

        txt.insert("1.0", "\n".join(out))
        txt.configure(state="disabled")

    def _populate_raw_tab(self, info: Dict[str, Any]):
        import json
        txt = ctk.CTkTextbox(self.tab_raw, font=ctk.CTkFont(family="Consolas", size=11))
        txt.pack(fill="both", expand=True, padx=5, pady=5)
        raw_c2pa = info.get("c2pa_data")
        if raw_c2pa:
            txt.insert("1.0", json.dumps(raw_c2pa, indent=2, ensure_ascii=False))
        else:
            txt.insert("1.0", json.dumps(info, indent=2, default=str, ensure_ascii=False))
        txt.configure(state="disabled")


class MobileQrDialog(ctk.CTkToplevel):
    """Modal para escanear e instalar o app ZeroMeta no Android via Wi-Fi."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("📱 ZeroMeta no Celular (Android)")
        self.geometry("520x640")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        # Header
        lbl_head = ctk.CTkLabel(
            self,
            text="📱 Instalar ZeroMeta no Celular",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        lbl_head.pack(pady=(20, 4))

        lbl_sub = ctk.CTkLabel(
            self,
            text="Conecte seu celular ao mesmo Wi-Fi deste PC e aponte a câmera:",
            font=ctk.CTkFont(size=12),
            text_color="gray75"
        )
        lbl_sub.pack(pady=(0, 15))

        # Start server & generate QR
        from mobile_server import ensure_background_server, get_secure_https_url
        local_url = ensure_background_server() or "http://localhost:8080"
        https_url = get_secure_https_url()
        server_url = https_url or local_url

        try:
            import qrcode
            qr_pil = qrcode.make(server_url)
            qr_ctk = ctk.CTkImage(light_image=qr_pil, dark_image=qr_pil, size=(240, 240))
            lbl_qr = ctk.CTkLabel(self, text="", image=qr_ctk)
            lbl_qr.pack(pady=5)
        except Exception:
            pass

        # Link Box
        link_box = ctk.CTkFrame(self, fg_color=("#1e293b", "#0f172a"), corner_radius=8)
        link_box.pack(padx=25, pady=12, fill="x")

        lbl_link_title = ctk.CTkLabel(
            link_box,
            text="🔒 Link Seguro HTTPS (sem avisos no celular):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981" if https_url else "gray60"
        )
        lbl_link_title.pack(pady=(8, 2))

        lbl_url = ctk.CTkLabel(
            link_box,
            text=server_url,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        )
        lbl_url.pack(pady=(0, 8))

        # Instructions
        inst_frame = ctk.CTkFrame(self, fg_color="transparent")
        inst_frame.pack(padx=30, pady=5, fill="x")

        instructions = (
            "1. Abra o link no Chrome do seu Android.\n"
            "2. Toque no menu de 3 pontinhos e selecione:\n"
            "   'Instalar aplicativo' ou 'Adicionar à tela inicial'.\n"
            "3. O app ficará na tela de início e funcionará 100% OFFLINE!"
        )
        lbl_inst = ctk.CTkLabel(
            inst_frame,
            text=instructions,
            font=ctk.CTkFont(size=12),
            justify="left",
            text_color="gray80"
        )
        lbl_inst.pack(anchor="w")

        btn_close = ctk.CTkButton(self, text="Fechar", width=120, command=self.destroy)
        btn_close.pack(pady=(15, 20))


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ZeroMeta AI - Removedor de Metadados & C2PA")
        self.geometry("1050x760")
        self.minsize(850, 620)

        # Processing state
        self.is_processing = False
        self.should_stop = False
        self.scanned_items = []
        self.output_directory = None

        # Build UI
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("#1f2937", "#111827"))
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        icon_lbl = ctk.CTkLabel(
            header_frame,
            text="🛡️",
            font=ctk.CTkFont(size=36)
        )
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(15, 10), pady=12)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="ZeroMeta AI • Removedor Definitivo de Metadados & C2PA",
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w"
        )
        title_lbl.grid(row=0, column=1, sticky="w", pady=(12, 0))

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text="Elimina manifestos de IA (OpenAI, ChatGPT, Midjourney, Adobe), GPS, Câmera, Prompts e Histórico sem perder qualidade de imagem.",
            font=ctk.CTkFont(size=12),
            text_color="gray75",
            anchor="w"
        )
        subtitle_lbl.grid(row=1, column=1, sticky="w", pady=(0, 12))

        btn_mobile = ctk.CTkButton(
            header_frame,
            text="📱 Usar no Celular",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            width=140,
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._open_mobile_dialog
        )
        btn_mobile.grid(row=0, column=2, rowspan=2, padx=(10, 15), pady=12)

        # 2. Folder Selection & Options Card
        controls_card = ctk.CTkFrame(self, corner_radius=10)
        controls_card.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        controls_card.grid_columnconfigure(1, weight=1)

        # Folder Picker
        dir_lbl = ctk.CTkLabel(controls_card, text="Diretório das Fotos:", font=ctk.CTkFont(weight="bold"))
        dir_lbl.grid(row=0, column=0, padx=(15, 10), pady=(12, 6), sticky="w")

        self.dir_entry = ctk.CTkEntry(
            controls_card,
            placeholder_text="Clique em 'Selecionar Pasta' ou cole o caminho aqui (ex: C:\\Imagens\\Fotos)"
        )
        self.dir_entry.grid(row=0, column=1, padx=5, pady=(12, 6), sticky="ew")

        btn_browse = ctk.CTkButton(
            controls_card,
            text="📂 Selecionar Pasta",
            width=140,
            command=self._select_folder
        )
        btn_browse.grid(row=0, column=2, padx=5, pady=(12, 6))

        btn_browse_file = ctk.CTkButton(
            controls_card,
            text="📄 Foto Única",
            width=110,
            fg_color="gray40",
            hover_color="gray30",
            command=self._select_single_file
        )
        btn_browse_file.grid(row=0, column=3, padx=(5, 15), pady=(12, 6))

        # Checkboxes & Options Frame
        opts_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        opts_frame.grid(row=1, column=0, columnspan=4, padx=15, pady=(4, 12), sticky="ew")
        opts_frame.grid_columnconfigure(3, weight=1)

        self.var_recursive = ctk.BooleanVar(value=True)
        chk_rec = ctk.CTkCheckBox(
            opts_frame,
            text="Varrer subpastas recursivamente",
            variable=self.var_recursive
        )
        chk_rec.grid(row=0, column=0, padx=(0, 15), pady=4, sticky="w")

        self.var_destination = ctk.StringVar(value="new_folder")
        rb_new_folder = ctk.CTkRadioButton(
            opts_frame,
            text="Salvar em subpasta '_fotos_limpas'",
            variable=self.var_destination,
            value="new_folder",
            command=self._toggle_destination_ui
        )
        rb_new_folder.grid(row=0, column=1, padx=10, pady=4, sticky="w")

        rb_overwrite = ctk.CTkRadioButton(
            opts_frame,
            text="Sobrescrever originais",
            variable=self.var_destination,
            value="overwrite",
            command=self._toggle_destination_ui
        )
        rb_overwrite.grid(row=0, column=2, padx=10, pady=4, sticky="w")

        self.var_backup = ctk.BooleanVar(value=True)
        self.chk_backup = ctk.CTkCheckBox(
            opts_frame,
            text="Criar backup (.bak)",
            variable=self.var_backup,
            state="disabled"
        )
        self.chk_backup.grid(row=0, column=3, padx=10, pady=4, sticky="w")

        self.var_reset_timestamps = ctk.BooleanVar(value=True)
        chk_time = ctk.CTkCheckBox(
            opts_frame,
            text="Resetar data de arquivo no Windows",
            variable=self.var_reset_timestamps
        )
        chk_time.grid(row=0, column=4, padx=(10, 0), pady=4, sticky="w")

        # 3. Action Bar & Stats Frame
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        # Action Buttons
        btn_box = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_box.pack(side="top", fill="x", pady=(0, 8))

        self.btn_start = ctk.CTkButton(
            btn_box,
            text="🚀 INICIAR LIMPEZA DE METADADOS",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self._start_cleaning
        )
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_audit = ctk.CTkButton(
            btn_box,
            text="🔍 Apenas Auditar (Sem Alterar)",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._start_audit
        )
        self.btn_audit.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(
            btn_box,
            text="⏹️ Parar",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            state="disabled",
            command=self._stop_processing
        )
        self.btn_stop.pack(side="left", padx=5)

        self.btn_open_dest = ctk.CTkButton(
            btn_box,
            text="📂 Abrir Pasta de Destino",
            height=40,
            state="disabled",
            fg_color="gray30",
            hover_color="gray25",
            command=self._open_output_folder
        )
        self.btn_open_dest.pack(side="right", padx=(5, 0))

        # Metrics Cards Frame
        stats_cards = ctk.CTkFrame(action_frame, corner_radius=8, fg_color=("#1e293b", "#0f172a"))
        stats_cards.pack(side="top", fill="x", pady=2)
        stats_cards.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_total = self._create_metric_card(stats_cards, 0, "Fotos Processadas", "0", "🖼️")
        self.card_c2pa = self._create_metric_card(stats_cards, 1, "Rastros C2PA / IA", "0", "🤖", highlight=True)
        self.card_exif = self._create_metric_card(stats_cards, 2, "EXIF / GPS / Câmera", "0", "📍")
        self.card_saved = self._create_metric_card(stats_cards, 3, "Espaço Economizado", "0 KB", "💾")

        # Progress bar & label
        prog_box = ctk.CTkFrame(action_frame, fg_color="transparent")
        prog_box.pack(side="top", fill="x", pady=(8, 2))
        prog_box.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(prog_box)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.progress_bar.set(0.0)

        self.lbl_status = ctk.CTkLabel(
            prog_box,
            text="Pronto. Selecione a pasta ou fotos para iniciar.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
            anchor="w"
        )
        self.lbl_status.grid(row=1, column=0, sticky="w")

        # 4. Results Table
        table_frame = ctk.CTkFrame(self, corner_radius=10)
        table_frame.grid(row=3, column=0, padx=15, pady=(5, 15), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(1, weight=1)

        table_header = ctk.CTkFrame(table_frame, fg_color="transparent")
        table_header.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        tbl_title = ctk.CTkLabel(
            table_header,
            text="Relatório de Arquivos (Dê um duplo clique para inspecionar os metadados em detalhes)",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        tbl_title.pack(side="left")

        self.lbl_table_count = ctk.CTkLabel(
            table_header,
            text="0 itens",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        self.lbl_table_count.pack(side="right")

        # Treeview styling
        tree_container = tk.Frame(table_frame, bg="#18181b")
        tree_container.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#18181b",
            foreground="#f4f4f5",
            fieldbackground="#18181b",
            rowheight=26,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background="#27272a",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map("Treeview", background=[("selected", "#0284c7")])

        cols = ("name", "format", "c2pa", "exif", "status", "size_before", "size_after")
        self.tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("name", text="Arquivo")
        self.tree.heading("format", text="Formato")
        self.tree.heading("c2pa", text="C2PA / Assinatura IA")
        self.tree.heading("exif", text="EXIF / GPS / Prompts")
        self.tree.heading("status", text="Status")
        self.tree.heading("size_before", text="Tamanho Original")
        self.tree.heading("size_after", text="Tamanho Limpo")

        self.tree.column("name", width=260, anchor="w")
        self.tree.column("format", width=70, anchor="center")
        self.tree.column("c2pa", width=170, anchor="w")
        self.tree.column("exif", width=170, anchor="w")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("size_before", width=110, anchor="e")
        self.tree.column("size_after", width=110, anchor="e")

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _create_metric_card(self, parent, col, title, value, icon, highlight=False):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, padx=10, pady=8)

        color = "#38bdf8" if highlight else "#ffffff"
        icon_lbl = ctk.CTkLabel(frame, text=icon, font=ctk.CTkFont(size=20))
        icon_lbl.pack(side="left", padx=(0, 8))

        content_box = ctk.CTkFrame(frame, fg_color="transparent")
        content_box.pack(side="left")

        val_lbl = ctk.CTkLabel(
            content_box,
            text=value,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=color
        )
        val_lbl.pack(anchor="w")

        title_lbl = ctk.CTkLabel(
            content_box,
            text=title,
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        title_lbl.pack(anchor="w")

        return val_lbl

    def _toggle_destination_ui(self):
        is_overwrite = self.var_destination.get() == "overwrite"
        if is_overwrite:
            self.chk_backup.configure(state="normal")
        else:
            self.chk_backup.configure(state="disabled")

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Selecione a Pasta de Fotos")
        if folder:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, folder)
            self._preview_file_count(folder)

    def _select_single_file(self):
        file = filedialog.askopenfilename(
            title="Selecione uma Imagem",
            filetypes=[
                ("Arquivos de Imagem", "*.jpg *.jpeg *.png *.webp *.tiff *.bmp *.jfif"),
                ("Todos os Arquivos", "*.*")
            ]
        )
        if file:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, file)
            self.lbl_status.configure(text=f"1 foto selecionada: {os.path.basename(file)}")

    def _preview_file_count(self, folder):
        try:
            images = scan_directory_images(folder, recursive=self.var_recursive.get())
            self.lbl_status.configure(text=f"Pasta carregada: {len(images)} foto(s) encontrada(s).")
        except Exception:
            pass

    def _open_mobile_dialog(self):
        MobileQrDialog(self)

    def _format_bytes(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
        idx = int(item_id)
        if 0 <= idx < len(self.scanned_items):
            item_data = self.scanned_items[idx]
            info = item_data.get("info_before") or item_data
            MetadataDetailDialog(self, info)

    def _open_output_folder(self):
        if self.output_directory and os.path.exists(self.output_directory):
            try:
                os.startfile(self.output_directory)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o diretório: {e}")

    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.scanned_items.clear()
        self.lbl_table_count.configure(text="0 itens")
        self.card_total.configure(text="0")
        self.card_c2pa.configure(text="0")
        self.card_exif.configure(text="0")
        self.card_saved.configure(text="0 KB")

    def _set_ui_state(self, is_running: bool):
        self.is_processing = is_running
        state = "disabled" if is_running else "normal"
        self.btn_start.configure(state=state)
        self.btn_audit.configure(state=state)
        self.btn_stop.configure(state="normal" if is_running else "disabled")
        if not is_running and self.output_directory and os.path.exists(self.output_directory):
            self.btn_open_dest.configure(state="normal")

    def _start_cleaning(self):
        path = self.dir_entry.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Aviso", "Por favor, selecione uma pasta ou arquivo de imagem válido.")
            return

        self._clear_tree()
        self._set_ui_state(True)
        self.should_stop = False

        thread = threading.Thread(target=self._worker_cleaning, args=(path,), daemon=True)
        thread.start()

    def _start_audit(self):
        path = self.dir_entry.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Aviso", "Por favor, selecione uma pasta ou arquivo de imagem válido.")
            return

        self._clear_tree()
        self._set_ui_state(True)
        self.should_stop = False

        thread = threading.Thread(target=self._worker_audit, args=(path,), daemon=True)
        thread.start()

    def _stop_processing(self):
        self.should_stop = True
        self.lbl_status.configure(text="Solicitando cancelamento... aguarde.")

    def _worker_cleaning(self, target_path: str):
        is_single = os.path.isfile(target_path)
        is_overwrite = self.var_destination.get() == "overwrite"
        make_backup = self.var_backup.get() and is_overwrite
        reset_timestamps = self.var_reset_timestamps.get()

        if is_single:
            images = [target_path]
            input_dir = os.path.dirname(target_path)
            output_dir = input_dir if is_overwrite else os.path.join(input_dir, "_fotos_limpas")
        else:
            input_dir = target_path
            output_dir = input_dir if is_overwrite else os.path.join(input_dir, "_fotos_limpas")
            images = scan_directory_images(input_dir, recursive=self.var_recursive.get())

        self.output_directory = output_dir
        total = len(images)
        if total == 0:
            self.after(0, lambda: self.lbl_status.configure(text="Nenhuma imagem encontrada para processar."))
            self.after(0, lambda: self._set_ui_state(False))
            return

        c2pa_count = 0
        exif_count = 0
        bytes_saved = 0
        success_count = 0

        for idx, src_file in enumerate(images, 1):
            if self.should_stop:
                break

            # Calculate destination path
            if is_overwrite:
                dst_file = src_file
                if make_backup:
                    bak_path = src_file + ".bak"
                    if not os.path.exists(bak_path):
                        import shutil
                        shutil.copy2(src_file, bak_path)
            else:
                rel_path = os.path.relpath(src_file, input_dir)
                dst_file = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)

            res = clean_single_image(
                src_path=src_file,
                dst_path=dst_file,
                mode="smart_lossless",
                reset_os_timestamps=reset_timestamps
            )

            if res["success"]:
                success_count += 1
                if res["c2pa_detected"]:
                    c2pa_count += 1
                if res["exif_detected"] or res["gps_detected"]:
                    exif_count += 1
                bytes_saved += max(0, res["bytes_saved"])

            self.after(0, self._update_row_result, idx - 1, res, idx, total, success_count, c2pa_count, exif_count, bytes_saved)

        self.after(0, self._finish_processing, total, success_count, c2pa_count)

    def _worker_audit(self, target_path: str):
        is_single = os.path.isfile(target_path)
        if is_single:
            images = [target_path]
        else:
            images = scan_directory_images(target_path, recursive=self.var_recursive.get())

        total = len(images)
        if total == 0:
            self.after(0, lambda: self.lbl_status.configure(text="Nenhuma foto encontrada."))
            self.after(0, lambda: self._set_ui_state(False))
            return

        c2pa_count = 0
        exif_count = 0

        for idx, src_file in enumerate(images, 1):
            if self.should_stop:
                break

            info = inspect_image_metadata(src_file)
            if info["has_c2pa"]:
                c2pa_count += 1
            if info["has_exif"] or info["has_gps"]:
                exif_count += 1

            audit_res = {
                "success": True,
                "src": src_file,
                "dst": src_file,
                "original_size": info["file_size"],
                "new_size": info["file_size"],
                "bytes_saved": 0,
                "used_method": "audit_only",
                "c2pa_detected": info["has_c2pa"],
                "ai_prompt_detected": info["has_ai_prompt"],
                "exif_detected": info["has_exif"],
                "gps_detected": info["has_gps"],
                "info_before": info,
                "error": None
            }

            self.after(0, self._update_row_result, idx - 1, audit_res, idx, total, idx, c2pa_count, exif_count, 0, True)

        self.after(0, self._finish_audit, total, c2pa_count)

    def _update_row_result(self, row_idx, res, current, total, success_count, c2pa_count, exif_count, bytes_saved, is_audit=False):
        self.scanned_items.append(res)

        info = res.get("info_before", {})
        fname = os.path.basename(res["src"])
        ext = os.path.splitext(fname)[1].upper().replace(".", "")

        # Format C2PA badge
        c2pa_text = "—"
        if res.get("c2pa_detected"):
            c2pa_sum = info.get("c2pa_summary", {})
            agents = c2pa_sum.get("software_agents", [])
            gens = c2pa_sum.get("generators", [])
            if agents:
                c2pa_text = f"🤖 IA: {', '.join(agents)}"
            elif gens:
                c2pa_text = f"🤖 {', '.join(gens)}"
            else:
                c2pa_text = "🤖 C2PA Presente"

        # Format EXIF badge
        exif_parts = []
        if res.get("gps_detected"):
            exif_parts.append("📍 GPS")
        if res.get("ai_prompt_detected"):
            exif_parts.append("🧠 Prompt")
        if res.get("exif_detected"):
            exif_parts.append("📷 EXIF")
        exif_text = " • ".join(exif_parts) if exif_parts else "—"

        status_text = "🔍 Auditado" if is_audit else ("✅ 100% Limpo" if res["success"] else "❌ Erro")
        size_before_str = self._format_bytes(res["original_size"])
        size_after_str = self._format_bytes(res["new_size"]) if not is_audit else "—"

        self.tree.insert(
            "",
            "end",
            iid=str(row_idx),
            values=(fname, ext, c2pa_text, exif_text, status_text, size_before_str, size_after_str)
        )
        self.tree.see(str(row_idx))

        # Update stats
        progress_val = current / max(1, total)
        self.progress_bar.set(progress_val)
        self.lbl_status.configure(text=f"Processando [{current}/{total}]: {fname}")
        self.lbl_table_count.configure(text=f"{current} de {total} itens")

        self.card_total.configure(text=str(current))
        self.card_c2pa.configure(text=str(c2pa_count))
        self.card_exif.configure(text=str(exif_count))
        self.card_saved.configure(text=self._format_bytes(bytes_saved))

    def _finish_processing(self, total, success, c2pa_count):
        self._set_ui_state(False)
        self.progress_bar.set(1.0)
        self.lbl_status.configure(text=f"Concluído! {success} de {total} fotos limpas. {c2pa_count} rastros de IA/C2PA eliminados.")
        messagebox.showinfo(
            "Limpeza Concluída",
            f"Processamento finalizado com sucesso!\n\n"
            f"• Total de fotos: {total}\n"
            f"• Limpas com êxito: {success}\n"
            f"• Manifestos C2PA / IA eliminados: {c2pa_count}\n"
            f"• Destino: {self.output_directory}"
        )

    def _finish_audit(self, total, c2pa_count):
        self._set_ui_state(False)
        self.progress_bar.set(1.0)
        self.lbl_status.configure(text=f"Auditoria concluída! {total} fotos analisadas ({c2pa_count} com IA/C2PA).")
        messagebox.showinfo(
            "Auditoria Concluída",
            f"Varredura de metadados concluída!\n\n"
            f"• Total de fotos analisadas: {total}\n"
            f"• Fotos com C2PA / IA detectadas: {c2pa_count}\n\n"
            f"Nenhuma foto foi alterada. Para limpá-las, clique em 'INICIAR LIMPEZA DE METADADOS'."
        )


def launch_gui():
    app = MainWindow()
    app.mainloop()
