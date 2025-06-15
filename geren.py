import os;import shutil;import sys;import subprocess;import zipfile;import tarfile;import rarfile;from pathlib import Path
import tkinter as tk; from tkinter import messagebox; import customtkinter as ctk; from win32com.client import Dispatch; import tempfile
import threading; import datetime; import math; from watchdog.observers import Observer; from watchdog.events import FileSystemEventHandler
import hashlib

# Configuração do tema
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

# Ícones para diferentes tipos de arquivos
ICONS = {
    'folder': '📁', 'archive': '🗄', 'image': '🖼', 'audio': '🎵',
    'video': '🎬', 'executable': '⚙️', 'default': '📄'
}

# Extensões de arquivo por tipo
FILE_TYPES = {
    'archive': ['.zip', '.rar', '.tar', '.gz', '.bz2', '.7z'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
    'audio': ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'],
    'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'],
    'executable': ['.exe', '.msi', '.bat', '.cmd', '.ps1']
}

class FileManagerEventHandler(FileSystemEventHandler):
    def __init__(self, file_manager):
        self.file_manager = file_manager
    
    def on_any_event(self, event):
        # Atualiza a visualização quando ocorrer qualquer mudança no diretório
        if (event.event_type == 'modified') or (getattr(event, 'is_synthetic', False) and event.event_type == 'modified'):
            return
        
        # Usa after para agendar a atualização na thread principal do Tkinter
        self.file_manager.after(500, self.file_manager.refresh_current_directory)

