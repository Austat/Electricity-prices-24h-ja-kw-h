import calendar
import csv
import datetime
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

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
plt.rcParams["font.family"] = "Segoe UI"


class ElectricityPriceApp:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.ini")

    # Jatkuva kulutus, kW (= kWh yhden tunnin aikana)
    CONSUMPTION_KW = 1.0

    def __init__(self, root):
        self.root = root
        self.root.title("Sähkön hinnat - GUI")
        self.root.configure(bg=COLORS["bg"])

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
            input_frame, values=["halpa", "kallis"], width=7
        )
        self.price_type.set("halpa")
        self.price_type.grid(row=0, column=5, padx=5)

        ttk.Label(input_frame, text="Tulosmuoto:").grid(
            row=0, column=6, sticky="w"
        )
        self.result_type = ttk.Combobox(
            input_frame, values=["haja", "sarja"], width=7
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

        ttk.Button(
            input_frame, text="Hae hinnat", command=self.update_table
        ).grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(
            input_frame, text="Tallenna CSV", command=self.save_to_csv
        ).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(
            input_frame, text="Asetukset", command=self.open_settings_window
        ).grid(row=1, column=2, padx=5, pady=5)

        # Taulukko
        self.tree = ttk.Treeview(
            root, columns=("Aikaleima", "Hinta"), show="headings"
        )
        self.tree.heading("Aikaleima", text="Aikaleima (Suomi)")
        self.tree.heading(
            "Hinta", text=f"Kustannus €/h ({self.CONSUMPTION_KW:g} kW)"
        )
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Kaavio
        self.figure, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

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

    def monthly_fee_per_hour(self, timestamp):
        """Muuntaa kyseisen kuukauden kuukausimaksut euroiksi per tunti."""
        days_in_month = calendar.monthrange(timestamp.year, timestamp.month)[1]
        total_monthly_fee = self.sales_monthly_fee + self.transfer_monthly_fee
        return total_monthly_fee / days_in_month / 24

    def calculate_hourly_breakdown(self, entry):
        """Palauttaa API-, siirto- ja myyntiosuuden euroina per tunti."""
        timestamp = datetime.datetime.fromisoformat(entry["aikaleima_suomi"])
        days_in_month = calendar.monthrange(timestamp.year, timestamp.month)[1]

        # API-hinta verollisena. API:n hinta muunnetaan senteistä euroiksi.
        taxable_api_price = float(entry["hinta"] * self.tax_multiplier) / 100

        # Sähkön siirto sisältää siirtohinnan, sähköveron ja siirron kk-maksun.
        transfer_monthly_fee = self.transfer_monthly_fee / days_in_month / 24
        electricity_transfer = (
            self.transfer_eur_kwh
            + self.electricity_tax_eur_kwh
            + transfer_monthly_fee
        )

        # Sähkön myyntiosuus sisältää marginaalin ja myynnin kk-maksun.
        sales_monthly_fee = self.sales_monthly_fee / days_in_month / 24
        electricity_sales = self.margin_eur_kwh + sales_monthly_fee

        return taxable_api_price, electricity_transfer, electricity_sales

    def calculate_hourly_components(self, entry):
        """Palauttaa kustannuksen jaettuna myyntiin ja siirtoon."""
        api_price, electricity_transfer, electricity_sales = (
            self.calculate_hourly_breakdown(entry)
        )
        total_sales = api_price + electricity_sales
        return total_sales, electricity_transfer

    def calculate_hourly_cost(self, entry):
        api_price, electricity_transfer, electricity_sales = (
            self.calculate_hourly_breakdown(entry)
        )
        total = api_price + electricity_transfer + electricity_sales

        print(
            f"{entry['aikaleima_suomi']} | "
            f"API {api_price:.6f} + "
            f"siirto {electricity_transfer:.6f} + "
            f"myynti {electricity_sales:.6f} = "
            f"{total:.9f}"
        )
        return total

    def fetch_prices(self):
        selected_date = self.date_entry.get_date()
        now = datetime.datetime.now()
        start_time_a = datetime.datetime.combine(
            selected_date, datetime.time(now.hour, 0)
        )
        start_time = start_time_a - datetime.timedelta(hours=12)
        end_time = start_time_a + datetime.timedelta(hours=12)

        aikaraja = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M')}_"
            f"{end_time.strftime('%Y-%m-%dT%H:%M')}"
        )

        print(
            f"{start_time.strftime('%Y-%m-%dT%H:%M')} - "
            f"{end_time.strftime('%Y-%m-%dT%H:%M')}"
        )

        params = {
            "tunnit": self.hours_spinbox.get(),
            "tulos": self.result_type.get(),
            "aikaraja": aikaraja,
        }
        url = f"https://www.sahkohinta-api.fi/api/v1/{self.price_type.get()}"

        try:
            response = requests.get(url, params=params, timeout=20)
            if response.status_code == 204 or not response.text.strip():
                print("API palautti tyhjän vastauksen -> käytetään data.dat")
                return self.load_backup_data()

            response.raise_for_status()
            data = response.json()
            self.save_backup_data(data)
            return data
        except Exception as error:
            print("Virhe API-haussa:", error)
            return self.load_backup_data()

    def update_current_price(self, data):
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        for entry in data:
            entry_time = datetime.datetime.fromisoformat(
                entry["aikaleima_suomi"]
            ).replace(minute=0, second=0, microsecond=0)

            if entry_time == now:
                api_price, electricity_transfer, electricity_sales = (
                    self.calculate_hourly_breakdown(entry)
                )
                hourly_cost = api_price + electricity_transfer + electricity_sales

                self.current_label.config(
                    text=(
                        f"Kuluva tunti: {hourly_cost:.3f} €/h\n"
                        f"(API {api_price:.3f} € + "
                        f"siirto {electricity_transfer:.3f} € + "
                        f"myynti {electricity_sales:.3f} €)"
                    )
                )
                return

        self.current_label.config(
            text="Kuluva tunti: -- €/h\n(API -- € + siirto -- € + myynti -- €)"
        )

    def update_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        data = self.fetch_prices()
        if not data:
            return

        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        for entry in data:
            entry_time = datetime.datetime.fromisoformat(
                entry["aikaleima_suomi"]
            ).replace(minute=0, second=0, microsecond=0)
            hourly_cost = self.calculate_hourly_cost(entry)
            tag = "current_hour" if entry_time == now else ""

            self.tree.insert(
                "",
                "end",
                values=(entry["aikaleima_suomi"], f"{hourly_cost:.4f}"),
                tags=(tag,),
            )

        self.tree.tag_configure(
            "current_hour",
            background=COLORS["selection"],
            foreground=COLORS["text"],
        )

        self.update_current_price(data)
        self.draw_chart(data)

        # Päivitä 20 minuutin välein. Estä päällekkäiset ajastimet.
        if hasattr(self, "refresh_job"):
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(1200000, self.update_table)

    def draw_chart(self, data):
        """Piirtää tuntihinnat pinottuna: sähkön myynti + sähkön siirto."""
        self.ax.clear()
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
        active_index = None

        for index, entry in enumerate(data):
            entry_time = datetime.datetime.fromisoformat(
                entry["aikaleima_suomi"]
            ).replace(minute=0, second=0, microsecond=0)
            if entry_time == now:
                active_index = index
                break

        if active_index is None:
            active_index = len(data) - 1

        start = max(0, active_index - 6)
        end = min(len(data), active_index + 12)
        window = data[start:end]

        times = [entry["aikaleima_suomi"][-5:] for entry in window]
        sales_costs = []
        transfer_costs = []

        for entry in window:
            sales, transfer = self.calculate_hourly_components(entry)
            sales_costs.append(sales)
            transfer_costs.append(transfer)

        bars_sales = self.ax.bar(
            times,
            sales_costs,
            color=COLORS["primary"],
            label="Sähkön myynti",
        )
        bars_transfer = self.ax.bar(
            times,
            transfer_costs,
            bottom=sales_costs,
            color=COLORS["secondary"],
            label="Sähkön siirto",
        )

        self.ax.yaxis.set_major_locator(ticker.MultipleLocator(0.10))
        self.ax.grid(
            which="major",
            color=COLORS["grid"],
            linestyle="-",
            linewidth=0.8,
            alpha=0.8,
        )
        self.ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.05))
        self.ax.grid(
            which="minor",
            color=COLORS["grid"],
            linestyle="-",
            linewidth=0.4,
            alpha=0.6,
        )
        self.ax.set_axisbelow(True)

        for index, (sales_bar, transfer_bar, entry) in enumerate(
            zip(bars_sales, bars_transfer, window)
        ):
            hourly_cost = sales_costs[index] + transfer_costs[index]
            daily_cost = hourly_cost * 24
            entry_time = datetime.datetime.fromisoformat(
                entry["aikaleima_suomi"]
            ).replace(minute=0, second=0, microsecond=0)
            is_active = entry_time == now
            text_color = COLORS["accent"] if is_active else COLORS["muted"]

            self.ax.annotate(
                f"{hourly_cost:.3f} €/h\n"
                f"{daily_cost:.2f} €/24h\n"
                f"({self.CONSUMPTION_KW:g} kW)",
                xy=(
                    sales_bar.get_x() + sales_bar.get_width() / 2,
                    hourly_cost,
                ),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                color=text_color,
            )

            if is_active:
                sales_bar.set_facecolor(COLORS["accent_dark"])
                transfer_bar.set_facecolor(COLORS["accent"])

        legend = self.ax.legend(
            loc="upper left",
            facecolor=COLORS["surface"],
            edgecolor=COLORS["border"],
            framealpha=1.0,
        )
        for legend_text in legend.get_texts():
            legend_text.set_color(COLORS["text"])

        self.ax.set_ylabel("Kokonaiskustannus (€/h)", color=COLORS["text"])
        self.ax.set_title(
            f"Sähkön kokonaiskustannus ({self.CONSUMPTION_KW:g} kW kulutus)",
            color=COLORS["text"],
            fontsize=13,
            fontweight="bold",
        )
        self.ax.tick_params(axis="x", rotation=45, colors=COLORS["text"])
        self.ax.tick_params(axis="y", colors=COLORS["text"])
        self.figure.tight_layout()
        self.canvas.draw()

    def save_backup_data(self, data):
        try:
            with open("data.dat", "w", encoding="utf-8") as file:
                json.dump(data, file)
            print("Varmuuskopio tallennettu data.dat")
        except Exception as error:
            print("Varmuuskopion tallennus epäonnistui:", error)

    def load_backup_data(self):
        if not os.path.exists("data.dat"):
            print("Varmuuskopiota ei ole olemassa.")
            return []

        try:
            with open("data.dat", "r", encoding="utf-8") as file:
                data = json.load(file)
            print("Luettiin varmuuskopio data.dat")
            return data
        except Exception as error:
            print("Varmuuskopion luku epäonnistui:", error)
            return []

    def save_to_csv(self):
        data = [
            (
                self.tree.item(row)["values"][0],
                self.tree.item(row)["values"][1],
            )
            for row in self.tree.get_children()
        ]

        try:
            with open(
                "sahkohinnat.csv", "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Aikaleima",
                        f"Kustannus €/h ({self.CONSUMPTION_KW:g} kW)",
                    ]
                )
                writer.writerows(data)

            messagebox.showinfo(
                "Tallennettu",
                "Tiedot tallennettu tiedostoon sahkohinnat.csv",
            )
        except Exception as error:
            messagebox.showerror(
                "Virhe", f"Virhe tallennettaessa tiedostoa: {error}"
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = ElectricityPriceApp(root)
    root.mainloop()
