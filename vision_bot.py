"""POC IA GPT - GUI para detecção de capacetes em vídeos com suporte à API GPT.

Este módulo fornece uma aplicação Tkinter capaz de carregar vídeos MP4, enviar
quadros amostrados para a API de visão do GPT e indicar, para cada quadro
analisado, se há uso adequado de capacete. O foco é oferecer uma base limpa e
organizada para experimentos com visão computacional assistida por IA.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cv2
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

try:
    RESAMPLING = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLING = Image.LANCZOS

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - depende de ambiente externo
    raise SystemExit(
        "A biblioteca 'openai' é necessária para executar este projeto. "
        "Instale-a com 'pip install openai'."
    ) from exc


# ---------------------------------------------------------------------------
# Configurações e estruturas auxiliares
# ---------------------------------------------------------------------------

LOG_FILE = Path("poc_ia_gpt.log")
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


@dataclass
class FrameDetection:
    """Estrutura que representa o resultado retornado pela API para um quadro."""

    frame_index: int
    timestamp_s: float
    helmet_detected: bool
    confidence: Optional[float]
    summary: str


class GPTHelmetDetector:
    """Cliente responsável por enviar quadros para a API GPT."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        if not api_key:
            raise ValueError("A chave de API do GPT não pode ser vazia.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def analyze_frame(self, image_bgr) -> FrameDetection:
        """Envia um quadro em formato BGR para análise pela API GPT."""
        success, buffer = cv2.imencode(".jpg", image_bgr)
        if not success:
            raise RuntimeError("Falha ao codificar o quadro em JPEG.")

        encoded_image = base64.b64encode(buffer).decode("utf-8")
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Você é um inspetor de segurança especialista em uso de "
                                "EPI. Analise a imagem fornecida e responda em JSON com "
                                "os campos 'helmet_detected' (true/false), "
                                "'confidence' (0-1) e 'summary' (texto curto)."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Observe atentamente a cena e indique se todas as pessoas "
                                "presentes usam capacete de segurança adequado."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_base64": encoded_image,
                        },
                    ],
                },
            ],
            max_output_tokens=200,
        )

        raw_text = response.output_text.strip()
        logging.debug("Resposta bruta do GPT: %s", raw_text)

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logging.error("Falha ao decodificar JSON da API: \n%s", raw_text)
            raise RuntimeError(
                "A API retornou um formato inesperado. Verifique os logs para mais detalhes."
            ) from exc

        helmet_detected = bool(payload.get("helmet_detected"))
        confidence = payload.get("confidence")
        summary = payload.get("summary") or "Sem descrição fornecida."

        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None

        return FrameDetection(
            frame_index=-1,
            timestamp_s=0.0,
            helmet_detected=helmet_detected,
            confidence=confidence_value,
            summary=summary,
        )


# ---------------------------------------------------------------------------
# Interface gráfica principal
# ---------------------------------------------------------------------------


