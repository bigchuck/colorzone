"""
ColorZone — painting color study utility
Overlay colored zones on a line drawing to explore color temperature
relationships before committing to canvas.

Usage:
    python colorzone.py                  # startup dialog
    python colorzone.py session.json     # open existing session directly
"""

import json
import os
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)

APP_TITLE = "ColorZone"
HANDLE_RADIUS = 6
HANDLE_COLOR = "#ffffff"
HANDLE_ACTIVE = "#ffdd00"
HANDLE_OUTLINE = "#333333"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Zone:
    def __init__(self, name, polygons=None, color="#888888",
                 opacity=0.55, z_order=0):
        self.name = name
        self.polygons = polygons or [[]]   # list of polygon point lists
        self.color = color
        self.opacity = opacity
        self.z_order = z_order

    def to_dict(self):
        return {
            "name": self.name,
            "polygons": self.polygons,
            "color": self.color,
            "opacity": round(self.opacity, 3),
            "z_order": self.z_order,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            polygons=d.get("polygons", [[]]),
            color=d.get("color", "#888888"),
            opacity=d.get("opacity", 0.55),
            z_order=d.get("z_order", 0),
        )


class Session:
    def __init__(self, drawing_path="", canvas_w=800, canvas_h=640, zones=None):
        self.drawing_path = drawing_path   # relative to session file
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h
        self.zones = zones or []
        self.session_path = None           # set when saved

    def to_dict(self):
        return {
            "drawing_path": self.drawing_path,
            "canvas_w": self.canvas_w,
            "canvas_h": self.canvas_h,
            "zones": [z.to_dict() for z in self.zones],
        }

    @classmethod
    def from_dict(cls, d):
        s = cls(
            drawing_path=d.get("drawing_path", ""),
            canvas_w=d.get("canvas_w", 800),
            canvas_h=d.get("canvas_h", 640),
        )
        s.zones = [Zone.from_dict(z) for z in d.get("zones", [])]
        return s

    def resolve_drawing(self):
        """Return absolute path to the drawing image, or None."""
        if not self.drawing_path:
            return None
        p = Path(self.drawing_path)
        if p.is_absolute() and p.exists():
            return str(p)
        if self.session_path:
            base = Path(self.session_path).parent
            candidate = base / p
            if candidate.exists():
                return str(candidate)
        if p.exists():
            return str(p)
        return None


# ---------------------------------------------------------------------------
# Session manager (load / save)
# ---------------------------------------------------------------------------

