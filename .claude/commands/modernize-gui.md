# Modernize GUI — WhatsApp Message Sender

Redisena y moderniza la interfaz grafica de la aplicacion.

Objetivo especifico: $ARGUMENTS

Si no se especifica objetivo, aplica el Nivel 1 (Quick Wins con ttk.Style).

---

## CONTEXTO

La app usa Tkinter/ttk puro. Las siguientes librerias estan disponibles:
- customtkinter 5.2.2 (moderno, esquinas redondeadas, modo oscuro/claro)
- Pillow 11.3.0 (imagenes, iconos)
- tkinterdnd2 0.4.3 (drag & drop)

---

## FASE 1 — ANALISIS

Lee el archivo frontend/gui.py y responde:
1. Que colores/fuentes se usan actualmente (o ninguno = default gris)
2. Donde se definen los botones principales
3. Hay alguna funcion de estilos existente (_apply_theme, etc.)?
4. Que widgets son los mas prominentes visualmente
5. Hay imports de customtkinter? (verificar si ya se usa)

---

## NIVEL 1 — Quick Wins con ttk.Style (NO invasivo)

*Para aplicar: /modernize-gui nivel 1*

Agregar una funcion _apply_theme() llamada al final de _build_ui():

```python
def _apply_theme(self) -> None:
    """Aplica el sistema de diseno visual WhatsApp Pro a todos los widgets."""
    # === Colores del tema WhatsApp Pro ===
    PRIMARY   = "#075E54"   # Verde oscuro — header, botones primarios
    ACCENT    = "#25D366"   # Verde claro — acciones, badges
    BG_MAIN   = "#F0F2F5"   # Fondo principal claro
    BG_CARD   = "#FFFFFF"   # Fondo de tarjetas
    TEXT      = "#111B21"   # Texto principal
    TEXT_MUTED= "#667781"   # Texto secundario
    BORDER    = "#E9EDEF"   # Bordes suaves

    # Fondo de la ventana principal
    self.root.configure(bg=BG_MAIN)

    # Estilo de ttk (tabs, combobox, scrollbars)
    style = ttk.Style()
    style.theme_use("clam")  # Base mas personalizable que "default"

    # Tabs del Notebook
    style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_CARD, foreground=TEXT,
                    font=("Segoe UI", 10), padding=[12, 6])
    style.map("TNotebook.Tab",
              background=[("selected", PRIMARY)],
              foreground=[("selected", "#FFFFFF")])

    # Combobox
    style.configure("TCombobox", fieldbackground=BG_CARD, background=BORDER,
                    foreground=TEXT, font=("Segoe UI", 10))

    # Scrollbars
    style.configure("TScrollbar", background=BORDER, troughcolor=BG_MAIN,
                    relief="flat")

    # Aplicar colores a los widgets tk existentes
    for widget in self.root.winfo_children():
        _style_widget_recursive(widget, BG_MAIN, BG_CARD, TEXT, PRIMARY, ACCENT, BORDER)


def _style_widget_recursive(widget, bg_main, bg_card, text, primary, accent, border):
    """Aplica estilos recursivamente a todos los widgets de la jerarquia."""
    try:
        cls = widget.winfo_class()
        # Etiquetas (labels)
        if cls == "Label":
            widget.configure(bg=bg_main, fg=text, font=("Segoe UI", 10))
        # Campos de texto
        elif cls == "Entry":
            widget.configure(bg=bg_card, fg=text, relief="flat",
                             highlightbackground=border, highlightthickness=1,
                             font=("Segoe UI", 10))
        # Frames
        elif cls in ("Frame", "LabelFrame"):
            widget.configure(bg=bg_main)
        # Botones (excepto el de donacion que ya tiene color)
        elif cls == "Button":
            current_bg = widget.cget("bg")
            if current_bg not in ("#f5a623",):  # Preservar colores especiales
                widget.configure(bg=primary, fg="#FFFFFF", relief="flat",
                                 font=("Segoe UI", 10, "bold"),
                                 activebackground=accent, cursor="hand2",
                                 padx=12, pady=6)
        # Text (area de logs)
        elif cls == "Text":
            widget.configure(bg=bg_card, fg=text, relief="flat",
                             font=("Consolas", 9), insertbackground=text)
        # Listboxes
        elif cls == "Listbox":
            widget.configure(bg=bg_card, fg=text, relief="flat",
                             selectbackground=primary, selectforeground="#FFFFFF",
                             font=("Segoe UI", 10), borderwidth=0)
        # Canvas
        elif cls == "Canvas":
            widget.configure(bg=bg_main, highlightthickness=0)
    except tk.TclError:
        pass  # Ignorar widgets que no soporten la configuracion
    # Aplicar recursivamente a hijos
    for child in widget.winfo_children():
        _style_widget_recursive(child, bg_main, bg_card, text, primary, accent, border)
```

---

## NIVEL 2 — CustomTkinter Hibrido

*Para aplicar: /modernize-gui nivel 2*

Reemplazar botones principales con CTkButton manteniendo la logica:

```python
# Al inicio de gui.py agregar:
import customtkinter as ctk
ctk.set_appearance_mode("light")    # "light", "dark", "system"
ctk.set_default_color_theme("green")  # "blue", "green", "dark-blue"

# Reemplazar tk.Button por CTkButton:
btn_schedule = ctk.CTkButton(
    self.root,
    text=self.i18n.t("btn_schedule"),
    command=self.schedule_all_messages,
    fg_color="#075E54",       # Fondo verde WhatsApp
    hover_color="#128C7E",    # Hover mas claro
    text_color="#FFFFFF",
    corner_radius=8,
    font=ctk.CTkFont("Segoe UI", 11, "bold"),
    height=38,
)
```

---

## NIVEL 3 — Dark Mode Completo

*Para aplicar: /modernize-gui nivel 3*

Migracion completa a ctk.CTk() con modo oscuro/claro toggleable desde el menu.
Requiere reemplazar tk.Tk() por ctk.CTk() y todos los widgets progresivamente.

---

## PROCESO DE APLICACION

1. Analizar gui.py (SIEMPRE primero)
2. Elegir nivel segun el objetivo
3. Aplicar cambios con Edit tool (quirurgico, no reescribir)
4. Verificar sintaxis: python -c "import ast; ast.parse(open(chr(39)frontend/gui.py chr(39), encoding=chr(39)utf-8chr(39)).read()); print(chr(39)OKchr(39))"
5. Bump version: python scripts/bump_version.py minor (si es cambio visual significativo)
6. Actualizar CHANGELOG.md
7. Compilar: .\\build_exe.ps1
8. Push a GitHub

---

## REGLAS
- Preservar 100% funcionalidad (scheduling, browser control, i18n, logging)
- No bloquear el hilo principal de la GUI
- Comentar cada cambio de estilo para saber que hace
- Cambios incrementales (un componente a la vez)
- Siempre verificar sintaxis antes de reportar como completo
