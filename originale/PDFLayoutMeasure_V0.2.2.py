import math
import os
import tkinter as tk
import queue
import threading
from collections import OrderedDict
from tkinter import filedialog, messagebox, simpledialog

import fitz
from PIL import Image, ImageTk


class PDFLayoutMeasure:
    VERSION = "V0.2.2"
    NONE = "none"
    CALIBRATE = "calibrate"
    MEASURE = "measure"

    def __init__(self, root):
        self.root = root
        self.root.title(f"PDF Layout Measure {self.VERSION}")
        self.root.geometry("1450x900")
        self.root.minsize(1000, 650)

        self.doc = None
        self.pdf_path = None
        self.page_index = 0
        self.page_width = 0.0
        self.page_height = 0.0

        self.zoom = 1.5
        self.min_zoom = 0.20
        self.max_zoom = 8.0

        # Tile renderer
        self.tile_size = 512
        self.tile_preload = 1
        self.max_cached_tiles = 160
        self.zoom_cache_precision = 3
        self.render_delay = 90
        self.render_job = None
        self.document_generation = 0
        self.tile_cache = OrderedDict()
        self.visible_tile_items = {}
        self.visible_tile_images = {}

        # Rendering asincrono: PyMuPDF lavora in un thread dedicato.
        # Tkinter e ImageTk restano sempre nel thread principale.
        self.render_epoch = 0
        self.task_sequence = 0
        self.pending_tile_keys = set()
        self.render_tasks = queue.PriorityQueue()
        self.render_results = queue.Queue()
        self.worker_stop = threading.Event()
        self.worker_thread = threading.Thread(
            target=self.render_worker,
            name="PDFTileRenderer",
            daemon=True
        )

        # Interaction and measurements
        self.is_panning = False
        self.mode = self.NONE
        self.selected_points = []
        self.mm_per_pdf_unit = None
        self.calibration_page = None
        self.calibration_points = []
        self.measurement_points = []
        self.measurement_result = None
        self.overlay_items = []
        self.crosshair_items = []

        self.create_gui()
        self.worker_thread.start()
        self.result_poll_job = self.root.after(20, self.process_render_results)
        self.root.after(100, self.initial_update)

    # ---------------- GUI ----------------
    def create_gui(self):
        top = tk.Frame(self.root, bg="#eeeeee", height=48)
        top.pack(side=tk.TOP, fill=tk.X)

        self.make_button(top, "Apri PDF", self.open_pdf, 12).pack(side=tk.LEFT, padx=5, pady=5)
        self.make_button(top, "< Pagina", self.previous_page, 10).pack(side=tk.LEFT, padx=2)
        self.make_button(top, "Pagina >", self.next_page, 10).pack(side=tk.LEFT, padx=2)
        self.page_label = tk.Label(top, text="Pagina: - / -", bg="#eeeeee")
        self.page_label.pack(side=tk.LEFT, padx=10)
        self.make_button(top, "Zoom -", self.zoom_out, 8).pack(side=tk.LEFT, padx=2)
        self.make_button(top, "Zoom +", self.zoom_in, 8).pack(side=tk.LEFT, padx=2)
        self.make_button(top, "Adatta", self.fit_page, 8).pack(side=tk.LEFT, padx=2)
        self.zoom_label = tk.Label(top, text="Zoom: 150%", bg="#eeeeee")
        self.zoom_label.pack(side=tk.LEFT, padx=10)
        self.status_label = tk.Label(top, text="Nessun PDF caricato", bg="#eeeeee", anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)

        tools = tk.Frame(self.root, bg="#dcdcdc", height=52)
        tools.pack(side=tk.TOP, fill=tk.X)
        self.btn_calibrate = self.make_button(tools, "Calibra scala", self.start_calibration, 14, tk.DISABLED)
        self.btn_measure = self.make_button(tools, "Misura", self.start_measurement, 12, tk.DISABLED)
        self.btn_clear = self.make_button(tools, "Cancella misura", self.clear_measurement, 15, tk.DISABLED)
        self.btn_reset = self.make_button(tools, "Reset scala", self.reset_scale, 12, tk.DISABLED)
        self.btn_cancel = self.make_button(tools, "Annulla selezione", self.cancel_operation, 16, tk.DISABLED)
        for button in (self.btn_calibrate, self.btn_measure, self.btn_clear, self.btn_reset, self.btn_cancel):
            button.pack(side=tk.LEFT, padx=2, pady=6)
        self.scale_label = tk.Label(tools, text="Scala: non calibrata", bg="#dcdcdc", fg="#a00000", font=("Segoe UI", 9, "bold"))
        self.scale_label.pack(side=tk.LEFT, padx=14)

        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)
        result = tk.Frame(main, width=270, bg="#f4f4f4", relief=tk.GROOVE, borderwidth=1)
        result.pack(side=tk.RIGHT, fill=tk.Y)
        result.pack_propagate(False)
        tk.Label(result, text="RISULTATO MISURA", bg="#f4f4f4", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=15, pady=(18, 12))
        self.result_x = self.result_row(result, "Delta X")
        self.result_y = self.result_row(result, "Delta Y")
        self.result_d = self.result_row(result, "Distanza", True)
        tk.Frame(result, height=1, bg="#cccccc").pack(fill=tk.X, padx=15, pady=18)
        self.mode_label = tk.Label(result, text="Nessuna operazione", bg="#f4f4f4", justify=tk.LEFT, wraplength=230, font=("Segoe UI", 10, "bold"))
        self.mode_label.pack(anchor="w", padx=15, pady=5)
        tk.Label(result, text="Rotella: scroll verticale\nShift + rotella: orizzontale\nCtrl + rotella: zoom\nTasto centrale/destro: pan", bg="#f4f4f4", fg="#555555", justify=tk.LEFT).pack(anchor="w", padx=15, pady=20)

        viewer = tk.Frame(main)
        viewer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.v_scroll = tk.Scrollbar(viewer, orient=tk.VERTICAL, command=self.vertical_scroll)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll = tk.Scrollbar(viewer, orient=tk.HORIZONTAL, command=self.horizontal_scroll)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas = tk.Canvas(viewer, bg="#404040", highlightthickness=0, xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bindings = {
            "<Button-1>": self.left_click, "<Motion>": self.mouse_motion,
            "<Leave>": self.mouse_leave, "<MouseWheel>": self.mouse_wheel,
            "<Shift-MouseWheel>": self.shift_mouse_wheel,
            "<Control-MouseWheel>": self.ctrl_mouse_wheel,
            "<ButtonPress-2>": self.start_pan, "<B2-Motion>": self.move_pan,
            "<ButtonRelease-2>": self.end_pan, "<ButtonPress-3>": self.start_pan,
            "<B3-Motion>": self.move_pan, "<ButtonRelease-3>": self.end_pan,
            "<Configure>": self.canvas_resized,
        }
        for event, callback in bindings.items():
            self.canvas.bind(event, callback)
        self.root.bind("<Escape>", lambda _event: self.cancel_operation())

    @staticmethod
    def make_button(parent, text, command, width, state=tk.NORMAL):
        return tk.Button(parent, text=text, command=command, width=width, state=state)

    @staticmethod
    def result_row(parent, title, highlight=False):
        frame = tk.Frame(parent, bg="#f4f4f4")
        frame.pack(fill=tk.X, padx=15, pady=6)
        tk.Label(frame, text=title, bg="#f4f4f4", fg="#606060").pack(anchor="w")
        label = tk.Label(frame, text="-", bg="#f4f4f4", fg="#005a9e" if highlight else "#202020", font=("Segoe UI", 13 if highlight else 11, "bold"), justify=tk.LEFT)
        label.pack(anchor="w", pady=(2, 0))
        return label

    def initial_update(self):
        self.update_labels()
        self.update_controls()

    # ---------------- PDF ----------------
    def open_pdf(self):
        path = filedialog.askopenfilename(title="Seleziona layout PDF", filetypes=[("File PDF", "*.pdf"), ("Tutti i file", "*.*")])
        if path:
            self.load_pdf(path)

    def load_pdf(self, path):
        try:
            new_doc = fitz.open(path)
            if len(new_doc) == 0:
                new_doc.close()
                raise ValueError("Il PDF non contiene pagine.")
            if self.doc:
                self.doc.close()
            self.doc = new_doc
            self.invalidate_document_tiles()
            self.pdf_path = path
            self.page_index = 0
            self.reset_all()
            self.root.title(f"PDF Layout Measure {self.VERSION} - {os.path.basename(path)}")
            self.status_label.config(text=os.path.basename(path))
            self.load_current_page()
            self.root.after(100, self.fit_page)
        except Exception as error:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF.\n\n{error}")

    def load_current_page(self):
        if not self.doc:
            return
        rect = self.doc.load_page(self.page_index).rect
        self.page_width, self.page_height = rect.width, rect.height
        if self.calibration_page is not None and self.calibration_page != self.page_index:
            self.reset_all()
        self.cancel_operation(False)
        self.clear_visible_tiles()
        self.update_scroll_region()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.update_labels()
        self.update_controls()
        self.schedule_render(10)

    # ---------------- Asynchronous tile renderer ----------------
    def schedule_render(self, delay=None):
        """Accorpa richieste ravvicinate di zoom, pan e scroll."""
        if not self.doc:
            return
        if delay is None:
            delay = self.render_delay
        if self.render_job is not None:
            try:
                self.root.after_cancel(self.render_job)
            except tk.TclError:
                pass
        self.render_job = self.root.after(delay, self.request_visible_tiles)

    def request_visible_tiles(self):
        """Mostra subito la cache e accoda le tile mancanti per il worker."""
        self.render_job = None
        if not self.doc or not self.pdf_path:
            return

        self.root.update_idletasks()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            self.schedule_render(100)
            return

        page_w = self.page_width * self.zoom
        page_h = self.page_height * self.zoom
        if page_w <= 0 or page_h <= 0:
            return

        x0 = max(0.0, self.canvas.canvasx(0))
        y0 = max(0.0, self.canvas.canvasy(0))
        x1 = min(page_w, x0 + width)
        y1 = min(page_h, y0 + height)
        size = self.tile_size

        c0 = max(0, int(x0 // size) - self.tile_preload)
        r0 = max(0, int(y0 // size) - self.tile_preload)
        c1 = min(int((page_w - 1) // size), int(x1 // size) + self.tile_preload)
        r1 = min(int((page_h - 1) // size), int(y1 // size) + self.tile_preload)

        required_positions = [(c, r) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        required_keys = {self.tile_key(c, r) for c, r in required_positions}

        for key in set(self.visible_tile_items) - required_keys:
            self.remove_visible_tile(key)

        # Ogni nuovo viewport invalida i risultati non ancora consegnati.
        self.render_epoch += 1
        epoch = self.render_epoch
        self.clear_task_queue()
        self.pending_tile_keys.clear()

        center_c = ((x0 + x1) / 2) / size
        center_r = ((y0 + y1) / 2) / size
        visible_c0 = int(x0 // size)
        visible_r0 = int(y0 // size)
        visible_c1 = int(x1 // size)
        visible_r1 = int(y1 // size)

        cached_count = 0
        queued_count = 0
        missing = []

        for column, row in required_positions:
            key = self.tile_key(column, row)
            if key in self.visible_tile_items:
                continue

            image = self.get_cached_tile(key)
            if image is not None:
                self.show_tile(key, column, row, image)
                cached_count += 1
                continue

            in_viewport = (
                visible_c0 <= column <= visible_c1
                and visible_r0 <= row <= visible_r1
            )
            ring_priority = 0 if in_viewport else 1
            distance_priority = (column - center_c) ** 2 + (row - center_r) ** 2
            missing.append((ring_priority, distance_priority, column, row, key))

        # Prima il centro del viewport, poi i bordi, infine il preload.
        missing.sort(key=lambda item: (item[0], item[1]))
        for ring_priority, distance_priority, column, row, key in missing:
            self.task_sequence += 1
            task = (
                ring_priority,
                distance_priority,
                self.task_sequence,
                epoch,
                self.document_generation,
                self.pdf_path,
                self.page_index,
                self.zoom,
                self.page_width,
                self.page_height,
                column,
                row,
                key,
            )
            self.pending_tile_keys.add(key)
            self.render_tasks.put(task)
            queued_count += 1

        self.redraw_overlays()
        self.status_label.config(
            text=(
                f"{os.path.basename(self.pdf_path)} | "
                f"Tile visibili: {len(self.visible_tile_items)} | "
                f"Cache: {cached_count} | In coda: {queued_count}"
            )
        )

    def render_worker(self):
        """Worker unico: usa un proprio documento PyMuPDF, mai quello della GUI."""
        worker_doc = None
        worker_path = None

        while not self.worker_stop.is_set():
            try:
                task = self.render_tasks.get(timeout=0.10)
            except queue.Empty:
                continue

            if task is None:
                break

            (
                _ring_priority,
                _distance_priority,
                _sequence,
                epoch,
                document_generation,
                path,
                page_index,
                zoom,
                page_width,
                page_height,
                column,
                row,
                key,
            ) = task

            try:
                if worker_doc is None or worker_path != path:
                    if worker_doc is not None:
                        worker_doc.close()
                    worker_doc = fitz.open(path)
                    worker_path = path

                image = self.render_tile_in_worker(
                    worker_doc,
                    page_index,
                    zoom,
                    page_width,
                    page_height,
                    column,
                    row,
                )
                self.render_results.put(("tile", epoch, document_generation, key, column, row, image))
            except Exception as error:
                self.render_results.put(("error", epoch, document_generation, key, str(error)))
            finally:
                self.render_tasks.task_done()

        if worker_doc is not None:
            worker_doc.close()

    def render_tile_in_worker(
        self,
        worker_doc,
        page_index,
        zoom,
        page_width,
        page_height,
        column,
        row,
    ):
        page_w = page_width * zoom
        page_h = page_height * zoom
        x0 = column * self.tile_size
        y0 = row * self.tile_size
        x1 = min(x0 + self.tile_size, page_w)
        y1 = min(y0 + self.tile_size, page_h)
        if x1 <= x0 or y1 <= y0:
            return None

        clip = fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)
        pix = worker_doc.load_page(page_index).get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            clip=clip,
            alpha=False,
        )
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def process_render_results(self):
        """Consegna progressivamente le tile alla GUI senza bloccare Tkinter."""
        processed = 0
        try:
            while processed < 4:
                result = self.render_results.get_nowait()
                processed += 1

                if result[0] == "error":
                    _, epoch, generation, key, error_text = result
                    self.pending_tile_keys.discard(key)
                    if epoch == self.render_epoch and generation == self.document_generation:
                        self.status_label.config(text=f"Errore tile: {error_text}")
                    continue

                _, epoch, generation, key, column, row, image = result
                self.pending_tile_keys.discard(key)

                # Ignora risultati prodotti per pagina, zoom o viewport precedenti.
                if (
                    image is None
                    or epoch != self.render_epoch
                    or generation != self.document_generation
                    or key != self.tile_key(column, row)
                ):
                    continue

                self.store_tile(key, image)
                if key not in self.visible_tile_items and self.tile_is_required_now(column, row):
                    self.show_tile(key, column, row, image)
                    self.redraw_overlays()

        except queue.Empty:
            pass

        if not self.worker_stop.is_set():
            self.result_poll_job = self.root.after(20, self.process_render_results)

    def tile_is_required_now(self, column, row):
        if not self.doc:
            return False
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        x0 = max(0.0, self.canvas.canvasx(0))
        y0 = max(0.0, self.canvas.canvasy(0))
        x1 = min(self.page_width * self.zoom, x0 + width)
        y1 = min(self.page_height * self.zoom, y0 + height)
        size = self.tile_size
        c0 = max(0, int(x0 // size) - self.tile_preload)
        r0 = max(0, int(y0 // size) - self.tile_preload)
        c1 = int(x1 // size) + self.tile_preload
        r1 = int(y1 // size) + self.tile_preload
        return c0 <= column <= c1 and r0 <= row <= r1

    def clear_task_queue(self):
        while True:
            try:
                self.render_tasks.get_nowait()
                self.render_tasks.task_done()
            except queue.Empty:
                break

    def tile_key(self, column, row):
        return (
            self.document_generation,
            self.page_index,
            round(self.zoom, self.zoom_cache_precision),
            column,
            row,
        )

    def show_tile(self, key, column, row, image):
        tk_image = ImageTk.PhotoImage(image)
        item = self.canvas.create_image(
            column * self.tile_size,
            row * self.tile_size,
            anchor=tk.NW,
            image=tk_image,
            tags=("pdf_tile",),
        )
        self.canvas.tag_lower(item)
        self.visible_tile_items[key] = item
        self.visible_tile_images[key] = tk_image

    def get_cached_tile(self, key):
        image = self.tile_cache.get(key)
        if image is not None:
            self.tile_cache.move_to_end(key)
        return image

    def store_tile(self, key, image):
        self.tile_cache[key] = image
        self.tile_cache.move_to_end(key)
        while len(self.tile_cache) > self.max_cached_tiles:
            self.tile_cache.popitem(last=False)

    def remove_visible_tile(self, key):
        item = self.visible_tile_items.pop(key, None)
        if item is not None:
            self.canvas.delete(item)
        self.visible_tile_images.pop(key, None)

    def clear_visible_tiles(self):
        for item in self.visible_tile_items.values():
            self.canvas.delete(item)
        self.visible_tile_items.clear()
        self.visible_tile_images.clear()

    def invalidate_document_tiles(self):
        self.document_generation += 1
        self.render_epoch += 1
        self.clear_task_queue()
        self.pending_tile_keys.clear()
        self.clear_visible_tiles()
        self.tile_cache.clear()

    # ---------------- Calibration and measure ----------------
    def start_calibration(self):
        if not self.doc:
            return
        self.cancel_operation(False)
        self.mode, self.selected_points = self.CALIBRATE, []
        self.mm_per_pdf_unit = self.calibration_page = None
        self.calibration_points = []
        self.measurement_points = []
        self.measurement_result = None
        self.reset_results()
        self.mode_label.config(text="CALIBRAZIONE\nSeleziona il primo punto", fg="#b00020")
        self.canvas.config(cursor="crosshair")
        self.update_scale_label()
        self.update_controls()
        self.redraw_overlays()

    def complete_calibration(self):
        p1, p2 = self.selected_points
        distance = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if distance <= 0:
            messagebox.showerror("Calibrazione non valida", "I due punti coincidono.")
            self.start_calibration()
            return
        real_mm = simpledialog.askfloat("Distanza reale", "Inserisci la distanza reale tra i due punti [mm]:", parent=self.root, minvalue=0.000001)
        if real_mm is None:
            self.cancel_operation()
            return
        self.mm_per_pdf_unit = real_mm / distance
        self.calibration_page = self.page_index
        self.calibration_points = [p1, p2]
        self.mode, self.selected_points = self.NONE, []
        self.canvas.config(cursor="")
        self.mode_label.config(text="Scala calibrata\nPremi Misura per iniziare", fg="#006400")
        self.update_scale_label()
        self.update_controls()
        self.redraw_overlays()

    def start_measurement(self):
        if not self.scale_valid():
            messagebox.showwarning("Scala non calibrata", "Prima calibra la scala con una distanza conosciuta.")
            return
        self.cancel_operation(False)
        self.mode, self.selected_points = self.MEASURE, []
        self.measurement_points = []
        self.measurement_result = None
        self.reset_results()
        self.mode_label.config(text="MISURA\nSeleziona il primo punto", fg="#005a9e")
        self.canvas.config(cursor="crosshair")
        self.update_controls()
        self.redraw_overlays()

    def complete_measurement(self):
        p1, p2 = self.selected_points
        dx = abs(p2[0] - p1[0]) * self.mm_per_pdf_unit
        dy = abs(p2[1] - p1[1]) * self.mm_per_pdf_unit
        distance = math.hypot(dx, dy)
        self.measurement_points = [p1, p2]
        self.measurement_result = {"x": dx, "y": dy, "d": distance}
        self.mode, self.selected_points = self.NONE, []
        self.canvas.config(cursor="")
        self.result_x.config(text=self.format_result(dx))
        self.result_y.config(text=self.format_result(dy))
        self.result_d.config(text=self.format_result(distance))
        self.mode_label.config(text="Misura completata\nPremi Misura per una nuova misura", fg="#006400")
        self.update_controls()
        self.redraw_overlays()

    def left_click(self, event):
        if self.mode not in (self.CALIBRATE, self.MEASURE):
            return
        point = self.event_to_pdf(event)
        if not (0 <= point[0] <= self.page_width and 0 <= point[1] <= self.page_height):
            return
        self.selected_points.append(point)
        if len(self.selected_points) == 1:
            self.mode_label.config(text=("CALIBRAZIONE" if self.mode == self.CALIBRATE else "MISURA") + "\nSeleziona il secondo punto")
        elif self.mode == self.CALIBRATE:
            self.complete_calibration()
        else:
            self.complete_measurement()
        self.redraw_overlays()

    # ---------------- Overlays ----------------
    def redraw_overlays(self):
        self.clear_overlays()
        if len(self.calibration_points) == 2:
            self.draw_segment(*self.calibration_points, "#e53935", "CALIBRAZIONE", (6, 4))
        if len(self.measurement_points) == 2:
            label = "MISURA"
            if self.measurement_result:
                label += "  " + self.format_mm(self.measurement_result["d"])
            self.draw_segment(*self.measurement_points, "#00a2ff", label)
        for index, point in enumerate(self.selected_points, 1):
            self.draw_marker(point, "#ffd000", f"P{index}")
        if len(self.selected_points) == 2:
            self.draw_line(*self.selected_points, "#ffd000", (4, 3))

    def clear_overlays(self):
        for item in self.overlay_items:
            self.canvas.delete(item)
        self.overlay_items.clear()

    def draw_segment(self, p1, p2, color, label, dash=None):
        self.draw_line(p1, p2, color, dash, 3)
        self.draw_marker(p1, color, "P1")
        self.draw_marker(p2, color, "P2")
        x1, y1 = self.pdf_to_canvas(*p1)
        x2, y2 = self.pdf_to_canvas(*p2)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        rect = self.canvas.create_rectangle(mx - 70, my - 16, mx + 70, my + 16, fill="white", outline=color, width=2)
        text = self.canvas.create_text(mx, my, text=label, fill="#202020", font=("Segoe UI", 9, "bold"))
        self.overlay_items.extend((rect, text))

    def draw_line(self, p1, p2, color, dash=None, width=2):
        x1, y1 = self.pdf_to_canvas(*p1)
        x2, y2 = self.pdf_to_canvas(*p2)
        self.overlay_items.append(self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, dash=dash))

    def draw_marker(self, point, color, text):
        x, y = self.pdf_to_canvas(*point)
        items = [
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=color, outline="#202020", width=2),
            self.canvas.create_line(x - 12, y, x + 12, y, fill=color, width=2),
            self.canvas.create_line(x, y - 12, x, y + 12, fill=color, width=2),
            self.canvas.create_text(x + 18, y - 12, text=text, fill=color, font=("Segoe UI", 9, "bold"), anchor=tk.W),
        ]
        self.overlay_items.extend(items)

    def mouse_motion(self, event):
        self.clear_crosshair()
        if self.mode not in (self.CALIBRATE, self.MEASURE):
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.crosshair_items = [
            self.canvas.create_line(x - 12, y, x + 12, y, fill="#ffd000"),
            self.canvas.create_line(x, y - 12, x, y + 12, fill="#ffd000"),
            self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, outline="#ffd000"),
        ]

    def mouse_leave(self, _event):
        self.clear_crosshair()

    def clear_crosshair(self):
        for item in self.crosshair_items:
            self.canvas.delete(item)
        self.crosshair_items.clear()

    # ---------------- Reset and controls ----------------
    def cancel_operation(self, update_message=True):
        self.mode, self.selected_points = self.NONE, []
        if hasattr(self, "canvas"):
            self.canvas.config(cursor="")
            self.clear_crosshair()
            self.redraw_overlays()
        if update_message and hasattr(self, "mode_label"):
            self.mode_label.config(text="Scala calibrata\nPremi Misura per iniziare" if self.scale_valid() else "Nessuna operazione\nPrima calibra la scala", fg="#006400" if self.scale_valid() else "#202020")
        if hasattr(self, "btn_calibrate"):
            self.update_controls()

    def clear_measurement(self):
        self.cancel_operation(False)
        self.measurement_points = []
        self.measurement_result = None
        self.reset_results()
        self.redraw_overlays()
        self.update_controls()

    def reset_scale(self):
        if self.mm_per_pdf_unit is None:
            return
        if messagebox.askyesno("Reset scala", "Cancellare calibrazione e ultima misura?"):
            self.reset_all()
            self.redraw_overlays()
            self.update_controls()

    def reset_all(self):
        self.mode, self.selected_points = self.NONE, []
        self.mm_per_pdf_unit = None
        self.calibration_page = None
        self.calibration_points = []
        self.measurement_points = []
        self.measurement_result = None
        if hasattr(self, "crosshair_items"):
            self.clear_crosshair()
        if hasattr(self, "result_x"):
            self.reset_results()
            self.update_scale_label()

    def reset_results(self):
        self.result_x.config(text="-")
        self.result_y.config(text="-")
        self.result_d.config(text="-")

    def scale_valid(self):
        return self.mm_per_pdf_unit is not None and self.mm_per_pdf_unit > 0 and self.calibration_page == self.page_index

    def update_controls(self):
        loaded = self.doc is not None
        active = self.mode != self.NONE
        calibrated = self.scale_valid()
        self.btn_calibrate.config(state=tk.NORMAL if loaded and not active else tk.DISABLED)
        self.btn_measure.config(state=tk.NORMAL if calibrated and not active else tk.DISABLED)
        self.btn_clear.config(state=tk.NORMAL if self.measurement_points and not active else tk.DISABLED)
        self.btn_reset.config(state=tk.NORMAL if calibrated and not active else tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL if active else tk.DISABLED)

    # ---------------- Navigation and zoom ----------------
    def previous_page(self):
        if self.doc and self.page_index > 0:
            self.page_index -= 1
            self.load_current_page()

    def next_page(self):
        if self.doc and self.page_index < len(self.doc) - 1:
            self.page_index += 1
            self.load_current_page()

    def update_scroll_region(self):
        self.canvas.config(scrollregion=(0, 0, self.page_width * self.zoom, self.page_height * self.zoom))

    def zoom_in(self):
        self.zoom_center(1.25)

    def zoom_out(self):
        self.zoom_center(1 / 1.25)

    def zoom_center(self, factor):
        self.apply_zoom(factor, self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)

    def apply_zoom(self, factor, cursor_x, cursor_y):
        if not self.doc:
            return
        old = self.zoom
        pdf_x, pdf_y = self.canvas.canvasx(cursor_x) / old, self.canvas.canvasy(cursor_y) / old
        new = max(self.min_zoom, min(old * factor, self.max_zoom))
        if abs(new - old) < 0.0001:
            return
        self.zoom = new
        self.clear_visible_tiles()
        self.update_scroll_region()
        self.root.update_idletasks()
        page_w, page_h = self.page_width * new, self.page_height * new
        left = max(0, min(pdf_x * new - cursor_x, max(0, page_w - self.canvas.winfo_width())))
        top = max(0, min(pdf_y * new - cursor_y, max(0, page_h - self.canvas.winfo_height())))
        if page_w:
            self.canvas.xview_moveto(left / page_w)
        if page_h:
            self.canvas.yview_moveto(top / page_h)
        self.update_labels()
        self.redraw_overlays()
        self.schedule_render(120)

    def fit_page(self):
        if not self.doc:
            return
        self.root.update_idletasks()
        width, height = self.canvas.winfo_width() - 30, self.canvas.winfo_height() - 30
        self.zoom = max(self.min_zoom, min(min(width / self.page_width, height / self.page_height), self.max_zoom))
        self.clear_visible_tiles()
        self.update_scroll_region()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.update_labels()
        self.redraw_overlays()
        self.schedule_render(10)

    # ---------------- Mouse, pan, scroll ----------------
    def mouse_wheel(self, event):
        if self.doc:
            self.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
            self.schedule_render(40)
        return "break"

    def shift_mouse_wheel(self, event):
        if self.doc:
            self.canvas.xview_scroll(-3 if event.delta > 0 else 3, "units")
            self.schedule_render(40)
        return "break"

    def ctrl_mouse_wheel(self, event):
        if self.doc:
            self.apply_zoom(1.20 if event.delta > 0 else 1 / 1.20, event.x, event.y)
        return "break"

    def vertical_scroll(self, *args):
        self.canvas.yview(*args)
        self.schedule_render(40)

    def horizontal_scroll(self, *args):
        self.canvas.xview(*args)
        self.schedule_render(40)

    def start_pan(self, event):
        if self.doc:
            self.is_panning = True
            self.canvas.scan_mark(event.x, event.y)
            self.canvas.config(cursor="fleur")

    def move_pan(self, event):
        if self.doc and self.is_panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            self.schedule_render(70)

    def end_pan(self, _event):
        if self.is_panning:
            self.is_panning = False
            self.canvas.config(cursor="crosshair" if self.mode != self.NONE else "")
            self.schedule_render(5)

    def canvas_resized(self, _event):
        if self.doc:
            self.schedule_render(100)

    # ---------------- Coordinates and formatting ----------------
    def event_to_pdf(self, event):
        return self.canvas.canvasx(event.x) / self.zoom, self.canvas.canvasy(event.y) / self.zoom

    def pdf_to_canvas(self, x, y):
        return x * self.zoom, y * self.zoom

    @staticmethod
    def format_number(value, decimals):
        return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def format_mm(self, value):
        return f"{self.format_number(value, 1)} mm"

    def format_result(self, value):
        return f"{self.format_number(value, 1)} mm\n{self.format_number(value / 1000, 3)} m"

    def update_scale_label(self):
        if self.scale_valid():
            self.scale_label.config(text=f"Scala: calibrata ({self.mm_per_pdf_unit:.6f} mm/unita PDF)", fg="#006400")
        else:
            self.scale_label.config(text="Scala: non calibrata", fg="#a00000")

    def update_labels(self):
        self.page_label.config(text=f"Pagina: {self.page_index + 1} / {len(self.doc)}" if self.doc else "Pagina: - / -")
        self.zoom_label.config(text=f"Zoom: {round(self.zoom * 100)}%")
        self.update_scale_label()

    # ---------------- Close ----------------
    def close_app(self):
        if self.render_job is not None:
            try:
                self.root.after_cancel(self.render_job)
            except tk.TclError:
                pass
        if getattr(self, "result_poll_job", None) is not None:
            try:
                self.root.after_cancel(self.result_poll_job)
            except tk.TclError:
                pass

        self.worker_stop.set()
        self.clear_task_queue()
        self.render_tasks.put(None)
        self.clear_visible_tiles()
        self.tile_cache.clear()

        if self.doc:
            self.doc.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PDFLayoutMeasure(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    root.mainloop()