class SessionManager:
    @staticmethod
    def save(session):
        if not session.session_path:
            path = filedialog.asksaveasfilename(
                title="Save session",
                defaultextension=".json",
                filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return False
            session.session_path = path
        with open(session.session_path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        return True

    @staticmethod
    def save_as(session):
        path = filedialog.asksaveasfilename(
            title="Save session as",
            defaultextension=".json",
            filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return False
        session.session_path = path
        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        return True

    @staticmethod
    def load(path=None):
        if not path:
            path = filedialog.askopenfilename(
                title="Open session",
                filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
            )
        if not path:
            return None
        with open(path) as f:
            data = json.load(f)
        session = Session.from_dict(data)
        session.session_path = path
        return session


# ---------------------------------------------------------------------------
# Renderer — composites zones over the drawing with Pillow
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self, session):
        self.session = session

    def _load_drawing(self):
        path = self.session.resolve_drawing()
        if path:
            img = Image.open(path).convert("RGBA")
            img = img.resize((self.session.canvas_w, self.session.canvas_h),
                              Image.LANCZOS)
            return img
        # blank white canvas if no drawing
        img = Image.new("RGBA",
                        (self.session.canvas_w, self.session.canvas_h),
                        (255, 255, 255, 255))
        return img

    def render(self, highlight_zone=None):
        """Return a composited PIL Image."""
        drawing = self._load_drawing()
        overlay = Image.new("RGBA", drawing.size, (0, 0, 0, 0))

        sorted_zones = sorted(self.session.zones, key=lambda z: z.z_order)
        for zone in sorted_zones:
            if not zone.polygons:
                continue
            r, g, b = self._hex_to_rgb(zone.color)
            alpha = int(zone.opacity * 255)
            if highlight_zone and zone is highlight_zone:
                alpha = min(255, alpha + 60)

            zone_layer = Image.new("RGBA", drawing.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(zone_layer)
            for poly in zone.polygons:
                if len(poly) >= 3:
                    flat = [coord for pt in poly for coord in pt]
                    draw.polygon(flat, fill=(r, g, b, alpha))
            overlay = Image.alpha_composite(overlay, zone_layer)

        result = Image.alpha_composite(drawing, overlay)
        return result

    def export_flat(self):
        path = filedialog.asksaveasfilename(
            title="Export flat PNG",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        img = self.render().convert("RGB")
        img.save(path)
        messagebox.showinfo(APP_TITLE, f"Exported to:\n{path}")

    @staticmethod
    def _hex_to_rgb(hex_color):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Startup dialog
# ---------------------------------------------------------------------------

class StartupDialog(tk.Tk):
    """Startup dialog runs as the root Tk window to avoid event-loop issues."""

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(False, False)
        self.result = None    # Session or None

        pad = dict(padx=16, pady=8)

        tk.Label(self, text="ColorZone",
                 font=("TkDefaultFont", 18, "bold")).pack(pady=(20, 4))
        tk.Label(self, text="Painting color study utility",
                 fg="#666666").pack(pady=(0, 16))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16)

        tk.Button(self, text="New session …",
                  width=28, height=2,
                  command=self._new).pack(**pad)
        tk.Button(self, text="Open session …",
                  width=28, height=2,
                  command=self._open).pack(**pad)
        tk.Button(self, text="Quit",
                  width=28,
                  command=self._quit).pack(pady=(4, 20))

        self.protocol("WM_DELETE_WINDOW", self._quit)
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _new(self):
        drawing = filedialog.askopenfilename(
            title="Select line drawing",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not drawing:
            return
        img = Image.open(drawing)
        w, h = img.size
        self.result = Session(drawing_path=drawing, canvas_w=w, canvas_h=h)
        self.quit()     # exit mainloop, keep window alive briefly

    def _open(self):
        session = SessionManager.load()
        if session:
            self.result = session
            self.quit()

    def _quit(self):
        self.result = None
        self.quit()


# ---------------------------------------------------------------------------
# Canvas editor — handles zone overlay + polygon editing
# ---------------------------------------------------------------------------

class CanvasEditor(tk.Canvas):
    """
    Zoom-aware canvas editor.
    Polygon coords are always stored in IMAGE space (original pixel coords).
    Display coords = image coords * zoom.
    """

    ZOOM_STEPS = [0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67,
                  0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]

    def __init__(self, parent, session, renderer, on_change,
                 on_zoom_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.session = session
        self.renderer = renderer
        self.on_change = on_change
        self.on_zoom_change = on_zoom_change  # callback(zoom_pct_str)

        self.active_zone = None
        self.active_poly_idx = 0
        self.edit_mode = False
        self.drag_vertex = None

        self.zoom = 1.0
        self._photo = None
        self._base_img = None    # cached full-res render

        # grab focus on any click so keyboard bindings work
        self.bind("<Button-1>",       self._on_click)
        self.bind("<B1-Motion>",      self._on_drag)
        self.bind("<ButtonRelease-1>",self._on_release)
        self.bind("<Button-3>",       self._on_right_click)
        self.bind("<Return>",         self._done_editing)
        self.bind("<Escape>",         self._cancel_edit)
        # mouse-wheel zoom
        self.bind("<MouseWheel>",     self._on_wheel)       # Windows/macOS
        self.bind("<Button-4>",       self._on_wheel)       # Linux scroll up
        self.bind("<Button-5>",       self._on_wheel)       # Linux scroll down

    # ---- coordinate helpers -----------------------------------------------

    def _to_img(self, cx, cy):
        """Canvas display coords → image coords."""
        return cx / self.zoom, cy / self.zoom

    def _to_canvas(self, ix, iy):
        """Image coords → canvas display coords."""
        return ix * self.zoom, iy * self.zoom

    # ---- rendering --------------------------------------------------------

    def refresh(self, highlight=None, rerender=True):
        if rerender or self._base_img is None:
            self._base_img = self.renderer.render(highlight_zone=highlight)

        w = int(self._base_img.width  * self.zoom)
        h = int(self._base_img.height * self.zoom)
        if w < 1 or h < 1:
            return
        displayed = self._base_img.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(displayed)

        self.config(scrollregion=(0, 0, w, h))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)

        if self.edit_mode and self.active_zone:
            self._draw_handles()

        if self.on_zoom_change:
            self.on_zoom_change(f"{int(self.zoom * 100)}%")

    def _draw_handles(self):
        zone = self.active_zone
        z = self.zoom
        for pi, poly in enumerate(zone.polygons):
            if len(poly) >= 2:
                flat = [c * z for pt in poly for c in pt]
                if len(poly) >= 3:
                    self.create_polygon(flat, outline="#ffdd00",
                                        fill="", width=2, tags="handle")
                else:
                    self.create_line(flat, fill="#ffdd00",
                                     width=2, tags="handle")
            for vi, (ix, iy) in enumerate(poly):
                cx, cy = ix * z, iy * z
                r = HANDLE_RADIUS
                active = (pi == self.active_poly_idx and
                          self.drag_vertex == (pi, vi))
                fill = HANDLE_ACTIVE if active else HANDLE_COLOR
                self.create_oval(cx-r, cy-r, cx+r, cy+r,
                                 fill=fill, outline=HANDLE_OUTLINE,
                                 width=1.5, tags=("handle", f"v_{pi}_{vi}"))

            if len(poly) >= 2:
                for vi in range(len(poly)):
                    ix1, iy1 = poly[vi]
                    ix2, iy2 = poly[(vi+1) % len(poly)]
                    mcx = (ix1 + ix2) / 2 * z
                    mcy = (iy1 + iy2) / 2 * z
                    r = 4
                    self.create_oval(mcx-r, mcy-r, mcx+r, mcy+r,
                                     fill="#aaaaaa", outline="#333333",
                                     width=1, tags=("handle", f"m_{pi}_{vi}"))

    # ---- zoom controls ----------------------------------------------------

    def zoom_in(self):
        steps = self.ZOOM_STEPS
        for s in steps:
            if s > self.zoom + 0.001:
                self.zoom = s
                break
        else:
            self.zoom = steps[-1]
        self.refresh()

    def zoom_out(self):
        steps = list(reversed(self.ZOOM_STEPS))
        for s in steps:
            if s < self.zoom - 0.001:
                self.zoom = s
                break
        else:
            self.zoom = steps[-1]
        self.refresh()

    def zoom_fit(self):
        """Fit the full drawing inside the visible canvas area."""
        self.update_idletasks()
        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw < 2 or vh < 2:
            return
        zw = vw / self.session.canvas_w
        zh = vh / self.session.canvas_h
        raw = min(zw, zh)
        # snap to nearest step below
        best = self.ZOOM_STEPS[0]
        for s in self.ZOOM_STEPS:
            if s <= raw + 0.001:
                best = s
        self.zoom = best
        self.refresh()

    def _on_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    # ---- interaction ------------------------------------------------------

    def _on_click(self, event):
        self.focus_set()          # always grab keyboard focus on click
        if not self.edit_mode or not self.active_zone:
            return

        ix, iy = self._to_img(event.x, event.y)

        hit = self._hit_vertex(ix, iy)
        if hit:
            self.drag_vertex = hit
            return

        mid = self._hit_midpoint(ix, iy)
        if mid:
            pi, vi = mid
            poly = self.active_zone.polygons[pi]
            insert_at = vi + 1
            mix = (poly[vi][0] + poly[(vi+1) % len(poly)][0]) / 2
            miy = (poly[vi][1] + poly[(vi+1) % len(poly)][1]) / 2
            poly.insert(insert_at, [mix, miy])
            self.drag_vertex = (pi, insert_at)
            self.on_change()
            self.refresh(highlight=self.active_zone)
            return

        poly = self.active_zone.polygons[self.active_poly_idx]
        poly.append([ix, iy])
        self.on_change()
        self.refresh(highlight=self.active_zone)

    def _on_drag(self, event):
        if not self.edit_mode or self.drag_vertex is None:
            return
        pi, vi = self.drag_vertex
        ix, iy = self._to_img(event.x, event.y)
        self.active_zone.polygons[pi][vi] = [ix, iy]
        self.refresh(highlight=self.active_zone)

    def _on_release(self, event):
        if self.drag_vertex is not None:
            self.on_change()
        self.drag_vertex = None

    def _on_right_click(self, event):
        if not self.edit_mode or not self.active_zone:
            return
        ix, iy = self._to_img(event.x, event.y)
        hit = self._hit_vertex(ix, iy)
        if hit:
            pi, vi = hit
            poly = self.active_zone.polygons[pi]
            if len(poly) > 1:
                poly.pop(vi)
                self.on_change()
                self.refresh(highlight=self.active_zone)

    def _done_editing(self, event=None):
        """Enter — finish adding vertices to current polygon."""
        self.refresh(highlight=self.active_zone)

    def _cancel_edit(self, event=None):
        self.edit_mode = False
        self.refresh()

    # ---- hit testing (image-space coords) ---------------------------------

    def _hit_vertex(self, ix, iy):
        # hit radius scaled back to image space
        r = (HANDLE_RADIUS + 4) / self.zoom
        if not self.active_zone:
            return None
        for pi, poly in enumerate(self.active_zone.polygons):
            for vi, (vx, vy) in enumerate(poly):
                if abs(ix - vx) <= r and abs(iy - vy) <= r:
                    return (pi, vi)
        return None

    def _hit_midpoint(self, ix, iy):
        r = 6 / self.zoom
        if not self.active_zone:
            return None
        for pi, poly in enumerate(self.active_zone.polygons):
            if len(poly) < 2:
                continue
            for vi in range(len(poly)):
                x1, y1 = poly[vi]
                x2, y2 = poly[(vi+1) % len(poly)]
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                if abs(ix - mx) <= r and abs(iy - my) <= r:
                    return (pi, vi)
        return None

    # ---- zone editing controls --------------------------------------------

    def start_zone_edit(self, zone, poly_idx=0):
        self.active_zone = zone
        self.active_poly_idx = poly_idx
        self.edit_mode = True
        self.focus_set()
        self.refresh(highlight=zone)

    def stop_zone_edit(self):
        self.edit_mode = False
        self.active_zone = None
        self.refresh()

    def add_polygon_to_zone(self, zone):
        zone.polygons.append([])
        self.active_poly_idx = len(zone.polygons) - 1
        self.on_change()


# ---------------------------------------------------------------------------
# Zone list panel
# ---------------------------------------------------------------------------

class ZonePanel(tk.Frame):
    def __init__(self, parent, session, on_select, on_change, **kwargs):
        super().__init__(parent, **kwargs)
        self.session = session
        self.on_select = on_select
        self.on_change = on_change
        self.selected_zone = None

        self._build()

    def _build(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        tk.Label(top, text="Zones", font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Button(top, text="+", width=2, command=self._add_zone).pack(side="right")

        self.listbox = tk.Listbox(self, selectmode="single",
                                   activestyle="none",
                                   font=("TkDefaultFont", 10),
                                   height=12)
        self.listbox.pack(fill="both", expand=True, padx=6)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        ctrl = tk.Frame(self)
        ctrl.pack(fill="x", padx=6, pady=4)
        tk.Button(ctrl, text="▲", width=2,
                  command=self._move_up).pack(side="left")
        tk.Button(ctrl, text="▼", width=2,
                  command=self._move_down).pack(side="left", padx=2)
        tk.Button(ctrl, text="Del", width=4,
                  command=self._remove_zone).pack(side="right")

        # Color / opacity controls
        props = tk.LabelFrame(self, text="Zone properties", padx=6, pady=6)
        props.pack(fill="x", padx=6, pady=(0, 6))

        tk.Label(props, text="Color").grid(row=0, column=0, sticky="w")
        self.color_btn = tk.Button(props, text="      ",
                                    relief="raised",
                                    command=self._pick_color)
        self.color_btn.grid(row=0, column=1, sticky="ew", padx=4)

        tk.Label(props, text="Opacity").grid(row=1, column=0, sticky="w")
        self.opacity_var = tk.DoubleVar(value=0.55)
        self.opacity_slider = tk.Scale(props, from_=0.05, to=1.0,
                                       resolution=0.05,
                                       orient="horizontal",
                                       variable=self.opacity_var,
                                       showvalue=True,
                                       command=self._opacity_changed)
        self.opacity_slider.grid(row=1, column=1, sticky="ew", padx=4)

        tk.Label(props, text="Z-order").grid(row=2, column=0, sticky="w")
        self.z_var = tk.IntVar(value=0)
        self.z_spin = tk.Spinbox(props, from_=0, to=99,
                                  textvariable=self.z_var, width=5,
                                  command=self._z_changed)
        self.z_spin.grid(row=2, column=1, sticky="w", padx=4)
        props.columnconfigure(1, weight=1)

        tk.Label(props, text="Name").grid(row=3, column=0, sticky="w")
        self.name_var = tk.StringVar()
        name_entry = tk.Entry(props, textvariable=self.name_var, width=14)
        name_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=(4, 0))
        name_entry.bind("<Return>", self._name_changed)
        name_entry.bind("<FocusOut>", self._name_changed)

    def refresh(self):
        self.listbox.delete(0, "end")
        for z in sorted(self.session.zones, key=lambda x: x.z_order):
            self.listbox.insert("end", f"[{z.z_order}] {z.name}")
        self._sync_props()

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        zones_sorted = sorted(self.session.zones, key=lambda x: x.z_order)
        self.selected_zone = zones_sorted[idx]
        self._sync_props()
        self.on_select(self.selected_zone)

    def _sync_props(self):
        z = self.selected_zone
        if not z:
            return
        self.color_btn.config(bg=z.color)
        self.opacity_var.set(z.opacity)
        self.z_var.set(z.z_order)
        self.name_var.set(z.name)

    def _add_zone(self):
        name = f"zone_{len(self.session.zones)+1}"
        z_order = max((z.z_order for z in self.session.zones), default=-1) + 1
        zone = Zone(name=name, z_order=z_order)
        self.session.zones.append(zone)
        self.selected_zone = zone
        self.refresh()
        self.on_change()
        # select last item
        self.listbox.select_set("end")
        self.on_select(zone)

    def _remove_zone(self):
        if not self.selected_zone:
            return
        if not messagebox.askyesno(APP_TITLE,
                f"Remove zone '{self.selected_zone.name}'?"):
            return
        self.session.zones.remove(self.selected_zone)
        self.selected_zone = None
        self.refresh()
        self.on_change()
        self.on_select(None)

    def _move_up(self):
        if not self.selected_zone:
            return
        z = self.selected_zone
        z.z_order = max(0, z.z_order - 1)
        self.refresh()
        self.on_change()

    def _move_down(self):
        if not self.selected_zone:
            return
        z = self.selected_zone
        z.z_order += 1
        self.refresh()
        self.on_change()

    def _pick_color(self):
        if not self.selected_zone:
            return
        color = colorchooser.askcolor(
            color=self.selected_zone.color,
            title="Pick zone color",
        )
        if color and color[1]:
            self.selected_zone.color = color[1]
            self.color_btn.config(bg=color[1])
            self.on_change()

    def _opacity_changed(self, val=None):
        if self.selected_zone:
            self.selected_zone.opacity = self.opacity_var.get()
            self.on_change()

    def _z_changed(self):
        if self.selected_zone:
            self.selected_zone.z_order = self.z_var.get()
            self.refresh()
            self.on_change()

    def _name_changed(self, event=None):
        if self.selected_zone:
            self.selected_zone.name = self.name_var.get()
            self.refresh()
            self.on_change()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class MainWindow(tk.Tk):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.renderer = Renderer(session)
        self.unsaved = False

        self.title(self._window_title())
        self.resizable(True, True)

        self._build_menu()
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.refresh_all()

    def _window_title(self):
        name = (Path(self.session.session_path).name
                if self.session.session_path else "Untitled")
        dirty = " •" if self.unsaved else ""
        return f"{APP_TITLE} — {name}{dirty}"

    def _build_menu(self):
        mb = tk.Menu(self)
        self.config(menu=mb)

        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="File", menu=fm)
        fm.add_command(label="Save session        Ctrl+S", command=self._save)
        fm.add_command(label="Save session as …",          command=self._save_as)
        fm.add_separator()
        fm.add_command(label="Export flat PNG …",          command=self.renderer.export_flat)
        fm.add_separator()
        fm.add_command(label="Quit",                       command=self._on_close)

        self.bind_all("<Control-s>", lambda e: self._save())

    def _build_ui(self):
        # ---- Toolbar -------------------------------------------------------
        tb = tk.Frame(self, relief="flat", bd=1, bg="#ececec")
        tb.pack(side="top", fill="x")

        def tbtn(parent, text, cmd, width=None, bg=None):
            kw = dict(text=text, command=cmd, relief="flat",
                      padx=6, pady=3, font=("TkDefaultFont", 10),
                      activebackground="#d0d0d0",
                      bg=bg or "#ececec")
            if width:
                kw["width"] = width
            return tk.Button(parent, **kw)

        # Zoom controls
        tk.Label(tb, text="Zoom:", bg="#ececec",
                 font=("TkDefaultFont", 10)).pack(side="left", padx=(6, 2))
        tbtn(tb, "−", self._zoom_out, width=2).pack(side="left")
        self.zoom_label = tk.Label(tb, text="100%", width=5,
                                   bg="#ececec",
                                   font=("TkDefaultFont", 10))
        self.zoom_label.pack(side="left")
        tbtn(tb, "+", self._zoom_in,  width=2).pack(side="left")
        tbtn(tb, "Fit", self._zoom_fit).pack(side="left", padx=(2, 12))

        ttk.Separator(tb, orient="vertical").pack(side="left",
                                                   fill="y", pady=4, padx=2)

        # Edit controls
        self.edit_btn = tbtn(tb, "✏  Edit zone",
                             self._start_edit, bg="#ececec")
        self.edit_btn.pack(side="left", padx=4)

        tbtn(tb, "+ polygon", self._add_polygon).pack(side="left")

        self.stop_btn = tbtn(tb, "✓ Done",
                             self._stop_edit, bg="#c8eac8")
        self.stop_btn.pack(side="left", padx=4)
        self.stop_btn.config(state="disabled")

        ttk.Separator(tb, orient="vertical").pack(side="left",
                                                   fill="y", pady=4, padx=2)

        tbtn(tb, "Export PNG", self.renderer.export_flat).pack(side="left", padx=4)

        # Edit mode indicator label (right side)
        self.mode_label = tk.Label(tb, text="", bg="#ececec",
                                   font=("TkDefaultFont", 9, "italic"),
                                   fg="#666666")
        self.mode_label.pack(side="right", padx=8)

        # ---- Main pane: canvas left, zone panel right ----------------------
        pane = tk.PanedWindow(self, orient="horizontal",
                               sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # Canvas in a scrollable frame
        canvas_frame = tk.Frame(pane, bg="#888888")
        pane.add(canvas_frame, minsize=400)

        self.h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal")
        self.v_scroll = tk.Scrollbar(canvas_frame, orient="vertical")
        self.h_scroll.pack(side="bottom", fill="x")
        self.v_scroll.pack(side="right",  fill="y")

        self.editor = CanvasEditor(
            canvas_frame, self.session, self.renderer,
            on_change=self._mark_dirty,
            on_zoom_change=self._update_zoom_label,
            bg="#888888",
            cursor="crosshair",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )
        self.editor.pack(side="left", fill="both", expand=True)
        self.h_scroll.config(command=self.editor.xview)
        self.v_scroll.config(command=self.editor.yview)

        # Zone panel
        self.zone_panel = ZonePanel(
            pane, self.session,
            on_select=self._on_zone_select,
            on_change=self._mark_dirty,
            width=230,
        )
        pane.add(self.zone_panel, minsize=230)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = tk.Label(self, textvariable=self.status_var,
                          anchor="w", relief="sunken",
                          font=("TkDefaultFont", 9), fg="#555555")
        status.pack(side="bottom", fill="x", padx=2, pady=1)

    # ---- zoom helpers -----------------------------------------------------

    def _zoom_in(self):
        self.editor.zoom_in()

    def _zoom_out(self):
        self.editor.zoom_out()

    def _zoom_fit(self):
        self.editor.zoom_fit()

    def _update_zoom_label(self, pct_str):
        self.zoom_label.config(text=pct_str)

    # ---- zone editing -----------------------------------------------------

    def _on_zone_select(self, zone):
        if zone:
            self.editor.active_zone = zone
            self.status_var.set(
                f"Selected: {zone.name}  —  "
                f"click '✏ Edit zone' to draw vertices")
        else:
            self.editor.active_zone = None
            self.status_var.set("Ready")
        self.refresh_canvas()

    def _start_edit(self):
        z = self.zone_panel.selected_zone
        if not z:
            messagebox.showinfo(APP_TITLE, "Select a zone in the list first.")
            return
        if not z.polygons:
            z.polygons = [[]]
        self.editor.start_zone_edit(z)
        self.edit_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.mode_label.config(text="EDITING — click=add vertex  drag=move  "
                                    "right-click=delete  Enter=done  Esc=cancel",
                               fg="#cc3300")
        self.status_var.set(
            f"Editing: {z.name}  —  "
            f"click canvas to place vertices, drag handles to adjust")

    def _add_polygon(self):
        z = self.zone_panel.selected_zone
        if not z:
            messagebox.showinfo(APP_TITLE, "Select a zone first.")
            return
        self.editor.add_polygon_to_zone(z)
        self.editor.start_zone_edit(z, poly_idx=len(z.polygons)-1)
        self.edit_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.mode_label.config(text="EDITING new polygon", fg="#cc3300")
        self.status_var.set(
            f"New polygon on: {z.name}  —  click to add vertices")

    def _stop_edit(self):
        self.editor.stop_zone_edit()
        self.edit_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.mode_label.config(text="", fg="#666666")
        self.status_var.set("Ready")

    # ---- refresh ----------------------------------------------------------

    def refresh_all(self):
        self.zone_panel.refresh()
        self.refresh_canvas()
        self.after(50, self.editor.zoom_fit)

    def refresh_canvas(self):
        highlight = (self.editor.active_zone
                     if self.editor.edit_mode else None)
        self.editor.refresh(highlight=highlight)

    def _mark_dirty(self):
        self.unsaved = True
        self.title(self._window_title())
        self.refresh_canvas()
        self.zone_panel.refresh()

    # ---- file operations --------------------------------------------------

    def _save(self):
        if SessionManager.save(self.session):
            self.unsaved = False
            self.title(self._window_title())
            self.status_var.set("Session saved.")

    def _save_as(self):
        if SessionManager.save_as(self.session):
            self.unsaved = False
            self.title(self._window_title())
            self.status_var.set("Session saved.")

    def _on_close(self):
        if self.unsaved:
            r = messagebox.askyesnocancel(APP_TITLE,
                "You have unsaved changes. Save before closing?")
            if r is None:
                return
            if r:
                if not SessionManager.save(self.session):
                    return
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    session = None

    # Command-line argument: open session directly
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path):
            # Need a minimal Tk to load the file dialog / messageboxes
            root = tk.Tk()
            root.withdraw()
            session = SessionManager.load(path)
            root.destroy()
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_TITLE, f"File not found:\n{path}")
            root.destroy()
            return

    # Startup dialog if no session yet
    if session is None:
        dlg = StartupDialog()
        dlg.mainloop()          # blocks until quit() or window close
        session = dlg.result
        dlg.destroy()           # clean up the startup window

    if session is None:
        return

    app = MainWindow(session)
    app.mainloop()


if __name__ == "__main__":
    main()