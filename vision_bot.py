import requests
import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, Label, Button, Text, Frame, Scrollbar, Canvas, messagebox, Checkbutton
from PIL import Image, ImageTk
import os
from scipy.stats import entropy
import subprocess
import threading
import time
import pandas as pd
from datetime import datetime
import logging
import shutil

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#ffffe0", relief="solid", borderwidth=1,
                         font=("Arial", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class AnaliseAnomaliasGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Análise de Anomalias em Imagens/Vídeos")
        self.root.state('zoomed')
        self.root.configure(bg="#f0f0f0")

        self.cap = None
        self.stop_flag = False
        self.frame = None
        self.video_path = None
        self.image_path = None
        self.video_thread = None
        self.is_analyzing = False
        self.text_resultados = None
        self.test_mode = False

        logging.basicConfig(filename='anomalias_log.txt', level=logging.ERROR,
                            format='%(asctime)s - %(levelname)s - %(message)s')

        self.edge_density = tk.DoubleVar(value=0.1)
        self.laplacian_var = tk.DoubleVar(value=100)
        self.angle_tolerance = tk.DoubleVar(value=15)
        self.color_variance = tk.DoubleVar(value=100)
        self.entropy_threshold = tk.DoubleVar(value=2.0)
        self.brightness_threshold = tk.DoubleVar(value=30)
        self.frame_interval = tk.DoubleVar(value=10.0)
        self.frame_skip = 5

        self.analyze_edges = tk.BooleanVar(value=True)
        self.analyze_blur = tk.BooleanVar(value=True)
        self.analyze_alignment = tk.BooleanVar(value=True)
        self.analyze_colors = tk.BooleanVar(value=True)
        self.analyze_objects = tk.BooleanVar(value=True)
        self.analyze_brightness = tk.BooleanVar(value=True)

        self.last_anomaly_time = {}
        self.anomaly_frames = []
        self.anomaly_metrics = {}

        self.output_folder = "anomalias_frames"
        os.makedirs(self.output_folder, exist_ok=True)

        try:
            self.setup_ui()
        except Exception as e:
            logging.error(f"Erro ao configurar a GUI: {e}")
            raise

    def setup_ui(self):
        self.api_url="https://mdvr02.avansat.com.br:22056"
        self.api_url_live="https://mdvr02.avansat.com.br:22060"
        self.usuario="admin"
        self.senha="Avs$2023"
        #self.api_url="http://mdvr.avansat.com.br:12056"
        #self.usuario="admin"
        #self.senha="NTAvansat"

        self.chave = ""
        self.textBtnLiveServer = tk.StringVar()
        self.textBtnLiveServer.set("Carregar Live Servidor")
        self.running = False
        self.inLoop = False
        self.ffmpeg_proc = None
        self.ffmpeg_path = self._resolve_ffmpeg_path()
        self.frame_count = 0
        self.max_saved_frames = 1
        self.frames_dir = "./frames_capturados"
        # Cria diretório se não existir
        os.makedirs(self.frames_dir, exist_ok=True)

        self.main_frame = Frame(self.root, bg="#f0f0f0")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.image_frame = Frame(self.main_frame, bg="#f0f0f0")
        self.image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.label_imagem = Label(self.image_frame, bg="#f0f0f0", text="Carregue uma imagem ou vídeo")
        self.label_imagem.pack(fill=tk.BOTH, expand=True)

        self.control_frame = Frame(self.main_frame, bg="#f0f0f0", width=400)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        self.control_frame.pack_propagate(False)

        self.threshold_frame = Frame(self.control_frame, bg="#f0f0f0")
        self.threshold_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = Canvas(self.threshold_frame, bg="#f0f0f0")
        self.scrollbar = Scrollbar(self.threshold_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = Frame(self.canvas, bg="#f0f0f0")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.bind_mousewheel()

        self.selection_frame = Frame(self.scrollable_frame, bg="#f0f0f0")
        self.selection_frame.pack(fill=tk.X, pady=1)
        Label(self.selection_frame, text="Selecionar Análises:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(anchor='w')
        
        Checkbutton(self.selection_frame, text="Bordas", variable=self.analyze_edges, bg="#f0f0f0").pack(anchor='e', side=tk.LEFT)
        Checkbutton(self.selection_frame, text="Cores Sólidas", variable=self.analyze_colors, bg="#f0f0f0").pack(anchor='w', side=tk.RIGHT)
        self.selection_frame2 = Frame(self.scrollable_frame, bg="#f0f0f0")
        self.selection_frame2.pack(fill=tk.X, pady=1)
        Checkbutton(self.selection_frame2, text="Embaçamento", variable=self.analyze_blur, bg="#f0f0f0").pack(anchor='e', side=tk.LEFT)
        Checkbutton(self.selection_frame2, text="Ausência de Objetos", variable=self.analyze_objects, bg="#f0f0f0").pack(anchor='w', side=tk.RIGHT)
        self.selection_frame3 = Frame(self.scrollable_frame, bg="#f0f0f0")
        self.selection_frame3.pack(fill=tk.X, pady=1)
        Checkbutton(self.selection_frame3, text="Alinhamento", variable=self.analyze_alignment, bg="#f0f0f0").pack(anchor='e', side=tk.LEFT)
        Checkbutton(self.selection_frame3, text="Brilho", variable=self.analyze_brightness, bg="#f0f0f0").pack(anchor='w', side=tk.RIGHT)
        self.create_threshold_controls()

        results_frame = Frame(self.control_frame, bg="#f0f0f0")
        results_frame.pack(pady=10, fill=tk.X)
        
        self.text_resultados = Text(results_frame, height=11, width=50, wrap=tk.WORD)
        scrollbar_text = Scrollbar(results_frame, orient=tk.VERTICAL, command=self.text_resultados.yview)
        self.text_resultados.config(yscrollcommand=scrollbar_text.set)
        
        self.text_resultados.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_text.pack(side=tk.RIGHT, fill=tk.Y)

        self.button_frame = Frame(self.control_frame, bg="#f0f0f0")
        self.button_frame.pack(fill=tk.X, pady=10)

        Button(self.button_frame, text="Carregar Imagem", command=self.carregar_imagem, 
               bg="#4CAF50", fg="white", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)
        Button(self.button_frame, text="Carregar Vídeo", command=self.carregar_video, 
               bg="#4CAF50", fg="white", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)
        Button(self.button_frame, text='Spam?', textvariable=self.textBtnLiveServer, command=self.command_cargaServer, 
               bg="#3A694F", fg="white", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)
        Button(self.button_frame, text="Analisar", command=self.analisar,
               bg="#2196F3", fg="white", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)
        Button(self.button_frame, text="Parar", command=lambda: self.parar(True),
               bg="#F44336", fg="white", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)
        Button(self.button_frame, text="Testar Limiares", command=self.toggle_test_mode,
               bg="#FFC107", fg="black", width=12).pack(side=tk.TOP, padx=5, pady=2, fill=tk.X)

    def _resolve_ffmpeg_path(self):
        preferred = ["ffmpeg", "ffmpeg.exe"]
        if os.name == "nt":
            preferred = ["ffmpeg.exe", "ffmpeg"]
        for candidate in preferred:
            path = shutil.which(candidate)
            if path:
                return path
        return preferred[0]

    def _terminate_ffmpeg(self):
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            try:
                self.ffmpeg_proc.kill()
            except Exception:
                pass
        self.ffmpeg_proc = None

    def _append_result(self, message):
        if self.text_resultados:
            self.text_resultados.insert(tk.END, message)
            self.text_resultados.see(tk.END)

    def _connect_stream(self):
        if not self.url_stream:
            return False
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", self.url_stream,
                "-f", "mjpeg",
                "-q:v", "5",
                "-r", "5",
                "-"
            ]
            self.ffmpeg_proc = subprocess.Popen(
                cmd,
                bufsize=10 ** 8,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            return True
        except FileNotFoundError:
            self._append_result("\nErro: FFmpeg não encontrado. Verifique a instalação.")
            return False
        except Exception as exc:
            logging.error("Erro ao iniciar FFmpeg", exc_info=True)
            self._append_result(f"\nErro ao iniciar FFmpeg: {exc}")
            return False

    def _read_stream_frame(self):
        if not self.ffmpeg_proc or not self.ffmpeg_proc.stdout:
            return

        buffer = b""
        while self.running:
            try:
                chunk = self.ffmpeg_proc.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9")
                if start != -1 and end != -1 and end > start:
                    jpg = buffer[start:end + 2]
                    buffer = buffer[end + 2:]
                    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        self.frame_count += 1
                        self.frame = frame
                        self.exibir_frame(frame)
                        return
            except Exception as exc:
                logging.error("Erro ao ler frame do stream", exc_info=True)
                self._append_result(f"\nErro na leitura do stream: {exc}")
                break

    def stream_loop(self):
        tentativa = 0
        self._terminate_ffmpeg()
        while self.running:
            tentativa += 1
            if not self._connect_stream():
                if tentativa > 1:
                    break
                time.sleep(1)
                continue
            self._read_stream_frame()
            if self.frame is not None:
                break
            if tentativa > 1:
                break
        self.running = False
        self._terminate_ffmpeg()

    def open_live_video(self, device, canal):
        try:
            self.parar(False)
            self.frame = None
            self.url_stream = self._build_live_stream_url(device, canal)
            self.running = True
            self.frame_count = 0
            self.stream_loop()

            if self.frame is None:
                self._append_result("\nSem frame!")
                return False

            self.root.update_idletasks()
            self._append_result("\nFrame carregado!")
            self.anomaly_frames = []
            self.last_anomaly_time = {}
            self.image_path = f"{device}_{canal}.jpg"
            self.analisar()
            return True
        except Exception as exc:
            logging.error("Erro ao carregar vídeo", exc_info=True)
            self._append_result(f"\nFalha ao carregar vídeo: {exc}")
            return False
        finally:
            self.running = False
            self._terminate_ffmpeg()

    def _build_live_stream_url(self, device, canal):
        try:
            url_live = (
                f"{self.api_url.rstrip('/')}/api/v1/basic/live/video"
                f"?key={self.chave}&chl={canal}&audio=0&st=0&port=17891&terid={device}"
            )
            response = requests.get(url_live)
            response.raise_for_status()
            data = response.json()
            if data.get("errorcode") == 200:
                url = data["data"]["url"]
                index = url.find("/live")
                return f"{self.api_url_live.rstrip('/')}{url[index:]}"
            raise RuntimeError(f"Erro da API: {data.get('errorcode')}")
        except Exception as exc:
            raise RuntimeError(f"Erro ao obter URL de vídeo: {exc}") from exc

    def _fetch_devices_by_group(self):
        try:
            url_total = f"{self.api_url.rstrip('/')}/api/v1/basic/devices?key={self.chave}"
            r_total = requests.get(url_total)
            r_total.raise_for_status()
            dispositivos_data = r_total.json()
            self.dispositivos = dispositivos_data.get("data", [])
            total_dispositivos = len(self.dispositivos)

            url_online = f"{self.api_url.rstrip('/')}/api/v1/basic/state/now"
            payload = {"key": self.chave, "terid": []}
            r_online = requests.post(url_online, json=payload)
            r_online.raise_for_status()
            online_data = r_online.json()
            self.online_terids = {d["terid"] for d in online_data.get("data", [])}

            grupos = {}
            for dispositivo in self.dispositivos:
                if dispositivo["terid"] in self.online_terids:
                    nome_grupo = dispositivo.get("groupname", "(Sem Grupo)")
                    canais = dispositivo.get("channelcount", 0)
                    linha = (
                        f"{dispositivo['terid']} - {dispositivo.get('carlicence', '(sem placa)')} - {canais} canais"
                    )
                    grupos.setdefault(nome_grupo, []).append(linha)

            total_online = sum(len(lista) for lista in grupos.values())
            return grupos, total_online, total_dispositivos
        except Exception as exc:
            raise RuntimeError(f"Erro ao agrupar dispositivos por grupo: {exc}") from exc

    def _authenticate_streamax(self, api_url, usuario, senha):
        try:
            url = f"{api_url.rstrip('/')}/api/v1/basic/key?username={usuario}&password={senha}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("errorcode") == 200:
                return data["data"]["key"]
            raise RuntimeError(f"Erro da API: {data.get('errorcode')}")
        except Exception as exc:
            raise RuntimeError(f"Falha na autenticação: {exc}") from exc

    def create_threshold_controls(self):
        controls = [
            ("Limiar Bordas:", self.edge_density, 0.01, 0, 1, 
             "Densidade de bordas para detecção (0-1). Aumentar reduz falsos positivos."),
            ("Limiar Embaçamento:", self.laplacian_var, 10, 0, 500, 
             "Variância para detecção de embaçamento. Aumentar exige maior embaçamento."),
            ("Tolerância Ângulo (°):", self.angle_tolerance, 1, 0, 45, 
             "Tolerância para alinhamento (0-45°). Aumentar permite maior desalinhamento."),
            ("Limiar Cor Sólida:", self.color_variance, 10, 0, 500, 
             "Variância de cor para cores sólidas. Aumentar reduz falsos positivos."),
            ("Limiar Complexidade:", self.entropy_threshold, 0.1, 0, 5, 
             "Entropia para ausência de objetos. Aumentar exige menor complexidade."),
            ("Limiar Brilho:", self.brightness_threshold, 5, 0, 255, 
             "Intensidade para imagens escuras (0-255). Aumentar exige maior escuridão."),
            ("Intervalo Frames (s):", self.frame_interval, 1.0, 1.0, 30.0, 
             "Intervalo entre salvamentos de frames (1-30s). Aumentar reduz redundâncias.")
        ]
        
        for label_text, var, step, min_val, max_val, tooltip_text in controls:
            control_frame = Frame(self.scrollable_frame, bg="#f0f0f0")
            control_frame.pack(fill=tk.X, pady=5)
            
            label = Label(control_frame, text=label_text, bg="#f0f0f0", font=("Arial", 9), width=20, anchor='w')
            label.pack(side=tk.LEFT)
            ToolTip(label, tooltip_text)
            
            minus_button = Button(control_frame, text="-", width=3, bg="#ff6b6b", fg="white",
                                  command=lambda v=var, s=step, min_v=min_val: self.decrease_value(v, s, min_v))
            minus_button.pack(side=tk.LEFT, padx=2)
            ToolTip(minus_button, tooltip_text)
            
            value_label = Label(control_frame, textvariable=var, bg="white", width=8, relief="sunken")
            value_label.pack(side=tk.LEFT, padx=5)
            ToolTip(value_label, tooltip_text)
            
            plus_button = Button(control_frame, text="+", width=3, bg="#51cf66", fg="white",
                                 command=lambda v=var, s=step, max_v=max_val: self.increase_value(v, s, max_v))
            plus_button.pack(side=tk.LEFT, padx=2)
            ToolTip(plus_button, tooltip_text)
    
    def increase_value(self, var, step, max_val):
        current = var.get()
        new_val = min(current + step, max_val)
        var.set(round(new_val, 1))
        if self.test_mode and self.frame is not None and self.image_path and os.path.exists(self.image_path):
            self.reload_and_analyze()

    def decrease_value(self, var, step, min_val):
        current = var.get()
        new_val = max(current - step, min_val)
        var.set(round(new_val, 1))
        if self.test_mode and self.frame is not None and self.image_path and os.path.exists(self.image_path):
            self.reload_and_analyze()

    def bind_mousewheel(self):
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_to_mousewheel(event):
            self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            self.canvas.unbind_all("<MouseWheel>")
        
        self.canvas.bind('<Enter>', _bind_to_mousewheel)
        self.canvas.bind('<Leave>', _unbind_from_mousewheel)

    def toggle_test_mode(self):
        if self.frame is None or (self.image_path is None and self.video_path is None):
            messagebox.showwarning("Aviso", "Carregue uma imagem antes de testar limiares")
            return
        self.test_mode = not self.test_mode
        if self.text_resultados:
            self.text_resultados.delete(1.0, tk.END)
            self.text_resultados.insert(tk.END, f"Modo de teste {'ativado' if self.test_mode else 'desativado'}\n")
        if self.test_mode and self.frame is not None and self.image_path and os.path.exists(self.image_path):
            self.reload_and_analyze()

    def reload_and_analyze(self):
        try:
            self.frame = cv2.imread(self.image_path)
            if self.frame is None:
                raise ValueError(f"Não foi possível recarregar a imagem de {self.image_path}")
            self.analisar_imagem()
        except Exception as e:
            logging.error(f"Erro ao recarregar e analisar imagem: {e}")
            messagebox.showerror("Erro", f"Erro ao recarregar imagem: {str(e)}")

    def carregar_imagem(self):
        try:
            self.parar(True)
            self.image_path = filedialog.askopenfilename(
                title="Selecionar Imagem",
                filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.tiff")]
            )
            if self.image_path:
                self.image_path = os.path.normpath(self.image_path)  # Normaliza o caminho
                self.frame = cv2.imread(self.image_path)
                if self.frame is None:
                    raise ValueError("Não foi possível carregar a imagem")
                
                self.video_path = None
                self.exibir_frame(self.frame)
                if self.text_resultados:
                    self.text_resultados.delete(1.0, tk.END)
                    self.text_resultados.insert(tk.END, f"Imagem carregada: {os.path.basename(self.image_path)}\n")
                self.anomaly_frames = []
                self.last_anomaly_time = {}
        except Exception as e:
            logging.error(f"Erro ao carregar imagem: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar imagem: {str(e)}")
            
    def thread_cargaServer(self):
        self.threadServer = threading.Thread(target=self.carregar_server, daemon=True)
        self.threadServer.start()
        
    def command_cargaServer(self):
        if self.inLoop:
            self.textBtnLiveServer.set("Aguarde...")
            self.inLoop=False
        else:
            self.thread_cargaServer()
            
    def carregar_server(self):
        self.online_terids = []
        try:
            if self.text_resultados:
                self.text_resultados.delete(1.0, tk.END)
            self._append_result("Conectando servidor...\n")
            self.chave = self._authenticate_streamax(self.api_url, self.usuario, self.senha)
            if not self.chave:
                self._append_result("Falha na conexão\n")
                return

            self._append_result("Obtendo lista de devices...\n")
            grupos, total_online, total_dispositivos = self._fetch_devices_by_group()

            self._append_result(f"Total de dispositivos: {total_dispositivos}\n")
            self._append_result(f"Total online: {total_online}\n")

            if not grupos:
                self._append_result("Nenhum dispositivo online encontrado!\n")
                return

            self.textBtnLiveServer.set("Interromper Live")
            camera_atual = 0
            self.inLoop = True
            for dispositivo in self.dispositivos:
                if not self.inLoop:
                    self._append_result("Interrompido.")
                    break
                if dispositivo["terid"] in self.online_terids:
                    canais = dispositivo.get("channelcount", 0)
                    terid = dispositivo['terid']
                    carlicence = dispositivo['carlicence']
                    camera_atual += 1
                    perce = round(camera_atual / len(self.online_terids) * 100, 0)
                    for canal in range(1, canais):
                        if not self.inLoop:
                            self._append_result("Interrompido.")
                            break
                        self.image_path = None
                        self._append_result(f"\n{carlicence} / {canal}...")
                        self.root.title(f"Procurando Câmeras...{int(perce)}%")
                        self.root.update()
                        self.open_live_video(terid, canal)
                else:
                    self.root.update_idletasks()
            self.inLoop = False
            self.textBtnLiveServer.set("Carregar Live Servidor")
            self.root.title("Análise de Anomalias em Imagens/Vídeos")

        except Exception as e:
            logging.error(f"Erro ao carregar servidor: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar servidor: {str(e)}")

    def carregar_video(self):
        try:
            self.parar(True)
            self.video_path = filedialog.askopenfilename(
                title="Selecionar Vídeo",
                filetypes=[("Vídeos", "*.mp4 *.avi *.mov *.mkv *.wmv")]
            )
            if self.video_path:
                self.video_path = os.path.normpath(self.video_path)  # Normaliza o caminho
                self.cap = cv2.VideoCapture(self.video_path)
                if not self.cap.isOpened():
                    raise ValueError("Erro ao abrir o vídeo")
                
                ret, self.frame = self.cap.read()
                if not ret:
                    raise ValueError("Não foi possível ler o primeiro frame do vídeo")
                
                self.image_path = None
                self.exibir_frame(self.frame)
                if self.text_resultados:
                    self.text_resultados.delete(1.0, tk.END)
                    self.text_resultados.insert(tk.END, f"Vídeo carregado: {os.path.basename(self.video_path)}\n")
                self.anomaly_frames = []
                self.last_anomaly_time = {}
        except Exception as e:
            logging.error(f"Erro ao carregar vídeo: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar vídeo: {str(e)}")
            if self.cap:
                self.cap.release()
                self.cap = None

    def exibir_frame(self, frame):
        try:
            if frame is None:
                return
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = frame.shape[:2]
            
            #self.root.update_idletasks()
            max_width = max(self.image_frame.winfo_width() - 20, 400)
            max_height = max(self.image_frame.winfo_height() - 20, 300)
            
            ratio = min(max_width / width, max_height / height)
            ratio= 1.2
            #messagebox.showinfo("ratio", ratio)
            
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            
            frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
            img = Image.fromarray(frame_resized)
            imgtk = ImageTk.PhotoImage(image=img)
            
            self.label_imagem.imgtk = imgtk
            self.label_imagem.configure(image=imgtk, text="")
        except Exception as e:
            logging.error(f"Erro ao exibir frame: {e}")

    def save_anomaly_frame(self, frame, anomaly_type, frame_count=None, metrics=None):
        current_time = time.time()
        if anomaly_type in self.last_anomaly_time:
            if current_time - self.last_anomaly_time[anomaly_type] < self.frame_interval.get():
                return
        self.last_anomaly_time[anomaly_type] = current_time

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_name = os.path.basename(self.image_path if self.image_path else self.video_path) if self.image_path or self.video_path else "unnamed_source"
        frame_filename = f"{anomaly_type.replace(' ', '_')}_{source_name}_{timestamp}.jpg"
        frame_path = os.path.join(self.output_folder, frame_filename)

        try:
            cv2.imwrite(frame_path, frame)
        except Exception as e:
            logging.error(f"Erro ao salvar frame: {e}")
            return

        anomaly_data = {
            'Anomalia': anomaly_type,
            'Timestamp': timestamp,
            'Caminho_Frame': frame_path,
            'Frame': frame_count if frame_count is not None else 'N/A',
            'Arquivo_Origem': source_name,
            'Limiar_Bordas': self.edge_density.get(),
            'Limiar_Embaçamento': self.laplacian_var.get(),
            'Tolerância_Ângulo': self.angle_tolerance.get(),
            'Limiar_Cor_Sólida': self.color_variance.get(),
            'Limiar_Complexidade': self.entropy_threshold.get(),
            'Limiar_Brilho': self.brightness_threshold.get(),
        }
        if metrics:
            anomaly_data.update(metrics)
        self.anomaly_frames.append(anomaly_data)

    def generate_excel_report(self):
        if not self.anomaly_frames:
            if self.text_resultados:
                self.text_resultados.insert(tk.END, "\nNenhum dado para gerar relatório Excel\n")
            return

        df = pd.DataFrame(self.anomaly_frames)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_name = os.path.basename(self.image_path if self.image_path else self.video_path) if self.image_path or self.video_path else "unnamed_source"
        excel_filename = f"relatorio_anomalias_{source_name}_{timestamp}.xlsx"
        excel_path = os.path.join(self.output_folder, excel_filename)

        try:
            df.to_excel(excel_path, index=False, engine='openpyxl')
            if self.text_resultados:
                self.text_resultados.insert(tk.END, f"\nRelatório salvo em: {excel_path}\n")
        except Exception as e:
            logging.error(f"Erro ao gerar relatório Excel: {e}")
            messagebox.showerror("Erro", f"Erro ao gerar relatório: {str(e)}")

    def analisar_bordas(self, frame):
        try:
            if not self.analyze_edges.get():
                return frame, [], {}
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, threshold1=100, threshold2=200)
            
            height, width = frame.shape[:2]
            cantos_bordas = [
                edges[0:height//2, 0:width//2],
                edges[0:height//2, width//2:width],
                edges[height//2:height, 0:width//2],
                edges[height//2:height, width//2:width]
            ]
            
            regioes = [
                ((0, 0), (width//2, height//2)),
                ((width//2, 0), (width, height//2)),
                ((0, height//2), (width//2, height)),
                ((width//2, height//2), (width, height))
            ]
            
            anomalias_bordas = []
            metrics = {}
            for i, edges_region in enumerate(cantos_bordas):
                if edges_region.size > 0:
                    edge_density_value = np.sum(edges_region) / (edges_region.size * 255)
                    metrics[f"Densidade_Bordas_Canto_{i+1}"] = round(edge_density_value, 4)
                    if edge_density_value > self.edge_density.get():
                        (x1, y1), (x2, y2) = regioes[i]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        anomalia = f"Canto {i+1} com muitas bordas"
                        anomalias_bordas.append(anomalia)
            
            return frame, anomalias_bordas, metrics
        except Exception as e:
            logging.error(f"Erro na análise de bordas: {e}")
            return frame, [], {}

    def analisar_embacamento(self, frame):
        try:
            if not self.analyze_blur.get():
                return frame, [], {}
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            gaussian = cv2.GaussianBlur(gray, (5, 5), 1.0)
            sharpened = cv2.addWeighted(gray, 1.5, gaussian, -0.5, 0)

            height, width = sharpened.shape
            regions = [
                sharpened[0:height//2, 0:width//2],
                sharpened[0:height//2, width//2:width],
                sharpened[height//2:height, 0:width//2],
                sharpened[height//2:height, width//2:width]
            ]
            laplacian_vars = [cv2.Laplacian(region, cv2.CV_64F).var() for region in regions]
            mean_laplacian_var = np.mean(laplacian_vars)

            sobel_x = cv2.Sobel(sharpened, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(sharpened, cv2.CV_64F, 0, 1, ksize=3)
            gradient_var = cv2.Laplacian(np.hypot(sobel_x, sobel_y), cv2.CV_64F).var()

            hist = cv2.calcHist([sharpened], [0], None, [256], [0, 256])
            hist = hist / hist.sum()
            hist = hist[hist > 0]
            image_entropy = entropy(hist) if len(hist) > 0 else 0

            window_size = 32
            mean_local_std = 0
            if height > window_size and width > window_size:
                local_std_values = []
                for i in range(0, height - window_size, window_size):
                    for j in range(0, width - window_size, window_size):
                        patch = sharpened[i:i+window_size, j:j+window_size]
                        local_std_values.append(np.std(patch))
                mean_local_std = np.mean(local_std_values) if local_std_values else 0
            else:
                mean_local_std = np.std(sharpened)

            mean_intensity = np.mean(sharpened)
            std_intensity = np.std(sharpened)
            visibility_coeff = std_intensity / mean_intensity if mean_intensity > 0 else 0

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            dark_channel = np.min(frame_rgb, axis=2)
            dark_channel_mean = np.mean(dark_channel)

            dynamic_threshold = self.laplacian_var.get() * 0.5
            is_blurry = (
                (mean_laplacian_var < dynamic_threshold) or
                (gradient_var < 50) or
                (mean_local_std < 10) or
                (visibility_coeff < 0.2) or
                (dark_channel_mean > 100 and image_entropy < 3.0)
            )

            metrics = {
                'Variância_Laplaciano': round(mean_laplacian_var, 2),
                'Variância_Gradiente': round(gradient_var, 2),
                'Entropia_Imagem': round(image_entropy, 2),
                'Desvio_Padrão_Local': round(mean_local_std, 2),
                'Coeficiente_Visibilidade': round(visibility_coeff, 2),
                'Média_Canal_Escuro': round(dark_channel_mean, 2)
            }

            if is_blurry:
                cv2.putText(frame, "Imagem Embacada", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
                return frame, ["Imagem embaçada detectada"], metrics
            
            return frame, [], metrics
        except Exception as e:
            logging.error(f"Erro na análise de embaçamento: {e}")
            return frame, [], {}

    def analisar_alinhamento(self, frame):
        try:
            if not self.analyze_alignment.get():
                return frame, [], {}
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, 
                                   minLineLength=50, maxLineGap=20)  # Ajustes sugeridos
            
            metrics = {}
            if lines is not None and len(lines) > 0:
                angulos = []
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if x2 != x1:
                        angulo = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                        angulos.append(abs(angulo))
                
                if angulos:
                    media_angulos = np.mean(angulos)
                    metrics['Média_Ângulos'] = round(media_angulos, 2)
                    tolerance = self.angle_tolerance.get()
                    if (abs(media_angulos - 0) > tolerance or 
                        abs(media_angulos - 90) > tolerance):
                        cv2.putText(frame, "Camera Desalinhada", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
                        # Desenhar linhas detectadas para depuração
                        for line in lines:
                            x1, y1, x2, y2 = line[0]
                            cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        return frame, ["Camera desalinhada detectada"], metrics
            
            return frame, [], metrics
        except Exception as e:
            logging.error(f"Erro na análise de alinhamento: {e}")
            return frame, [], {}

    def analisar_cores_solidas(self, frame):
        try:
            if not self.analyze_colors.get():
                return frame, [], {}
            
            variancia = np.var(frame, axis=(0, 1))
            metrics = {'Variância_Cor_B': round(variancia[0], 2),
                       'Variância_Cor_G': round(variancia[1], 2),
                       'Variância_Cor_R': round(variancia[2], 2)}
            
            if np.all(variancia < self.color_variance.get()):
                cv2.putText(frame, "Cor Sólida Detectada", (10, 90), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
                return frame, ["Imagem com cor sólida detectada"], metrics
            return frame, [], metrics
        except Exception as e:
            logging.error(f"Erro na análise de cores sólidas: {e}")
            return frame, [], {}

    def analisar_sem_objetos(self, frame):
        try:
            if not self.analyze_objects.get():
                return frame, [], {}
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist_normalized = hist.flatten()
            hist_normalized = hist_normalized / hist_normalized.sum()
            
            hist_normalized = hist_normalized[hist_normalized > 0]
            
            ent = 0
            if len(hist_normalized) > 0:
                ent = entropy(hist_normalized)
            
            metrics = {'Entropia_Histograma': round(ent, 2)}
            
            if ent < self.entropy_threshold.get():
                cv2.putText(frame, "Sem Objetos/Pessoas", (10, 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
                return frame, ["Sem objetos ou pessoas detectados"], metrics
            
            return frame, [], metrics
        except Exception as e:
            logging.error(f"Erro na análise de objetos: {e}")
            return frame, [], {}

    def analisar_brilho(self, frame):
        try:
            if not self.analyze_brightness.get():
                return frame, [], {}
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brilho_medio = np.mean(gray)
            metrics = {'Brilho_Médio': round(brilho_medio, 2)}
            
            if brilho_medio < self.brightness_threshold.get():
                cv2.putText(frame, "Imagem Escura", (10, 150), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
                return frame, ["Imagem excessivamente escura"], metrics
            return frame, [], metrics
        except Exception as e:
            logging.error(f"Erro na análise de brilho: {e}")
            return frame, [], {}

    def analisar(self):
        if self.frame is None and self.cap is None:
            messagebox.showwarning("Aviso", "Carregue uma imagem ou vídeo antes de analisar")
            return
        if self.is_analyzing and not self.test_mode:
            messagebox.showinfo("Info", "Análise já está em andamento")
            return
        
        self.stop_flag = False
        
        if self.cap is not None and not self.test_mode:
            self.video_thread = threading.Thread(target=self.analisar_video_thread)
            self.video_thread.daemon = True
            self.video_thread.start()
        else:
            self.analisar_imagem()

    def analisar_imagem(self):
        try:
            self.is_analyzing = True
            if self.frame is None or (not self.inLoop and self.image_path is None and self.video_path is None):
                raise ValueError("Nenhuma imagem ou frame válido carregado")
            
            frame = self.frame.copy()
            anomalias = []

            if self.analyze_edges.get():
                frame, bordas_anomalias, bordas_metrics = self.analisar_bordas(frame)
                for anomalia in bordas_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=bordas_metrics)
                anomalias.extend(bordas_anomalias)

            if self.analyze_blur.get():
                frame, embacamento_anomalias, embacamento_metrics = self.analisar_embacamento(frame)
                for anomalia in embacamento_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=embacamento_metrics)
                anomalias.extend(embacamento_anomalias)

            if self.analyze_alignment.get():
                frame, alinhamento_anomalias, alinhamento_metrics = self.analisar_alinhamento(frame)
                for anomalia in alinhamento_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=alinhamento_metrics)
                anomalias.extend(alinhamento_anomalias)

            if self.analyze_colors.get():
                frame, cores_anomalias, cores_metrics = self.analisar_cores_solidas(frame)
                for anomalia in cores_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=cores_metrics)
                anomalias.extend(cores_anomalias)

            if self.analyze_objects.get():
                frame, objetos_anomalias, objetos_metrics = self.analisar_sem_objetos(frame)
                for anomalia in objetos_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=objetos_metrics)
                anomalias.extend(objetos_anomalias)

            if self.analyze_brightness.get():
                frame, brilho_anomalias, brilho_metrics = self.analisar_brilho(frame)
                for anomalia in brilho_anomalias:
                    self.save_anomaly_frame(frame, anomalia, metrics=brilho_metrics)
                anomalias.extend(brilho_anomalias)

            self.exibir_frame(frame)

            if self.text_resultados:
                self.text_resultados.delete(1.0, tk.END)
                source_name = os.path.basename(self.image_path if self.image_path else self.video_path) if self.image_path or self.video_path else "unnamed_source"
                self.text_resultados.insert(tk.END, f"{'Imagem' if self.image_path else 'Vídeo'}: {source_name}\n\n")
                if anomalias:
                    self.text_resultados.insert(tk.END, "Anomalias detectadas:\n")
                    for i, anomalia in enumerate(anomalias, 1):
                        self.text_resultados.insert(tk.END, f"{i}. {anomalia}\n")
                else:
                    self.text_resultados.insert(tk.END, "✅ Nenhuma anomalia detectada\n")
                if 'alinhamento_metrics' in locals() and 'Média_Ângulos' in alinhamento_metrics:
                    self.text_resultados.insert(tk.END, f"Ângulo Médio Detectado: {alinhamento_metrics['Média_Ângulos']}°\n")

            if not self.test_mode:
                self.generate_excel_report()
                
        except Exception as e:
            logging.error(f"Erro durante a análise de imagem: {e}")
            messagebox.showerror("Erro", f"Erro durante a análise: {str(e)}")
        finally:
            if not self.test_mode:
                self.is_analyzing = False

    def analisar_video_thread(self):
        try:
            self.is_analyzing = True
            frame_count = 0
            frame_index = 0
            
            while not self.stop_flag and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    self.root.after(0, lambda: self.text_resultados.insert(tk.END, "\nFim do vídeo\n") if self.text_resultados else None)
                    self.root.after(0, self.generate_excel_report)
                    break
                
                frame_count += 1
                if frame_count % self.frame_skip != 0:
                    continue
                frame_index += 1
                
                self.frame = frame.copy()
                anomalias = []

                if self.analyze_edges.get():
                    frame, bordas_anomalias, bordas_metrics = self.analisar_bordas(frame)
                    for anomalia in bordas_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, bordas_metrics)
                    anomalias.extend(bordas_anomalias)

                if self.analyze_blur.get():
                    frame, embacamento_anomalias, embacamento_metrics = self.analisar_embacamento(frame)
                    for anomalia in embacamento_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, embacamento_metrics)
                    anomalias.extend(embacamento_anomalias)

                if self.analyze_alignment.get():
                    frame, alinhamento_anomalias, alinhamento_metrics = self.analisar_alinhamento(frame)
                    for anomalia in alinhamento_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, alinhamento_metrics)
                    anomalias.extend(alinhamento_anomalias)

                if self.analyze_colors.get():
                    frame, cores_anomalias, cores_metrics = self.analisar_cores_solidas(frame)
                    for anomalia in cores_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, cores_metrics)
                    anomalias.extend(cores_anomalias)

                if self.analyze_objects.get():
                    frame, objetos_anomalias, objetos_metrics = self.analisar_sem_objetos(frame)
                    for anomalia in objetos_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, objetos_metrics)
                    anomalias.extend(objetos_anomalias)

                if self.analyze_brightness.get():
                    frame, brilho_anomalias, brilho_metrics = self.analisar_brilho(frame)
                    for anomalia in brilho_anomalias:
                        self.save_anomaly_frame(frame, anomalia, frame_index, brilho_metrics)
                    anomalias.extend(brilho_anomalias)

                self.root.after(0, lambda f=frame, a=anomalias, fc=frame_index: self.atualizar_gui_video(f, a, fc))
                
                time.sleep(0.033)
                
        except Exception as e:
            logging.error(f"Erro na análise de vídeo: {e}")
            self.root.after(0, lambda: messagebox.showerror("Erro", f"Erro na análise do vídeo: {str(e)}"))
        finally:
            self.is_analyzing = False
            self.root.after(0, self.generate_excel_report)

    def atualizar_gui_video(self, frame, anomalias, frame_count):
        try:
            self.exibir_frame(frame)
            
            if self.text_resultados:
                self.text_resultados.delete(1.0, tk.END)
                self.text_resultados.insert(tk.END, f"Vídeo: {os.path.basename(self.video_path)}\n")
                self.text_resultados.insert(tk.END, f"Frame: {frame_count}\n\n")
                
                if anomalias:
                    self.text_resultados.insert(tk.END, "Anomalias detectadas:\n")
                    for i, anomalia in enumerate(anomalias, 1):
                        self.text_resultados.insert(tk.END, f"{i}. {anomalia}\n")
                else:
                    self.text_resultados.insert(tk.END, "✅ Nenhuma anomalia detectada\n")
                
        except Exception as e:
            logging.error(f"Erro ao atualizar GUI: {e}")

    def parar(self, show_text):
        self.stop_flag = True
        self.is_analyzing = False
        self.test_mode = False
        
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join(timeout=1.0)
        
        self.frame = None
        if show_text:
            if self.text_resultados:
                try:
                    self.text_resultados.delete(1.0, tk.END)
                    self.text_resultados.insert(tk.END, "Análise parada\n")
                except tk.TclError:
                    pass
            self.generate_excel_report()

        self.anomaly_frames = []
        self.last_anomaly_time = {}

    def __del__(self):
        try:
            if self.is_analyzing or self.cap or self.video_thread:
                self.parar(True)
        except:
            pass

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = AnaliseAnomaliasGUI(root)
        
        def on_closing():
            app.parar(True)
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        root.mainloop()
    except Exception as e:
        logging.error(f"Erro ao iniciar a GUI: {e}")
        print(f"Erro ao iniciar a GUI: {e}")