class HelmetDetectionApp:
    """Aplicação Tkinter que conduz o fluxo de detecção de capacetes."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("POC IA GPT - Detecção de Capacetes")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Estado interno
        self.video_path: Optional[Path] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.analysis_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.gpt_client: Optional[GPTHelmetDetector] = None
        self.frame_results: List[FrameDetection] = []
        self.frame_step = tk.IntVar(value=30)

        # Construção da interface
        self._build_layout()
        self._log("Bem-vindo! Carregue um vídeo MP4 e informe sua chave da API GPT.")

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        main_frame = tk.Frame(self.root, padx=12, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Área de exibição de vídeo
        video_frame = tk.LabelFrame(main_frame, text="Pré-visualização do Vídeo")
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.video_label = tk.Label(video_frame, text="Nenhum vídeo carregado", width=64, height=24)
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Painel de controle
        control_frame = tk.LabelFrame(main_frame, text="Controles")
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)

        tk.Label(control_frame, text="Chave API GPT:").pack(anchor=tk.W)
        self.api_key_entry = tk.Entry(control_frame, show="*", width=40)
        self.api_key_entry.pack(fill=tk.X, pady=(0, 8))
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            self.api_key_entry.insert(0, env_key)

        tk.Label(control_frame, text="Amostragem (quadros analisados):").pack(anchor=tk.W)
        tk.Spinbox(
            control_frame,
            from_=1,
            to=120,
            textvariable=self.frame_step,
            width=10,
        ).pack(anchor=tk.W, pady=(0, 12))

        tk.Button(control_frame, text="Carregar Vídeo", command=self.load_video).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="Iniciar Análise", command=self.start_analysis).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="Parar", command=self.stop_analysis).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="Exportar Relatório", command=self.export_report).pack(fill=tk.X, pady=8)

        tk.Label(control_frame, text="Log de Execução:").pack(anchor=tk.W)
        self.log_text = tk.Text(control_frame, height=16, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Utilidades de UI
    # ------------------------------------------------------------------
    def _log(self, message: str) -> None:
        logging.info(message)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _display_frame(self, frame_bgr) -> None:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        image = image.resize((640, 360), RESAMPLING)
        photo = ImageTk.PhotoImage(image)
        self.video_label.configure(image=photo)
        self.video_label.image = photo

    # ------------------------------------------------------------------
    # Eventos do usuário
    # ------------------------------------------------------------------
    def load_video(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecionar vídeo",
            filetypes=[("Vídeos MP4", "*.mp4"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        self._release_video()
        self.video_path = Path(file_path)
        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            messagebox.showerror("Erro", "Não foi possível abrir o vídeo selecionado.")
            self.video_path = None
            return

        ret, frame = self.cap.read()
        if not ret:
            messagebox.showerror("Erro", "O vídeo não contém quadros válidos.")
            self._release_video()
            return

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._display_frame(frame)
        self._log(f"Vídeo carregado: {self.video_path.name}")

    def start_analysis(self) -> None:
        if self.analysis_thread and self.analysis_thread.is_alive():
            messagebox.showinfo("Análise em andamento", "A análise já está em execução.")
            return

        if not self.video_path or not self.cap or not self.cap.isOpened():
            messagebox.showwarning("Vídeo não carregado", "Carregue um vídeo MP4 antes de iniciar a análise.")
            return

        api_key = self.api_key_entry.get().strip()
        if not api_key:
            messagebox.showwarning("Chave da API", "Informe sua chave da API GPT para continuar.")
            return

        try:
            self.gpt_client = GPTHelmetDetector(api_key=api_key)
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao inicializar cliente GPT: {exc}")
            return

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.frame_results.clear()
        self.stop_event.clear()
        self.analysis_thread = threading.Thread(target=self._analyze_video_loop, daemon=True)
        self.analysis_thread.start()
        self._log("Análise iniciada. Aguarde, pois as requisições à API podem levar alguns segundos por quadro.")

    def stop_analysis(self) -> None:
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.stop_event.set()
            self.analysis_thread.join(timeout=2)
            self._log("Análise interrompida pelo usuário.")
        self.analysis_thread = None

    def export_report(self) -> None:
        if not self.frame_results:
            messagebox.showinfo("Sem dados", "Nenhuma detecção disponível para exportação.")
            return

        export_path = filedialog.asksaveasfilename(
            title="Salvar relatório",
            defaultextension=".csv",
            filetypes=[("Arquivo CSV", "*.csv")],
        )
        if not export_path:
            return

        header = "frame_index,timestamp_s,helmet_detected,confidence,summary\n"
        lines = [header]
        for result in self.frame_results:
            confidence_str = f"{result.confidence:.2f}" if result.confidence is not None else ""
            summary_clean = result.summary.replace("\n", " ")
            lines.append(
                f"{result.frame_index},{result.timestamp_s:.2f},{int(result.helmet_detected)},{confidence_str},\"{summary_clean}\"\n"
            )

        Path(export_path).write_text("".join(lines), encoding="utf-8")
        self._log(f"Relatório exportado para {export_path}")

    # ------------------------------------------------------------------
    # Lógica de análise
    # ------------------------------------------------------------------
    def _analyze_video_loop(self) -> None:
        assert self.cap is not None
        assert self.gpt_client is not None

        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_index = 0
        processed_frames = 0

        while not self.stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                self._log("Fim do vídeo ou erro na leitura dos quadros.")
                break

            frame_index += 1
            if frame_index % max(1, self.frame_step.get()) != 0:
                continue

            timestamp = frame_index / fps
            try:
                detection = self.gpt_client.analyze_frame(frame)
                detection.frame_index = frame_index
                detection.timestamp_s = timestamp
                self.frame_results.append(detection)
            except Exception as exc:
                logging.exception("Erro durante a análise do quadro %s", frame_index)
                self._log(f"Erro ao analisar quadro {frame_index}: {exc}")
                continue

            annotated = frame.copy()
            label = "Capacete OK" if detection.helmet_detected else "Sem Capacete"
            color = (0, 180, 0) if detection.helmet_detected else (0, 0, 255)
            confidence_text = (
                f"{detection.confidence:.2f}" if detection.confidence is not None else "N/A"
            )
            cv2.putText(
                annotated,
                f"{label} (conf: {confidence_text})",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                color,
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                detection.summary[:90],
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

            processed_frames += 1
            self.root.after(0, self._display_frame, annotated)
            self.root.after(0, self._log, f"Quadro {frame_index}/{total_frames}: {detection.summary}")

        self.root.after(0, self._analysis_finished, processed_frames)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _release_video(self) -> None:
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None

    def _analysis_finished(self, processed_frames: int) -> None:
        interrupted = self.stop_event.is_set()
        status = "interrompida" if interrupted else "concluída"
        self._log(f"Análise {status}. Quadros processados: {processed_frames}.")
        if self.cap:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.analysis_thread = None
        self.stop_event.clear()

    def on_close(self) -> None:
        self.stop_event.set()
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=2)
        self._release_video()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------


def main() -> None:
    root = tk.Tk()
    app = HelmetDetectionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