class FileManager(ctk.CTk):
    def __init__(self, initial_path=None):
        super().__init__()

        # Configurações do watchdog
        self.observer = None
        self.event_handler = None
        self.current_watched_path = None
        
        self.title("Gerenciador de Arquivos")
        self.geometry("900x600")
        # Histórico de navegação
        self.history = []
        self.history_index = -1
        
        # Variáveis para o menu de contexto
        self.context_menu = None
        self.selected_item = None
        
        # Área de transferência para copiar/mover
        self.clipboard = {"items": set(), "operation": None}
        
        # Arquivos compactados abertos
        self.open_archives = {}
        
        # Configurar layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.create_widgets()
        self.load_special_folders()
        
        # Verifica se foi passado um caminho inicial como argumento
        if initial_path:
            self.navigate_to(Path(initial_path))
        else:
            self.navigate_to(Path.home())
        
        # Configurar eventos de teclado
        self.bind("<Control-c>", lambda e: self.copy_selected_item())
        self.bind("<Control-x>", lambda e: self.cut_selected_item())
        self.bind("<Control-v>", lambda e: self.paste_item())
        
        self.last_folder_before_archive = None  # Guarda a última pasta antes de abrir um arquivo compactado
        
        # Dictionary to store size labels for updating from threads
        self._size_labels = {}
    
    def get_file_icon(self, path):
        if isinstance(path, str):
            path = Path(path)
        
        if path.is_dir():
            return ICONS['folder']
        
        ext = path.suffix.lower()
        for file_type, extensions in FILE_TYPES.items():
            if ext in extensions:
                return ICONS[file_type]
        return ICONS['default']
    
    def setup_watchdog(self, path):
        """Configura o watchdog para monitorar o diretório atual"""
        # Para o observer atual se existir
        if self.observer is not None:
            try:
                if self.observer.is_alive():
                    self.observer.unschedule_all()
                    self.observer.stop()
                    self.observer.join()
            except:
                pass
        
        # Só monitora se for um diretório real (não arquivo compactado)
        if path.is_dir():
            try:
                self.current_watched_path = path
                self.event_handler = FileManagerEventHandler(self)
                self.observer = Observer()
                self.observer.schedule(self.event_handler, str(path), recursive=False)
                self.observer.start()
            except Exception as e:
                print(f"Erro ao configurar observer: {e}")
                self.observer = None
        else:
            self.current_watched_path = None
    
    def refresh_current_directory(self):
        """Atualiza a visualização do diretório atual"""
        current_path = Path(self.address_bar.get())
        if current_path.exists():
            self.navigate_to(current_path)
    
    def safe_refresh(self):
        """Atualização segura que verifica se o caminho ainda existe"""
        try:
            current_path = Path(self.address_bar.get())
            if current_path.exists():
                self.navigate_to(current_path)
        except Exception as e:
            print(f"Erro durante atualização: {e}")

    def reactivate_observer(self):
        """Reativa o observer após operações críticas"""
        current_path = Path(self.address_bar.get())
        if current_path.exists():
            self.setup_watchdog(current_path)
        self.safe_refresh()
    
    def create_widgets(self):
        # Barra de navegação superior
        nav_frame = ctk.CTkFrame(self, height=40)
        nav_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        nav_frame.grid_columnconfigure(2, weight=1)
        
        # Frame para os botões de navegação
        nav_buttons_frame = ctk.CTkFrame(nav_frame, fg_color="transparent")
        nav_buttons_frame.grid(row=0, column=0, sticky="w")
        
        # Botão voltar
        self.back_btn = ctk.CTkButton(
            nav_buttons_frame, text="←", width=30, command=self.go_back,
            fg_color="transparent", hover_color=("#DDD", "#444"))
        self.back_btn.pack(side="left", padx=(0, 2))
        
        # Botão avançar
        self.forward_btn = ctk.CTkButton(
            nav_buttons_frame, text="→", width=30, command=self.go_forward,
            fg_color="transparent", hover_color=("#DDD", "#444"))
        self.forward_btn.pack(side="left", padx=(0, 5))
        
        # Barra de endereço
        self.address_bar = ctk.CTkEntry(nav_frame)
        self.address_bar.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        self.address_bar.bind("<Return>", self.navigate_from_address_bar)
        
        # Barra de pesquisa (novo campo)
        self.search_bar = ctk.CTkEntry(nav_frame, placeholder_text="Pesquisar na pasta...")
        self.search_bar.grid(row=0, column=4, sticky="nsew", padx=5, pady=5)
        self.search_bar.bind("<Return>", self.search_in_current_folder)
        
        # Botão de extrair (será mostrado apenas para arquivos compactados)
        self.extract_btn = ctk.CTkButton(
            nav_frame, text="Extrair", width=80, command=self.extract_archive,
            fg_color="#2A8C36", hover_color="#3DA64A")
        self.extract_btn.grid(row=0, column=5, sticky="e", padx=(0, 5))
        self.extract_btn.grid_remove()  # Escondido inicialmente
        
        # Frame principal
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=(0, 5))
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Frame de pastas especiais (esquerda)
        self.special_folders_frame = ctk.CTkScrollableFrame(main_frame, width=150, label_text="Favoritos")
        self.special_folders_frame.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        
        # Frame de conteúdo (direita)
        self.content_frame = ctk.CTkScrollableFrame(main_frame)
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)
        self.content_frame.grid_columnconfigure(0, weight=1)
        
        # Configurar eventos de mouse
        self.content_frame.bind("<Button-3>", self.show_context_menu)
        self.content_frame.bind("<Double-Button-1>", self.on_double_click)
        self.content_frame.bind("<Button-1>", self.on_content_frame_click)
        
        # Atualizar botões de navegação
        self.update_nav_buttons()
        
        # Barra de endereço
        self.address_bar = ctk.CTkEntry(nav_frame)
        self.address_bar.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        self.address_bar.bind("<Return>", self.navigate_from_address_bar)

        # Botão de extrair
        self.extract_btn = ctk.CTkButton(
            nav_frame, text="Extrair", width=80, command=self.extract_archive,
            fg_color="#2A8C36", hover_color="#3DA64A")
        self.extract_btn.grid(row=0, column=5, sticky="e", padx=(0, 5))
        self.extract_btn.grid_remove()  # Escondido inicialmente

        # Ajustar as colunas para acomodar a nova barra de pesquisa
        nav_frame.grid_columnconfigure(2, weight=3)  # Barra de endereço mais larga
        nav_frame.grid_columnconfigure(4, weight=1)  # Barra de pesquisa
    
    def load_special_folders(self):
        default_favorites = {
                "Desktop": str(Path.home() / "Desktop"),
                "Documents": str(Path.home() / "Documents"),
                "Downloads": str(Path.home() / "Downloads"),
                "Pictures": str(Path.home() / "Pictures"),
                "Music": str(Path.home() / "Music"),
                "Videos": str(Path.home() / "Videos")
        }
        favorites = {}
        for name, path in default_favorites.items():
            favorites[name] = path
        # Cria os botões para as pastas favoritas com melhor hover
        for name, path in favorites.items():
            btn = ctk.CTkButton(
                self.special_folders_frame, 
                text=f"{ICONS['folder']} {name}", 
                command=lambda p=path: self.navigate_to(Path(p)),
                anchor="w",
                fg_color="transparent",
                hover_color=("#DDD", "#444"))
            btn.pack(fill="x", pady=2, padx=5)
    
    def navigate_to(self, path):
        try:
            path = path.resolve()  # Obtém o caminho absoluto
            # Verifica se é um diretório válido ou arquivo compactado
            if not path.is_dir() and not self.is_supported_archive(path):
                messagebox.showerror("Erro", f"{path} não é um diretório válido ou arquivo compactado suportado.")
                return
            
            # Configura o watchdog para o novo diretório
            self.setup_watchdog(path)
            
            # Limpa a seleção ao navegar para uma nova pasta
            self.selected_item = None
            
            # Atualiza o histórico de navegação
            if self.history_index == -1 or self.history[self.history_index] != str(path):
                if self.history_index + 1 < len(self.history):
                    self.history = self.history[:self.history_index + 1]
                
                self.history.append(str(path))
                self.history_index += 1
            
            # Atualiza a barra de endereço
            self.address_bar.delete(0, tk.END)
            self.address_bar.insert(0, str(path))
            
            # Salva a última pasta antes de abrir um arquivo compactado
            if self.is_supported_archive(path):
                # Só atualiza se não está vindo de outro arquivo compactado
                if self.last_folder_before_archive is None or not self.is_supported_archive(Path(self.history[self.history_index-1])):
                    self.last_folder_before_archive = path.parent
            else:
                self.last_folder_before_archive = None
            
            # Mostra ou esconde o botão de extrair
            if self.is_supported_archive(path):
                self.extract_btn.grid()
            else:
                self.extract_btn.grid_remove()
            
            # Limpa o frame de conteúdo e reseta o scroll
            for widget in self.content_frame.winfo_children():
                widget.destroy()
            
            # Força a atualização do frame de conteúdo
            self.content_frame.update_idletasks()
            
            # Reseta a posição do scroll
            self.content_frame._parent_canvas.yview_moveto(0)
            
            # Verifica se é um arquivo compactado
            if self.is_supported_archive(path):
                self.show_archive_contents(path)
            else:
                # Navegação normal para pastas
                self.show_folder_contents(path)
            
            # Atualiza os botões de navegação
            self.update_nav_buttons()
            
            # Força uma atualização completa da interface
            self.update_idletasks()
            
        except PermissionError:
            messagebox.showerror("Erro", f"Permissão negada para acessar {path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro: {str(e)}")
    
    def is_supported_archive(self, path):
        if not path.is_file():
            return False
        return path.suffix.lower() in FILE_TYPES['archive']
    
    def show_folder_contents(self, path):
        # Limpa o frame de conteúdo
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        # Add ".." to navigate to the parent folder (always present)
        parent_btn = ctk.CTkButton(
            self.content_frame,
            text=f"{ICONS['folder']} .. [ Pasta ]",
            command=lambda: self.navigate_to(path.parent),
            anchor="w",
            fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
            hover_color=("#DDD", "#444"))
        parent_btn.grid(row=0, column=0, sticky="ew", pady=2, padx=5)
        parent_btn.bind("<Button-3>", lambda e, p=str(path.parent): self.show_context_menu(e, p))
        # Lista os itens no diretório
        row = 1
        try:
            # Usa scandir para melhor performance
            with os.scandir(path) as entries:
                # Primeiro ordena as pastas, depois os arquivos
                dirs = []
                files = []
                for entry in entries:
                    if entry.is_dir():
                        dirs.append(entry)
                    else:
                        files.append(entry)

                # Ordena as pastas e arquivos por nome
                dirs.sort(key=lambda x: x.name.lower())
                files.sort(key=lambda x: x.name.lower())

                # Add folders first
                for entry in dirs:
                    item_path = Path(entry.path)
                    item_name = entry.name
                    icon = ICONS['folder']

                    # Truncate long folder names
                    display_name = item_name if len(item_name) <= 40 else item_name[:37] + '...'

                    # Calculate folder size using the existing method
                    size = self.calculate_folder_size_sync(item_path)
                    size_str = self.convert_size(size)

                    # Display folders with size information
                    btn_text = f"{icon} {display_name} [ Pasta ] [{size_str}]"

                    btn = ctk.CTkButton(
                        self.content_frame,
                        text=btn_text,
                        command=lambda p=str(item_path): self.navigate_to(Path(p)),
                        anchor="w",
                        fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                        hover_color=("#DDD", "#444"))
                    btn.grid(row=row, column=0, sticky="ew", pady=2, padx=5)
                    btn.bind("<Button-1>", lambda e, p=str(item_path): self.select_item(e, p))
                    btn.bind("<Button-3>", lambda e, p=str(item_path): self.show_context_menu(e, p))
                    btn.bind("<Double-Button-1>", lambda e, p=str(item_path): self.on_double_click(e, p))
                    row += 1

                # Add files after
                for entry in files:
                    item_path = Path(entry.path)
                    item_name = entry.name
                    icon = self.get_file_icon(item_path)

                    # Truncate long file names
                    display_name = item_name if len(item_name) <= 30 else item_name[:27] + '...'

                    # Get file size using Windows API
                    shell = Dispatch("Shell.Application")
                    file = shell.Namespace(0).ParseName(str(item_path.absolute()))
                    size = file.Size if file else 0
                    size_str = self.convert_size(size)

                    btn = ctk.CTkButton(
                        self.content_frame,
                        text=f"{icon} {display_name} [ Arquivo ] [{size_str}]",
                        anchor="w",
                        fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                        hover_color=("#DDD", "#444"))

                    btn.grid(row=row, column=0, sticky="ew", pady=2, padx=5)
                    btn.bind("<Button-1>", lambda e, p=str(item_path): self.select_item(e, p))
                    btn.bind("<Button-3>", lambda e, p=str(item_path): self.show_context_menu(e, p))
                    btn.bind("<Double-Button-1>", lambda e, p=str(item_path): self.on_double_click(e, p))
                    row += 1
        except Exception as e:
            # print(f"Error listing directory {path}: {e}") # Keep for debugging
            pass # Keep the pass for the outer try/except
    
    def show_archive_contents(self, archive_path):
        # Limpa o frame de conteúdo
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        # Adiciona ".." para navegar para a pasta pai
        parent_btn = ctk.CTkButton(
            self.content_frame, 
            text=f"{ICONS['folder']} .. [ Pasta ]", 
            command=lambda: self.navigate_to(archive_path.parent),
            anchor="w",
            fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
            hover_color=("#DDD", "#444"))
        parent_btn.grid(row=0, column=0, sticky="ew", pady=2, padx=5)
        parent_btn.bind("<Button-3>", lambda e, p=str(archive_path.parent): self.show_context_menu(e, p))
        # Mostra indicador de carregamento
        loading_label = ctk.CTkLabel(self.content_frame, text="Carregando...")
        loading_label.grid(row=1, column=0, pady=10)
        def load_members():
            try:
                archive_members = self.get_archive_members(archive_path)
                sorted_members = sorted(archive_members, key=lambda x: (not x['is_dir'], x['name'].lower()))
                def display():
                    loading_label.destroy()
                    row = 1
                    for member in sorted_members:
                        icon = ICONS['folder'] if member['is_dir'] else self.get_file_icon(Path(member['name']))

                        # Truncate long archive member names
                        display_name = member['name'] if len(member['name']) <= 40 else member['name'][:37] + '...'

                        btn = ctk.CTkButton(
                            self.content_frame,
                            text=f"{icon} {display_name}", # Use icon and truncated name
                            anchor="w",
                            fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                            hover_color=("#DDD", "#444"))
                        btn.grid(row=row, column=0, sticky="ew", pady=2, padx=5)
                        btn.member_info = {
                            'archive_path': str(archive_path),
                            'member_path': member['path'],
                            'is_dir': member['is_dir']
                        }
                        btn.bind("<Button-1>", lambda e, b=btn: self.select_archive_item(e, b))
                        btn.bind("<Button-3>", lambda e, b=btn: self.show_archive_context_menu(e, b))
                        btn.bind("<Double-Button-1>", lambda e, b=btn: self.on_archive_double_click(e, b))
                        row += 1
                self.content_frame.after(0, display)
            except Exception as e:
                self.content_frame.after(0, lambda: loading_label.configure(text=f"Erro: {str(e)}"))
        threading.Thread(target=load_members).start()
    
    def get_archive_members(self, archive_path):
        ext = archive_path.suffix.lower()
        members = []
        try:
            if ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    for member in zip_ref.infolist():
                        is_dir = member.is_dir() or member.filename.endswith('/')
                        members.append({
                            'name': Path(member.filename).name,
                            'path': member.filename,
                            'is_dir': is_dir
                        })
            
            elif ext == '.rar':
                with rarfile.RarFile(archive_path, 'r') as rar_ref:
                    for member in rar_ref.infolist():
                        is_dir = member.isdir()
                        members.append({
                            'name': Path(member.filename).name,
                            'path': member.filename,
                            'is_dir': is_dir
                        })
            
            elif ext in ['.tar', '.tar.gz', '.tar.bz2']:
                mode = 'r'
                if ext == '.tar.gz':
                    mode = 'r:gz'
                elif ext == '.tar.bz2':
                    mode = 'r:bz2'
                
                with tarfile.open(archive_path, mode) as tar_ref:
                    for member in tar_ref.getmembers():
                        is_dir = member.isdir()
                        members.append({
                            'name': Path(member.name).name,
                            'path': member.name,
                            'is_dir': is_dir
                        })
        
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao ler arquivo compactado: {str(e)}")
        return members
    
    def select_archive_item(self, event, button):
        # Define o item selecionado
        self.selected_item = button
    
    def show_archive_context_menu(self, event, button):
        # Destrói o menu de contexto anterior se existir
        if self.context_menu:
            self.context_menu.destroy()
        
        member_info = button.member_info
        current_path = Path(self.address_bar.get())
        
        # Cria um novo menu de contexto
        self.context_menu = tk.Menu(self, tearoff=0, 
                                  bg="#333" if ctk.get_appearance_mode() == "Dark" else "#EEE", 
                                  fg="#FFF" if ctk.get_appearance_mode() == "Dark" else "#000")
        
        # Define o item selecionado
        self.selected_item = button
        # Itens do menu para arquivos/pastas dentro do arquivo compactado
        self.context_menu.add_command(
            label="Copiar", 
            command=lambda: self.copy_archive_item(button))
        
        if not member_info['is_dir']:
            self.context_menu.add_command(
                label="Extrair este arquivo", 
                command=lambda: self.extract_single_file(button))
        
        # Adiciona opção de propriedades
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Propriedades", 
            command=lambda: self.show_properties(button.member_info['archive_path'], 
                                               is_archive_member=True, 
                                               member_info=button.member_info))
        
        # Mostra o menu na posição do clique
        self.context_menu.tk_popup(event.x_root, event.y_root)
    
    def copy_archive_item(self, button):
        member_info = button.member_info
        self.clipboard_clear()
        # Cria um arquivo temporário com o conteúdo do item do arquivo compactado
        try:
            with tempfile.NamedTemporaryFile(delete=False, prefix='temp_', suffix=Path(member_info['path']).suffix) as temp_file:
                temp_path = Path(temp_file.name)
                
                ext = Path(member_info['archive_path']).suffix.lower()
                
                if ext == '.zip':
                    with zipfile.ZipFile(member_info['archive_path'], 'r') as zip_ref:
                        with zip_ref.open(member_info['member_path']) as member_file:
                            temp_file.write(member_file.read())
                
                elif ext == '.rar':
                    with rarfile.RarFile(member_info['archive_path'], 'r') as rar_ref:
                        with rar_ref.open(member_info['member_path']) as member_file:
                            temp_file.write(member_file.read())
                
                elif ext in ['.tar', '.tar.gz', '.tar.bz2']:
                    mode = 'r'
                    if ext == '.tar.gz':
                        mode = 'r:gz'
                    elif ext == '.tar.bz2':
                        mode = 'r:bz2'
                    
                    with tarfile.open(member_info['archive_path'], mode) as tar_ref:
                        with tar_ref.extractfile(member_info['member_path']) as member_file:
                            temp_file.write(member_file.read())
                
                # Copia o caminho do arquivo temporário para a área de transferência
                self.clipboard_append(str(temp_path.absolute()))
                self.update()
                
                # Agenda a exclusão do arquivo temporário após 5 minutos
                threading.Timer(300, lambda: temp_path.unlink(missing_ok=True)).start()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível copiar o item: {str(e)}")
    
    def extract_single_file(self, button):
        member_info = button.member_info
        dialog = ctk.CTkToplevel(self)
        dialog.title("Extrair Arquivo")
        dialog.geometry("400x250")
        dialog.attributes('-topmost', True)
        frame = ctk.CTkFrame(dialog)
        frame.pack(pady=20, padx=20, fill="both", expand=True)
        ctk.CTkLabel(frame, text="Nome do arquivo:").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(frame)
        name_entry.pack(pady=(0, 10), padx=20, fill="x")
        name_entry.insert(0, Path(member_info['member_path']).name)
        ctk.CTkLabel(frame, text="Caminho de destino (deixe em branco para pasta atual):").pack(pady=(10, 0))
        path_entry = ctk.CTkEntry(frame)
        path_entry.pack(pady=(0, 20), padx=20, fill="x")
        def perform_extraction():
            file_name = name_entry.get().strip()
            dest_path = path_entry.get().strip()
            if not file_name:
                file_name = Path(member_info['member_path']).name
            if not dest_path:
                # Usa a última pasta antes de abrir o arquivo compactado, se disponível
                if self.last_folder_before_archive:
                    dest_path = str(self.last_folder_before_archive)
                else:
                    dest_path = os.getcwd()
            try:
                dest_path = Path(dest_path) / file_name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                ext = Path(member_info['archive_path']).suffix.lower()
                if ext == '.zip':
                    with zipfile.ZipFile(member_info['archive_path'], 'r') as zip_ref:
                        with zip_ref.open(member_info['member_path']) as member_file:
                            with open(dest_path, 'wb') as f:
                                f.write(member_file.read())
                elif ext == '.rar':
                    with rarfile.RarFile(member_info['archive_path'], 'r') as rar_ref:
                        with rar_ref.open(member_info['member_path']) as member_file:
                            with open(dest_path, 'wb') as f:
                                f.write(member_file.read())
                elif ext in ['.tar', '.tar.gz', '.tar.bz2']:
                    mode = 'r'
                    if ext == '.tar.gz':
                        mode = 'r:gz'
                    elif ext == '.tar.bz2':
                        mode = 'r:bz2'
                    with tarfile.open(member_info['archive_path'], mode) as tar_ref:
                        with tar_ref.extractfile(member_info['member_path']) as member_file:
                            with open(dest_path, 'wb') as f:
                                f.write(member_file.read())
                messagebox.showinfo("Sucesso", f"Arquivo extraído para {dest_path}")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível extrair o arquivo: {str(e)}")
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=10)
        extract_btn = ctk.CTkButton(
            btn_frame, text="Extrair", command=perform_extraction)
        extract_btn.pack(side="left", padx=5)
        cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancelar", command=dialog.destroy)
        cancel_btn.pack(side="right", padx=5)
        name_entry.bind("<Return>", lambda e: perform_extraction())
        path_entry.bind("<Return>", lambda e: perform_extraction())
    
    def on_archive_double_click(self, event, button):
        member_info = button.member_info
        if member_info['is_dir']:
            # Navega para a "pasta" dentro do arquivo compactado
            new_path = f"{member_info['archive_path']}/{member_info['member_path']}"
            self.navigate_to(Path(new_path))
    
    def extract_archive(self):
        archive_path = Path(self.address_bar.get())
        if not self.is_supported_archive(archive_path):
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Extrair Arquivo Compactado")
        dialog.geometry("400x300")
        dialog.attributes('-topmost', True)
        frame = ctk.CTkFrame(dialog)
        frame.pack(pady=20, padx=20, fill="both", expand=True)
        ctk.CTkLabel(frame, text="Nome da pasta (deixe em branco para usar nome do arquivo):").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(frame)
        name_entry.pack(pady=(0, 10), padx=20, fill="x")
        name_entry.insert(0, archive_path.stem)
        ctk.CTkLabel(frame, text="Caminho de destino (deixe em branco para pasta atual):").pack(pady=(10, 0))
        path_entry = ctk.CTkEntry(frame)
        path_entry.pack(pady=(0, 20), padx=20, fill="x")
        def perform_extraction():
            folder_name = name_entry.get().strip()
            dest_path = path_entry.get().strip()
            if not folder_name:
                folder_name = archive_path.stem
            if not dest_path:
                # Usa a última pasta antes de abrir o arquivo compactado, se disponível
                if self.last_folder_before_archive:
                    dest_path = str(self.last_folder_before_archive)
                else:
                    dest_path = os.getcwd()
            try:
                full_dest_path = Path(dest_path) / folder_name
                full_dest_path.mkdir(parents=True, exist_ok=True)
                ext = archive_path.suffix.lower()
                if ext == '.zip':
                    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                        zip_ref.extractall(full_dest_path)
                elif ext == '.rar':
                    with rarfile.RarFile(archive_path, 'r') as rar_ref:
                        rar_ref.extractall(full_dest_path)
                elif ext in ['.tar', '.tar.gz', '.tar.bz2']:
                    mode = 'r'
                    if ext == '.tar.gz':
                        mode = 'r:gz'
                    elif ext == '.tar.bz2':
                        mode = 'r:bz2'
                    with tarfile.open(archive_path, mode) as tar_ref:
                        tar_ref.extractall(full_dest_path)
                messagebox.showinfo("Sucesso", f"Arquivo extraído para {full_dest_path}")
                dialog.destroy()
                self.navigate_to(full_dest_path)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível extrair o arquivo: {str(e)}")
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=10)
        extract_btn = ctk.CTkButton(
            btn_frame, text="Extrair", command=perform_extraction)
        extract_btn.pack(side="left", padx=5)
        cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancelar", command=dialog.destroy)
        cancel_btn.pack(side="right", padx=5)
        name_entry.bind("<Return>", lambda e: perform_extraction())
        path_entry.bind("<Return>", lambda e: perform_extraction())
    
    def on_double_click(self, event, item_path=None):
        if item_path:
            self.open_item(item_path)
    
    def navigate_from_address_bar(self, event=None):
        path = self.address_bar.get().strip()
        try:
            if path:
                self.navigate_to(Path(path))
                # Ensure focus is set to content frame after successful navigation
                self.after(10, self.content_frame.focus_set) # Set focus to content frame
        except Exception as e:
            messagebox.showerror("Erro de Navegação", f"Não foi possível navegar para {path}: {e}")
    
    def search_in_current_folder(self, event=None):
        search_term = self.search_bar.get().strip().lower()
        current_path = Path(self.address_bar.get())
    
        if not search_term:
            # Se a pesquisa estiver vazia, mostra todos os itens
            self.navigate_to(current_path)
    
        try:
            # Limpa o frame de conteúdo
            for widget in self.content_frame.winfo_children():
                widget.destroy()
        
            # Adiciona ".." para navegar para a pasta pai
            if current_path.parent != current_path:
                parent_btn = ctk.CTkButton(
                    self.content_frame, 
                    text=f"{ICONS['folder']} .. [ Pasta ]", 
                    command=lambda: self.navigate_to(current_path.parent),
                    anchor="w",
                    fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                    hover_color=("#DDD", "#444"))
                parent_btn.grid(row=0, column=0, sticky="ew", pady=2, padx=5)
        
            row = 1
            if self.is_supported_archive(current_path):
                # Pesquisa dentro do arquivo compactado
                archive_members = self.get_archive_members(current_path)
                for member in sorted(archive_members, key=lambda x: (not x['is_dir'], x['name'].lower())):
                    if search_term in member['name'].lower():
                        icon = ICONS['folder'] if member['is_dir'] else self.get_file_icon(Path(member['name']))
                        btn = ctk.CTkButton(
                            self.content_frame, 
                            text=f"{icon} {member['name']}", 
                            anchor="w",
                            fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                            hover_color=("#DDD", "#444"))
                        btn.grid(row=row, column=0, sticky="ew", pady=2, padx=5)
                        btn.member_info = {
                            'archive_path': str(current_path),
                            'member_path': member['path'],
                            'is_dir': member['is_dir']
                        }
                        btn.bind("<Button-1>", lambda e, b=btn: self.select_archive_item(e, b))
                        btn.bind("<Button-3>", lambda e, b=btn: self.show_archive_context_menu(e, b))
                        btn.bind("<Double-Button-1>", lambda e, b=btn: self.on_archive_double_click(e, b))
                        row += 1
            else:
                # Pesquisa em pastas normal
                for item in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    if search_term in item.name.lower():
                        item_name = item.name
                        item_path = str(item)
                        icon = self.get_file_icon(item)
                        if item.is_dir():
                            btn = ctk.CTkButton(
                                self.content_frame, 
                                text=f"{icon} {item_name} [ Pasta ]", 
                                command=lambda p=item_path: self.navigate_to(Path(p)),
                                anchor="w",
                                fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                                hover_color=("#DDD", "#444"))
                        else:
                            btn = ctk.CTkButton(
                                self.content_frame, 
                                text=f"{icon} {item_name} [ Arquivo ]", 
                                anchor="w",
                                fg_color="#3A3A3A" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                                hover_color=("#DDD", "#444"))
                        btn.grid(row=row, column=0, sticky="ew", pady=2, padx=5)
                        btn.bind("<Button-1>", lambda e, p=item_path: self.select_item(e, p))
                        btn.bind("<Button-3>", lambda e, p=item_path: self.show_context_menu(e, p))
                        btn.bind("<Double-Button-1>", lambda e, p=item_path: self.on_double_click(e, p))
                        row += 1
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro durante a pesquisa: {str(e)}")
        # Ensure focus is set to content frame after the search operation, regardless of outcome
        self.after(10, self.content_frame.focus_set) # Set focus to content frame
    
    def go_back(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.navigate_to(Path(self.history[self.history_index]))
    
    def go_forward(self):
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self.navigate_to(Path(self.history[self.history_index]))
    
    def update_nav_buttons(self):
        # Atualiza o estado dos botões de voltar/avançar
        self.back_btn.configure(state="normal" if self.history_index > 0 else "disabled")
        self.forward_btn.configure(state="normal" if self.history_index + 1 < len(self.history) else "disabled")
    
    def select_item(self, event, item_path):
        # Define o item selecionado
        self.selected_item = item_path
    
    def on_content_frame_click(self, event):
        # Verifica se o clique foi em um item ou em área vazia
        if not event.widget.winfo_containing(event.x_root, event.y_root):
            # Cria um menu simplificado para áreas vazias
            if self.context_menu:
                self.context_menu.destroy()
            
            current_path = Path(self.address_bar.get())
            
            self.context_menu = tk.Menu(self, tearoff=0,
                                      bg="#333" if ctk.get_appearance_mode() == "Dark" else "#EEE",
                                      fg="#FFF" if ctk.get_appearance_mode() == "Dark" else "#000")
            
            self.context_menu.add_command(
                label="Nova Pasta", 
                command=lambda: self.create_new_item(current_path, "folder"))
            
            self.context_menu.add_command(
                label="Novo Arquivo", 
                command=lambda: self.create_new_item(current_path, "file"))
            
            self.context_menu.tk_popup(event.x_root, event.y_root)
    
    def show_context_menu(self, event, item_path=None):
        # Destrói o menu de contexto anterior se existir
        if self.context_menu:
            self.context_menu.destroy()
        
        self.selected_item = item_path if item_path else None
        current_path = Path(self.address_bar.get())
        
        # Cria um novo menu de contexto com o tema do CustomTkinter
        self.context_menu = tk.Menu(self, tearoff=0, 
                                  bg="#333" if ctk.get_appearance_mode() == "Dark" else "#EEE", 
                                  fg="#FFF" if ctk.get_appearance_mode() == "Dark" else "#000")
        
        if self.selected_item:
            path = Path(self.selected_item)
            
            # Itens do menu para arquivos/pastas selecionados
            self.context_menu.add_command(
                label="Abrir", 
                command=lambda: self.open_item(self.selected_item))
            
            if path.is_file():
                self.context_menu.add_command(
                    label="Abrir com Bloco de Notas", 
                    command=lambda: self.open_in_notepad(self.selected_item))
            
            if path.is_dir():
                # Submenu para abrir terminal
                terminal_menu = tk.Menu(self.context_menu, tearoff=0,
                                       bg="#333" if ctk.get_appearance_mode() == "Dark" else "#EEE",
                                       fg="#FFF" if ctk.get_appearance_mode() == "Dark" else "#000")
                terminal_menu.add_command(
                    label="Abrir no CMD", 
                    command=lambda: self.open_in_terminal(self.selected_item, 'cmd'))
                terminal_menu.add_command(
                    label="Abrir no PowerShell", 
                    command=lambda: self.open_in_terminal(self.selected_item, 'powershell'))
                
                self.context_menu.add_cascade(label="Abrir no Terminal", menu=terminal_menu)
            
            self.context_menu.add_separator()
            
            self.context_menu.add_command(
                label="Copiar", 
                command=self.copy_selected_item)
            
            self.context_menu.add_command(
                label="Recortar", 
                command=self.cut_selected_item)
            
            self.context_menu.add_separator()
            
            self.context_menu.add_command(
                label="Renomear", 
                command=lambda: self.rename_item(self.selected_item))
            
            self.context_menu.add_command(
                label="Mover para Lixeira", 
                command=lambda: self.move_to_trash(self.selected_item))
            
            self.context_menu.add_separator()
            
            # Adiciona a opção de propriedades
            self.context_menu.add_command(
                label="Propriedades", 
                command=lambda: self.show_properties(self.selected_item))
        
        # Itens do menu para o diretório atual (sempre mostrados)
        self.context_menu.add_command(
            label="Nova Pasta", 
            command=lambda: self.create_new_item(current_path, "folder"))
        
        self.context_menu.add_command(
            label="Novo Arquivo", 
            command=lambda: self.create_new_item(current_path, "file"))
        
        if self.selected_item:
            self.context_menu.add_separator()
            self.context_menu.add_command(
                label="Copiar Caminho", 
                command=lambda: self.copy_to_clipboard(self.selected_item))
        
        # Mostra o menu na posição do clique
        self.context_menu.tk_popup(event.x_root, event.y_root)
    
    def open_item(self, item_path):
        path = Path(item_path)
        if path.is_dir():
            self.navigate_to(path)
        elif self.is_supported_archive(path):
            self.navigate_to(path)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o arquivo: {str(e)}")
    
    def open_in_terminal(self, item_path, terminal_type='powershell'):
        path = Path(item_path)
        if path.is_dir():
            try:
                if terminal_type == 'powershell':
                    subprocess.Popen(f'start powershell -NoExit -Command "Set-Location -Path \'{path}\'"', shell=True)
                else:  # cmd
                    subprocess.Popen(f'start cmd /K "cd /d \"{path}\""', shell=True)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o terminal: {str(e)}")
    
    def open_in_notepad(self, item_path):
        path = Path(item_path)
        if path.is_file():
            try:
                subprocess.Popen(f"notepad.exe '{path}'", shell=True)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir no Bloco de Notas: {str(e)}")
    
    def rename_item(self, item_path):
        path = Path(item_path)
        parent = path.parent
        
        dialog = ctk.CTkInputDialog(
            text=f"Digite o novo nome para {path.name}:",
            title="Renomear")
        
        new_name = dialog.get_input()
        
        if new_name and new_name != path.name:
            try:
                # Desativa o observer temporariamente
                if self.observer is not None and self.observer.is_alive():
                    self.observer.unschedule_all()
                
                new_path = parent / new_name
                path.rename(new_path)
                
                # Reativa o observer após um pequeno delay
                self.after(1000, self.reactivate_observer)
                
                self.navigate_to(parent)  # Atualiza a visualização
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível renomear: {str(e)}")
                # Reativa o observer em caso de erro
                self.after(1000, self.reactivate_observer)
    
    def move_to_trash(self, item_path):
        try:
            # Desativa o observer temporariamente
            if self.observer is not None and self.observer.is_alive():
                self.observer.unschedule_all()
            
            # Usando a shell do Windows para mover para a lixeira
            shell = Dispatch("Shell.Application")
            shell.Namespace(0).ParseName(str(Path(item_path).absolute())).InvokeVerb("delete")
            
            # Reativa o observer após um pequeno delay
            self.after(1000, self.reactivate_observer)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível mover para a lixeira: {str(e)}")
            self.reactivate_observer()
    
    def create_new_item(self, current_path, item_type):
        dialog = ctk.CTkInputDialog(
            text=f"Digite o nome do novo {'arquivo' if item_type == 'file' else 'pasta'}:",
            title=f"Novo {'Arquivo' if item_type == 'file' else 'Pasta'}")
        
        name = dialog.get_input()
        if name:
            try:
                # Desativa o observer temporariamente
                if self.observer is not None and self.observer.is_alive():
                    self.observer.unschedule_all()
                
                new_path = current_path / name
                if item_type == "folder":
                    new_path.mkdir(exist_ok=False)
                else:
                    new_path.touch(exist_ok=False)

                # Reativa o observer após um pequeno delay
                self.after(1000, self.reactivate_observer)
                self.navigate_to(current_path)  # Atualiza a visualização
            except FileExistsError:
                messagebox.showerror("Erro", f"Já existe um item com o nome '{name}'.")
                self.reactivate_observer()
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível criar o item: {str(e)}")
                self.reactivate_observer()
    
    def copy_to_clipboard(self, item_path):
        self.clipboard_clear()
        self.clipboard_append(str(Path(item_path).absolute()))
        self.update()  # Necessário para o clipboard funcionar
    
    def copy_selected_item(self):
        if self.selected_item:
            # Desativa o observer temporariamente
            if self.observer is not None and self.observer.is_alive():
                self.observer.unschedule_all()
            
            self.clipboard["items"] = {self.selected_item}
            self.clipboard["operation"] = "copy"
            self.copy_to_clipboard(self.selected_item)
            
            # Reativa o observer após um pequeno delay
            self.after(1000, self.reactivate_observer)
    
    def cut_selected_item(self):
        if self.selected_item:
            # Desativa o observer temporariamente
            if self.observer is not None and self.observer.is_alive():
                self.observer.unschedule_all()
            
            self.clipboard["items"] = {self.selected_item}
            self.clipboard["operation"] = "move"
            self.copy_to_clipboard(self.selected_item)
            
            # Reativa o observer após um pequeno delay
            self.after(1000, self.reactivate_observer)
    
    def paste_item(self):
        if not self.clipboard["items"] or not self.clipboard["operation"]:
            return
        
        current_path = Path(self.address_bar.get())
        try:
            # Desativa o observer temporariamente
            if self.observer is not None and self.observer.is_alive():
                self.observer.unschedule_all()
            
            for item_path in self.clipboard["items"]:
                source = Path(item_path)
                destination = current_path / source.name
                
                if self.clipboard["operation"] == "copy":
                    if source.is_dir():
                        shutil.copytree(source, destination)
                    else:
                        shutil.copy2(source, destination)
                else:  # move
                    shutil.move(source, destination)
            
            # Se foi uma operação de mover, limpa a área de transferência
            if self.clipboard["operation"] == "move":
                self.clipboard["items"].clear()
                self.clipboard["operation"] = None
            
            # Reativa o observer após um pequeno delay
            self.after(1000, self.reactivate_observer)
            
            # Atualiza a visualização
            self.navigate_to(current_path)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível {self.clipboard['operation']} o item: {str(e)}")
            # Reativa o observer em caso de erro
            self.after(1000, self.reactivate_observer)
    
    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.log(size_bytes, 1024))
        # Ensure we don't go out of bounds for units
        if i >= len(units):
             i = len(units) - 1
        return f"{size_bytes / (1024 ** i):.2f} {units[i]}"
    
    def calculate_file_hashes(self, file_path):
        """Calculates SHA256 and MD5 hashes of a file."""
        sha256_hash = hashlib.sha256()
        md5_hash = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # Read and update hash string value in blocks of 4K
                for byte_block in iter(lambda: f.read(4096),b""):
                    sha256_hash.update(byte_block)
                    md5_hash.update(byte_block)
            return sha256_hash.hexdigest(), md5_hash.hexdigest()
        except Exception as e:
            # print(f"Error calculating hashes for {file_path}: {e}") # Keep for debugging
            return None, None

    def show_properties(self, item_path, is_archive_member=False, member_info=None):
        """Mostra uma janela com as propriedades do arquivo/pasta"""
        path = Path(item_path)
        dialog = ctk.CTkToplevel(self)
        dialog.title("Propriedades")
        dialog.transient(self)
        dialog.lift()
        dialog.resizable(False, False)
        dialog.geometry("500x400")
        
        # Frame principal
        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Cabeçalho
        header_frame = ctk.CTkFrame(frame)
        header_frame.pack(fill="x", padx=10, pady=10)
        
        icon = self.get_file_icon(path)
        if is_archive_member:
            name = Path(member_info['member_path']).name # Get just the name for display
        else:
            name = path.name
        
        ctk.CTkLabel(header_frame, text=f"{icon} {name}", font=("Arial", 14, "bold")).pack(anchor="w")
        
        # Frame de conteúdo
        content_frame = ctk.CTkFrame(frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Informações
        info_text = tk.Text(content_frame, wrap="word", borderwidth=0, highlightthickness=0,
                           bg="#333" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
                           fg="#FFF" if ctk.get_appearance_mode() == "Dark" else "#000")
        info_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Adiciona as informações ao texto
        # Add full name
        if is_archive_member:
            full_name = member_info['member_path']
        else:
            full_name = path.name
        info_text.insert("end", f"Nome: {full_name}\n")

        info_text.insert("end", f"Tipo: {'Pasta' if path.is_dir() and not is_archive_member else 'Arquivo'}\n") # Differentiate type

        if is_archive_member:
            info_text.insert("end", f"Localização do arquivo: {member_info['archive_path']}\n")
            info_text.insert("end", f"Caminho dentro do arquivo: {member_info['member_path']}\n")
        else:
            info_text.insert("end", f"Localização: {path.parent}\n")
            info_text.insert("end", f"Caminho completo: {path.absolute()}\n")
        
        # For files or archive members, show size
        if not path.is_dir() or is_archive_member:
            try:
                if is_archive_member:
                    # Size is included in member_info from get_archive_members
                    size_bytes = member_info.get('size', 0)
                else:
                    size_bytes = path.stat().st_size
                
                info_text.insert("end", f"Tamanho: {self.convert_size(size_bytes)}\n")
            except Exception as e:
                info_text.insert("end", f"Tamanho: Não disponível\n")
        elif path.is_dir() and not is_archive_member:
            # For folders, calculate size and display
            info_text.insert("end", "Tamanho: Calculando...\n")
            # Create a temporary tag to identify this size line
            size_tag = f"size_{id(info_text)}"
            info_text.tag_add(size_tag, "end-2l", "end-1l") # Tag the "Tamanho: Calculando..." line

            def update_size_text(calculated_size):
                 size_str = self.convert_size(calculated_size)
                 # Remove the old line and insert the new one
                 try:
                     # Enable text widget to allow update
                     info_text.configure(state="normal")

                     # Find the start and end of the tagged line
                     start = info_text.tag_ranges(size_tag)[0]
                     end = info_text.tag_ranges(size_tag)[1]
                     info_text.delete(start, end)
                     info_text.insert(start, f"Tamanho: {size_str}\n")
                 except Exception as update_e:
                      # Fallback if tag somehow fails or update causes error
                      print(f"Error updating size text: {update_e}") # Log error for debugging
                      try:
                           # Try to just append if update fails
                           info_text.insert("end", f"Tamanho: {size_str} (Erro na atualização)\n")
                      except:
                           pass # Give up if even appending fails
                 finally:
                     # Disable text widget again
                     info_text.configure(state="disabled")


            # Calculate folder size in a separate thread
            threading.Thread(target=lambda: self.after(0, update_size_text, self.calculate_folder_size_sync(path))).start()


        # Add hash information for .exe files - Keep this as requested earlier
        if path.is_file() and path.suffix.lower() == '.exe' and not is_archive_member:
            sha256_hash, md5_hash = self.calculate_file_hashes(path)
            if sha256_hash and md5_hash:
                info_text.insert("end", f"SHA256: {sha256_hash}\n")
                info_text.insert("end", f"MD5: {md5_hash}\n")
        
        # Data de criação e modificação
        try:
            if not is_archive_member:
                created = datetime.datetime.fromtimestamp(path.stat().st_ctime)
                modified = datetime.datetime.fromtimestamp(path.stat().st_mtime)
                
                info_text.insert("end", f"Criado em: {created.strftime('%d/%m/%Y %H:%M:%S')}\n")
                info_text.insert("end", f"Modificado em: {modified.strftime('%d/%m/%Y %H:%M:%S')}\n")
                # For folders, display total items count
                if path.is_dir() and not is_archive_member:
                     info_text.insert("end", f"Quantia total de itens: {len(list(path.rglob('*')))}\n")

        except Exception as e:
            info_text.insert("end", "Datas: Não disponíveis\n")
        
        # Permissões
        try:
            if not is_archive_member:
                mode = path.stat().st_mode
                perms = []
                perms.append('R' if mode & 0o400 else '-')
                perms.append('W' if mode & 0o200 else '-')
                perms.append('X' if mode & 0o100 else '-')
                info_text.insert("end", f"Permissões: {''.join(perms)}\n")
        except Exception as e:
            info_text.insert("end", "Permissões: Não disponíveis\n")
        
        info_text.configure(state="disabled")
        
        # Botão de fechar
        ctk.CTkButton(frame, text="Fechar", command=dialog.destroy).pack(pady=10)

    def on_close(self):
        """Método chamado quando a janela é fechada"""
        if self.observer is not None and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.destroy()

    def calculate_folder_size_sync(self, folder_path):
        """Calculates the total size of a folder and its contents synchronously."""
        total_size = 0
        if not folder_path.is_dir():
            return total_size
        try:
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    total_size += self.calculate_folder_size_sync(Path(entry.path))
        except PermissionError:
            # Handle cases where access to a directory is denied
            pass # Or log a warning
        except Exception as e:
            print(f"Error calculating size for {folder_path}: {e}") # Keep for debugging
            return 0 # Return 0 on other errors
        return total_size


if __name__ == "__main__":
    # Verifica se foi passado um caminho como argumento
    initial_path = None
    if len(sys.argv) > 1:
        initial_path = ''.join(sys.argv[1:])
        if initial_path == '~':
            initial_path = os.path.expanduser("~")
        ok = os.path.isdir(initial_path)
        if not ok:
            print(f'Ocorreu um erro ao entrar em {initial_path}')
            exit()

    app = FileManager(initial_path)
    app.protocol("WM_DELETE_WINDOW", app.on_close) 
    app.mainloop()
