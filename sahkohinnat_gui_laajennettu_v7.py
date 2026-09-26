import calendar
import csv
import datetime
import json
import logging
import math
import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, ttk, messagebox
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import requests
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkcalendar import DateEntry


# Ammattimainen business dark mode / Fluent UI -väripaletti
COLORS = {
    "bg": "#181A1F",
    "surface": "#22252B",
    "primary": "#4F8CC9",
    "primary_hover": "#66A3DF",
    "secondary": "#73A6DC",
    "accent": "#FFB900",
    "accent_dark": "#C17D11",
    "text": "#F3F2F1",
    "muted": "#C8C6C4",
    "grid": "#3B4048",
    "header": "#2D3138",
    "selection": "#264F78",
    "border": "#454B55",
}

plt.rcParams["axes.facecolor"] = COLORS["surface"]
plt.rcParams["figure.facecolor"] = COLORS["surface"]
plt.rcParams["savefig.facecolor"] = COLORS["surface"]
plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]

logger = logging.getLogger(__name__)
FINLAND_TZ = ZoneInfo("Europe/Helsinki")


class ElectricityPriceApp:
    APP_DIR = Path(__file__).resolve().parent
    CONFIG_FILE = APP_DIR / "data.ini"
    CACHE_FILE = APP_DIR / "data.dat"

    # Jatkuva kulutus, kW (= kWh yhden tunnin aikana)
    CONSUMPTION_KW = 1.0

    def __init__(self, root):
        self.root = root
        self.root.title("Sähkön hinnat - GUI")
        self.root.configure(bg=COLORS["bg"])
        self.root.minsize(900, 650)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ElectricityPriceApp/7"})
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.refresh_job = None
        self.fetch_in_progress = False
        self.last_data = []

        self.load_config()

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure(
            "TLabel",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "TButton",
            background=COLORS["primary"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", COLORS["primary_hover"])],
            foreground=[("disabled", COLORS["muted"]), ("active", "white")],
        )
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            rowheight=28,
            fieldbackground=COLORS["surface"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["selection"])],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["header"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview.Heading",
            background=[("active", COLORS["selection"])],
        )

        # Input-rivi
        input_frame = ttk.Frame(root)
        input_frame.pack(padx=10, pady=5, fill="x")

        ttk.Label(input_frame, text="Hakupäivä:").grid(row=0, column=0, sticky="w")
        self.date_entry = DateEntry(
            input_frame,
            width=12,
            background=COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd",
        )
        self.date_entry.grid(row=0, column=1, padx=5)

        ttk.Label(input_frame, text="Tunnit (1-48):").grid(
            row=0, column=2, sticky="w"
        )
        self.hours_spinbox = ttk.Spinbox(input_frame, from_=1, to=48, width=5)
        self.hours_spinbox.set(23)
        self.hours_spinbox.grid(row=0, column=3, padx=5)

        ttk.Label(input_frame, text="Hintatyyppi:").grid(
            row=0, column=4, sticky="w"
        )
        self.price_type = ttk.Combobox(
            input_frame, values=["halpa", "kallis"], width=7, state="readonly"
        )
        self.price_type.set("halpa")
        self.price_type.grid(row=0, column=5, padx=5)

        ttk.Label(input_frame, text="Tulosmuoto:").grid(
            row=0, column=6, sticky="w"
        )
        self.result_type = ttk.Combobox(
            input_frame, values=["haja", "sarja"], width=7, state="readonly"
        )
        self.result_type.set("sarja")
        self.result_type.grid(row=0, column=7, padx=5)

        # Kuluva tunti -infolaatikko. Teksti käyttää kahta riviä.
        self.current_label = ttk.Label(
            input_frame,
            text="Kuluva tunti: -- €/h\n(API -- € + siirto -- € + myynti -- €)",
            font=("Segoe UI", 12, "bold"),
            foreground=COLORS["primary"],
            justify="left",
        )
        self.current_label.grid(row=0, column=8, padx=20, sticky="w")

        self.search_button = ttk.Button(
            input_frame, text="Hae hinnat", command=self.update_table
        )
        self.search_button.grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(
            input_frame, text="Tallenna CSV", command=self.save_to_csv
        ).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(
            input_frame, text="Asetukset", command=self.open_settings_window
        ).grid(row=1, column=2, padx=5, pady=5)

        # Taulukko
        self.tree = ttk.Treeview(
            root,
            columns=("Aikaleima", "API-hinta", "Myynnin hinta", "Siirron hinta", "Hinta"),
            show="headings",
        )
        self.tree.heading("Aikaleima", text="Aikaleima (Suomi)")
        self.tree.heading("API-hinta", text="API-hinta €/h")
        self.tree.heading("Myynnin hinta", text="Myynnin hinta €/h")
        self.tree.heading("Siirron hinta", text="Siirron hinta €/h")
        self.tree.heading(
            "Hinta", text=f"Kustannus €/h ({self.CONSUMPTION_KW:g} kW)"
        )
        self.tree.column("Aikaleima", width=180, minwidth=150, anchor="w")
        self.tree.column("API-hinta", width=110, minwidth=95, anchor="e")
        self.tree.column("Myynnin hinta", width=125, minwidth=105, anchor="e")
        self.tree.column("Siirron hinta", width=125, minwidth=105, anchor="e")
        self.tree.column("Hinta", width=140, minwidth=120, anchor="e")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Kaavio
        self.figure, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.root.bind("<Return>", lambda _event: self.update_table())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_table()

    def load_config(self):
        """Lukee JSON-muotoisen data.ini-tiedoston."""
        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as file:
                cfg = json.load(file)

            sales = cfg["sahkon_myynti"]
            transfer = cfg["sahkon_siirto"]

            self.tax_multiplier = float(sales["vero"])
            self.margin_eur_kwh = float(sales["marginaali"])
            self.sales_monthly_fee = float(sales["kk_maksu"])
            self.transfer_eur_kwh = float(transfer["siirto"])
            self.electricity_tax_eur_kwh = float(transfer["sahkovero"])
            self.transfer_monthly_fee = float(transfer["kk_maksu"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror(
                "Asetusvirhe",
                "data.ini-tiedoston lukeminen epäonnistui. "
                "Tarkista JSON-rakenne ja arvot.\n\n"
                f"Virhe: {error}",
            )
            raise

    def open_settings_window(self):
        """Avaa data.ini-tiedoston arvojen ylläpitoikkunan."""
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as file:
                cfg = json.load(file)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror(
                "Asetusvirhe",
                f"data.ini-tiedoston lukeminen epäonnistui:\n\n{error}",
            )
            return

        settings = tk.Toplevel(self.root)
        self.settings_window = settings
        settings.title("data.ini-asetusten ylläpito")
        settings.configure(bg=COLORS["bg"])
        settings.resizable(False, False)
        settings.transient(self.root)
        settings.grab_set()

        container = ttk.Frame(settings, padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(1, weight=1)

        field_definitions = [
            ("sales_tax", "ALV-kerroin", "Verollisen hinnan kerroin, esimerkiksi 1.255", ("sahkon_myynti", "vero")),
            ("sales_margin", "Myyntimarginaali (€/kWh)", "Sähkönmyyjän energiamarginaali kilowattitunnilta", ("sahkon_myynti", "marginaali")),
            ("sales_monthly_fee", "Myynnin kuukausimaksu (€)", "Sähkönmyyntisopimuksen kiinteä kuukausimaksu", ("sahkon_myynti", "kk_maksu")),
            ("transfer_monthly_fee", "Siirron kuukausimaksu (€)", "Sähkönsiirron kiinteä kuukausimaksu", ("sahkon_siirto", "kk_maksu")),
            ("transfer_price", "Siirtohinta (€/kWh)", "Sähkönsiirron hinta kilowattitunnilta", ("sahkon_siirto", "siirto")),
            ("electricity_tax", "Sähkövero (€/kWh)", "Sähköveron määrä kilowattitunnilta", ("sahkon_siirto", "sahkovero")),
        ]

        entries = {}
        current_section = None
        row = 0
        section_titles = {
            "sahkon_myynti": "Sähkön myynti",
            "sahkon_siirto": "Sähkön siirto",
        }

        for key, label, description, path in field_definitions:
            if path[0] != current_section:
                if current_section is not None:
                    ttk.Separator(container, orient="horizontal").grid(
                        row=row, column=0, columnspan=2, sticky="ew", pady=10
                    )
                    row += 1
                current_section = path[0]
                ttk.Label(
                    container,
                    text=section_titles[current_section],
                    font=("Segoe UI", 12, "bold"),
                    foreground=COLORS["primary"],
                ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
                row += 1

            label_frame = ttk.Frame(container)
            label_frame.grid(row=row, column=0, padx=(0, 18), pady=6, sticky="w")
            ttk.Label(label_frame, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(
                label_frame,
                text=description,
                foreground=COLORS["muted"],
                wraplength=360,
            ).pack(anchor="w")

            variable = tk.StringVar(value=str(cfg[path[0]][path[1]]))
            ttk.Entry(container, textvariable=variable, width=22).grid(
                row=row, column=1, padx=(0, 4), pady=6, sticky="ew"
            )
            entries[key] = (variable, path, label)
            row += 1

        button_frame = ttk.Frame(container)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))

        def close_settings():
            settings.grab_release()
            settings.destroy()

        def save_settings():
            values = {}
            invalid_fields = []
            for key, (variable, path, label) in entries.items():
                raw_value = variable.get().strip().replace(",", ".")
                try:
                    value = float(raw_value)
                    if value < 0 or value != value or value in (float("inf"), float("-inf")):
                        raise ValueError
                    if key == "sales_tax" and value == 0:
                        raise ValueError
                    values[key] = value
                except ValueError:
                    invalid_fields.append(label)

            if invalid_fields:
                messagebox.showerror(
                    "Virheelliset arvot",
                    "Anna seuraaviin kenttiin kelvollinen ei-negatiivinen numero:\n\n"
                    + "\n".join(f"• {label}" for label in invalid_fields),
                    parent=settings,
                )
                return

            for key, value in values.items():
                _variable, path, _label = entries[key]
                cfg[path[0]][path[1]] = value

            temporary_file = self.CONFIG_FILE + ".tmp"
            try:
                with open(temporary_file, "w", encoding="utf-8") as file:
                    json.dump(cfg, file, ensure_ascii=False, indent=4)
                    file.write("\n")
                os.replace(temporary_file, self.CONFIG_FILE)
                self.load_config()
                self.update_table()
            except Exception as error:
                if os.path.exists(temporary_file):
                    os.remove(temporary_file)
                messagebox.showerror(
                    "Tallennusvirhe",
                    f"Asetusten tallentaminen epäonnistui:\n\n{error}",
                    parent=settings,
                )
                return

            messagebox.showinfo(
                "Asetukset tallennettu",
                "data.ini päivitettiin ja uudet arvot otettiin käyttöön.",
                parent=settings,
            )
            close_settings()

        ttk.Button(button_frame, text="Peruuta", command=close_settings).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(button_frame, text="Tallenna", command=save_settings).pack(side="right")
        settings.protocol("WM_DELETE_WINDOW", close_settings)
        settings.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - settings.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - settings.winfo_height()) // 2
        settings.geometry(f"+{max(0, x)}+{max(0, y)}")

    @staticmethod
    def parse_timestamp(value):
        """Jäsentää API-aikaleiman Suomen aikaan."""
        timestamp = datetime.datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=FINLAND_TZ)
        return timestamp.astimezone(FINLAND_TZ)

    @staticmethod
    def hours_in_local_month(timestamp):
        """Palauttaa kuukauden todellisten paikallisten tuntien määrän."""
        start = datetime.datetime(timestamp.year, timestamp.month, 1, tzinfo=FINLAND_TZ)
        if timestamp.month == 12:
            end = datetime.datetime(timestamp.year + 1, 1, 1, tzinfo=FINLAND_TZ)
        else:
            end = datetime.datetime(timestamp.year, timestamp.month + 1, 1, tzinfo=FINLAND_TZ)
        duration = end.astimezone(datetime.timezone.utc) - start.astimezone(datetime.timezone.utc)
        return duration.total_seconds() / 3600

    def calculate_hourly_breakdown(self, entry):
        """Palauttaa API-, siirto- ja myyntikustannuksen euroina tunnilta."""
        timestamp = self.parse_timestamp(entry["aikaleima_suomi"])
        hours_in_month = self.hours_in_local_month(timestamp)
        consumption_kwh = self.CONSUMPTION_KW  # yhden tunnin kulutus

        api_eur_kwh = float(entry["hinta"]) * self.tax_multiplier / 100
        api_cost = api_eur_kwh * consumption_kwh

        transfer_variable = (
            self.transfer_eur_kwh + self.electricity_tax_eur_kwh
        ) * consumption_kwh
        transfer_fixed = self.transfer_monthly_fee / hours_in_month

        sales_variable = self.margin_eur_kwh * consumption_kwh
        sales_fixed = self.sales_monthly_fee / hours_in_month

        return api_cost, transfer_variable + transfer_fixed, sales_variable + sales_fixed

    def calculate_hourly_components(self, entry):
        api_cost, transfer_cost, sales_cost = self.calculate_hourly_breakdown(entry)
        return api_cost + sales_cost, transfer_cost

    def collect_request(self):
        """Kerää ja validoi hakuehdot Tkinterin pääsäikeessä."""
        try:
            hours = int(self.hours_spinbox.get())
        except ValueError as error:
            raise ValueError("Tuntimäärän pitää olla kokonaisluku.") from error
        if not 1 <= hours <= 48:
            raise ValueError("Tuntimäärän pitää olla välillä 1–48.")

        selected_date = self.date_entry.get_date()
        now = datetime.datetime.now(FINLAND_TZ)
        center = datetime.datetime.combine(
            selected_date, datetime.time(now.hour, 0), tzinfo=FINLAND_TZ
        )
        start_time = center - datetime.timedelta(hours=12)
        end_time = center + datetime.timedelta(hours=12)

        return {
            "hours": hours,
            "result_type": self.result_type.get(),
            "price_type": self.price_type.get(),
            "start": start_time,
            "end": end_time,
        }

    @staticmethod
    def validate_price_data(data):
        """Validoi API- tai välimuistidatan rakenteen ja arvot."""
        if not isinstance(data, list):
            raise ValueError("Hintadata ei ole lista.")

        validated = []
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise ValueError(f"Hintarivi {index + 1} ei ole objekti.")
            if "aikaleima_suomi" not in entry or "hinta" not in entry:
                raise ValueError(f"Hintariviltä {index + 1} puuttuu vaadittu kenttä.")
            ElectricityPriceApp.parse_timestamp(str(entry["aikaleima_suomi"]))
            price = float(entry["hinta"])
            if not math.isfinite(price):
                raise ValueError(f"Hintarivin {index + 1} hinta ei ole kelvollinen.")
            validated.append({**entry, "hinta": price})
        return validated

    def fetch_prices(self, request):
        """Hakee hinnat. Tätä metodia kutsutaan taustasäikeessä."""
        aikaraja = (
            f"{request['start'].strftime('%Y-%m-%dT%H:%M')}_"
            f"{request['end'].strftime('%Y-%m-%dT%H:%M')}"
        )
        params = {
            "tunnit": request["hours"],
            "tulos": request["result_type"],
            "aikaraja": aikaraja,
        }
        url = f"https://www.sahkohinta-api.fi/api/v1/{request['price_type']}"

        try:
            response = self.session.get(url, params=params, timeout=(5, 20))
            if response.status_code == 204 or not response.text.strip():
                raise ValueError("API palautti tyhjän vastauksen.")
            response.raise_for_status()
            data = self.validate_price_data(response.json())
            self.save_backup_data(data, request)
            return data, False, None
        except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning("API-haku epäonnistui: %s", error)
            cached = self.load_backup_data(request)
            if cached:
                return cached, True, str(error)
            raise RuntimeError(f"Hintojen hakeminen epäonnistui: {error}") from error

    def update_current_price(self, data):
        now = datetime.datetime.now(FINLAND_TZ).replace(minute=0, second=0, microsecond=0)
        for entry in data:
            entry_time = self.parse_timestamp(entry["aikaleima_suomi"]).replace(
                minute=0, second=0, microsecond=0
            )
            if entry_time == now:
                api_cost, transfer_cost, sales_cost = self.calculate_hourly_breakdown(entry)
                total = api_cost + transfer_cost + sales_cost
                self.current_label.config(
                    text=(
                        f"Kuluva tunti: {total:.3f} €/h\n"
                        f"(API {api_cost:.3f} € + siirto {transfer_cost:.3f} € + "
                        f"myynti {sales_cost:.3f} €)"
                    )
                )
                return
        self.current_label.config(
            text="Kuluva tunti: -- €/h\n(API -- € + siirto -- € + myynti -- €)"
        )

    def update_table(self):
        if self.fetch_in_progress:
            return
        try:
            request = self.collect_request()
        except ValueError as error:
            messagebox.showerror("Virheellinen hakuehto", str(error), parent=self.root)
            return

        self.fetch_in_progress = True
        self.search_button.state(["disabled"])
        self.current_label.config(text="Haetaan hintatietoja...")
        future = self.executor.submit(self.fetch_prices, request)
        future.add_done_callback(lambda task: self.root.after(0, self.finish_update, task))

    def finish_update(self, future):
        self.fetch_in_progress = False
        self.search_button.state(["!disabled"])
        try:
            data, from_cache, api_error = future.result()
        except Exception as error:
            logger.exception("Hintojen päivitys epäonnistui")
            messagebox.showerror("Hakuvirhe", str(error), parent=self.root)
            self.schedule_refresh()
            return

        self.last_data = data
        self.render_data(data)
        if from_cache:
            messagebox.showwarning(
                "Välimuistitiedot käytössä",
                "API-haku epäonnistui. Näytetään samaa hakua vastaava paikallinen "
                f"välimuisti.\n\nAPI-virhe: {api_error}",
                parent=self.root,
            )
        self.schedule_refresh()

    def render_data(self, data):
        for row in self.tree.get_children():
            self.tree.delete(row)
        if not data:
            self.update_current_price([])
            self.draw_chart([])
            return

        now = datetime.datetime.now(FINLAND_TZ).replace(minute=0, second=0, microsecond=0)
        for entry in data:
            entry_time = self.parse_timestamp(entry["aikaleima_suomi"]).replace(
                minute=0, second=0, microsecond=0
            )
            api_cost, transfer_cost, sales_cost = self.calculate_hourly_breakdown(entry)
            hourly_cost = api_cost + sales_cost + transfer_cost
            tag = "current_hour" if entry_time == now else ""
            self.tree.insert(
                "", "end",
                values=(
                    entry["aikaleima_suomi"], f"{api_cost:.4f}", f"{sales_cost:.4f}",
                    f"{transfer_cost:.4f}", f"{hourly_cost:.4f}",
                ),
                tags=(tag,),
            )

        self.tree.tag_configure(
            "current_hour", background=COLORS["selection"], foreground=COLORS["text"]
        )
        self.update_current_price(data)
        self.draw_chart(data)

    def schedule_refresh(self):
        if self.refresh_job is not None:
            try:
                self.root.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
        self.refresh_job = self.root.after(1_200_000, self.update_table)

    def draw_chart(self, data):
        """Piirtää tuntihinnat pinottuna: sähkön myynti + sähkön siirto."""
        self.ax.clear()
        if not data:
            self.ax.set_title("Ei näytettäviä hintatietoja", color=COLORS["text"])
            self.canvas.draw_idle()
            return

        now = datetime.datetime.now(FINLAND_TZ).replace(minute=0, second=0, microsecond=0)
        active_index = None
        for index, entry in enumerate(data):
            entry_time = self.parse_timestamp(entry["aikaleima_suomi"]).replace(
                minute=0, second=0, microsecond=0
            )
            if entry_time == now:
                active_index = index
                break

        if active_index is None:
            active_index = 0
        start = max(0, active_index - 6)
        end = min(len(data), active_index + 12)
        window = data[start:end]
        time_labels = [
            self.parse_timestamp(entry["aikaleima_suomi"]).strftime("%H:%M")
            for entry in window
        ]
        x_positions = list(range(len(window)))

        sales_costs, transfer_costs = [], []
        for entry in window:
            sales, transfer = self.calculate_hourly_components(entry)
            sales_costs.append(sales)
            transfer_costs.append(transfer)

        bars_sales = self.ax.bar(
            x_positions,
            sales_costs,
            color=COLORS["primary"],
            label="Sähkön myynti",
        )
        bars_transfer = self.ax.bar(
            x_positions,
            transfer_costs,
            bottom=sales_costs,
            color=COLORS["secondary"],
            label="Sähkön siirto",
        )
        self.ax.set_xticks(x_positions)
        self.ax.set_xticklabels(time_labels)
        self.ax.yaxis.set_major_locator(ticker.MultipleLocator(0.10))
        self.ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.05))
        self.ax.grid(which="major", color=COLORS["grid"], linewidth=0.8, alpha=0.8)
        self.ax.grid(which="minor", color=COLORS["grid"], linewidth=0.4, alpha=0.6)
        self.ax.set_axisbelow(True)

        for index, (sales_bar, transfer_bar, entry) in enumerate(zip(bars_sales, bars_transfer, window)):
            hourly_cost = sales_costs[index] + transfer_costs[index]
            entry_time = self.parse_timestamp(entry["aikaleima_suomi"]).replace(
                minute=0, second=0, microsecond=0
            )
            is_active = entry_time == now
            self.ax.annotate(
                f"{hourly_cost:.3f} €/h\n{hourly_cost * 24:.2f} € / 24 h*",
                xy=(sales_bar.get_x() + sales_bar.get_width() / 2, hourly_cost),
                xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                fontsize=8, color=COLORS["accent"] if is_active else COLORS["muted"],
            )
            if is_active:
                sales_bar.set_facecolor(COLORS["accent_dark"])
                transfer_bar.set_facecolor(COLORS["accent"])

        legend = self.ax.legend(
            loc="upper left", facecolor=COLORS["surface"],
            edgecolor=COLORS["border"], framealpha=1.0
        )
        for legend_text in legend.get_texts():
            legend_text.set_color(COLORS["text"])
        self.ax.set_ylabel("Kokonaiskustannus (€/h)", color=COLORS["text"])
        self.ax.set_title(
            f"Sähkön kokonaiskustannus ({self.CONSUMPTION_KW:g} kW kulutus)\n"
            "* 24 h samalla tuntihinnalla",
            color=COLORS["text"], fontsize=12, fontweight="bold",
        )
        self.ax.tick_params(axis="x", rotation=45, colors=COLORS["text"])
        self.ax.tick_params(axis="y", colors=COLORS["text"])
        self.figure.tight_layout()
        self.canvas.draw_idle()

    @staticmethod
    def request_signature(request):
        return {
            "hours": request["hours"],
            "result_type": request["result_type"],
            "price_type": request["price_type"],
            "start": request["start"].isoformat(),
            "end": request["end"].isoformat(),
        }

    def save_backup_data(self, data, request):
        payload = {
            "saved_at": datetime.datetime.now(FINLAND_TZ).isoformat(),
            "request": self.request_signature(request),
            "data": data,
        }
        temporary_file = self.CACHE_FILE.with_suffix(self.CACHE_FILE.suffix + ".tmp")
        try:
            with temporary_file.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary_file, self.CACHE_FILE)
            logger.info("Välimuisti tallennettu: %s", self.CACHE_FILE)
        except OSError as error:
            logger.warning("Välimuistin tallennus epäonnistui: %s", error)
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                pass

    def load_backup_data(self, request):
        if not self.CACHE_FILE.exists():
            return []
        try:
            with self.CACHE_FILE.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, dict):
                return []
            if payload.get("request") != self.request_signature(request):
                logger.info("Välimuisti ei vastaa nykyistä hakua.")
                return []
            return self.validate_price_data(payload.get("data"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning("Välimuistin luku epäonnistui: %s", error)
            return []

    def save_to_csv(self):
        data = [tuple(self.tree.item(row)["values"]) for row in self.tree.get_children()]
        if not data:
            messagebox.showinfo("Ei tallennettavaa", "Taulukossa ei ole tallennettavia tietoja.")
            return

        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="Tallenna CSV",
            defaultextension=".csv",
            filetypes=[("CSV-tiedosto", "*.csv")],
            initialfile="sahkohinnat.csv",
        )
        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow([
                    "Aikaleima", "API-hinta €/h", "Myynnin hinta €/h",
                    "Siirron hinta €/h", f"Kustannus €/h ({self.CONSUMPTION_KW:g} kW)",
                ])
                writer.writerows(data)
            messagebox.showinfo("Tallennettu", f"Tiedot tallennettu tiedostoon:\n{filename}")
        except OSError as error:
            messagebox.showerror("Virhe", f"Virhe tallennettaessa tiedostoa: {error}")

    def on_close(self):
        if self.refresh_job is not None:
            try:
                self.root.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
        self.session.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        plt.close(self.figure)
        self.root.destroy()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root = tk.Tk()
    app = ElectricityPriceApp(root)
    root.mainloop()
