import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import requests
import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv

# Tumma teema matplotlibille
plt.rcParams["axes.facecolor"] = "#0e2147"
plt.rcParams["figure.facecolor"] = "#091224"


class ElectricityPriceApp:
    def __init__(self, root):

        self.root = root
        self.root.title("Sähkön hinnat - GUI")
        self.root.configure(bg="#2E2E2E")

        # --- LUE ALV JA MARGINAALI ---
        with open("data.ini", "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
            self.vALV = float(lines[0])
            self.vMarginal = float(lines[1])

        # --- TYYLI ---
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#2E2E2E")
        style.configure("TLabel", background="#2E2E2E", foreground="white")
        style.configure("TButton", background="#555555", foreground="white", font=("Arial", 10, "bold"))
        style.configure("Treeview", background="#3E3E3E", foreground="white",
                        rowheight=25, fieldbackground="#3E3E3E")
        style.configure("Treeview.Heading", background="#555555", foreground="white",
                        font=("Arial", 10, "bold"))

        # --- INPUT-RIVI ---
        input_frame = ttk.Frame(root)
        input_frame.pack(padx=10, pady=5, fill='x')

        ttk.Label(input_frame, text="Hakupäivä:").grid(row=0, column=0, sticky='w')
        self.date_entry = DateEntry(input_frame, width=12, background="black", foreground="white",
                                    borderwidth=2, date_pattern="yyyy-mm-dd")
        self.date_entry.grid(row=0, column=1, padx=5)

        ttk.Label(input_frame, text="Tunnit (1-48):").grid(row=0, column=2, sticky='w')
        self.hours_spinbox = ttk.Spinbox(input_frame, from_=1, to=48, width=5)
        self.hours_spinbox.set(24)
        self.hours_spinbox.grid(row=0, column=3, padx=5)

        ttk.Label(input_frame, text="Hintatyyppi:").grid(row=0, column=4, sticky='w')
        self.price_type = ttk.Combobox(input_frame, values=["halpa", "kallis"], width=7)
        self.price_type.set("halpa")
        self.price_type.grid(row=0, column=5, padx=5)

        ttk.Label(input_frame, text="Tulosmuoto:").grid(row=0, column=6, sticky='w')
        self.result_type = ttk.Combobox(input_frame, values=["haja", "sarja"], width=7)
        self.result_type.set("sarja")
        self.result_type.grid(row=0, column=7, padx=5)

        # Kuluva tunti - infolaatikko
        self.current_label = ttk.Label(
            input_frame,
            text="Kuluva tunti: -- snt/kWh",
            font=("Arial", 16, "bold"),
            foreground="#45c4ff"
        )
        self.current_label.grid(row=0, column=8, padx=20, sticky="w")

        # Napit
        ttk.Button(input_frame, text="Hae hinnat", command=self.update_table).grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(input_frame, text="Tallenna CSV", command=self.save_to_csv).grid(row=1, column=1, padx=5, pady=5)

        # --- TAULUKKO ---
        self.tree = ttk.Treeview(root, columns=("Aikaleima", "Hinta"), show="headings")
        self.tree.heading("Aikaleima", text="Aikaleima (Suomi)")
        self.tree.heading("Hinta", text="Hinta (snt/kWh)")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # --- KAAVIO ---
        self.figure, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.update_table()

    # ----------------------------------------------------------------------

    def fetch_prices(self):
        date = self.date_entry.get_date()
        
        #start_time_a = datetime.datetime.combine(date, datetime.time(0, 0))
        selected_date = self.date_entry.get_date()   # palauttaa date-olion
        now = datetime.datetime.now()

        start_time_a = datetime.datetime.combine(
            selected_date,
            datetime.time(now.hour, 0)
        )
        
        start_time = start_time_a - datetime.timedelta(hours=12)
        end_time = start_time_a + datetime.timedelta(hours=12)

        aikaraja = f"{start_time.strftime('%Y-%m-%dT%H:%M')}_{end_time.strftime('%Y-%m-%dT%H:%M')}"


        print (f"{start_time.strftime('%Y-%m-%dT%H:%M')} - {end_time.strftime('%Y-%m-%dT%H:%M')}")
        
        params = {
            "tunnit": self.hours_spinbox.get(),
            "tulos": self.result_type.get(),
            "aikaraja": aikaraja
        }
        url = f"https://www.sahkohinta-api.fi/api/v1/{self.price_type.get()}"
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            messagebox.showerror("Virhe", f"Virhe haettaessa dataa: {e}")
            return []

##    def fetch_prices(self):
##        """
##        Hakee aina vain tämän päivän julkaistut tunnit.
##        Tämä on ainoa tapa saada API toimimaan luotettavasti.
##        """
##
##        url = f"https://www.sahkohinta-api.fi/api/v1/{self.price_type.get()}"
##
##        params = {
##            "tunnit": 24,
##            "tulos": "sarja"
##        }
##
##        try:
##            resp = requests.get(url, params=params)
##            resp.raise_for_status()
##
##            text = resp.text.strip()
##            if not text:
##                print("API palautti tyhjän vastauksen.")
##                return []
##
##            data = resp.json()
##        except Exception as e:
##            print("Virhe API-haussa:", e)
##            return []
##
##        # Lajittele aikajärjestykseen
##        data.sort(key=lambda x: x["aikaleima_suomi"])
##
##        return data



##    # ----------------------------------------------------------------------

    def update_current_price(self, data):

        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        for entry in data:
            entry_time = datetime.datetime.fromisoformat(entry["aikaleima_suomi"]).replace(minute=0, second=0, microsecond=0)

            if entry_time == now:
                final_price = (float(entry["hinta"]) + self.vMarginal) * self.vALV
                self.current_label.config(text=f"Kuluva tunti: {final_price:.2f} snt/kWh")
                return

        self.current_label.config(text="Kuluva tunti: -- snt/kWh")

    # ----------------------------------------------------------------------

    def update_table(self):

        for row in self.tree.get_children():
            self.tree.delete(row)

        data = self.fetch_prices()
        if not data:
            return

        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        for entry in data:
            entry_time = datetime.datetime.fromisoformat(entry["aikaleima_suomi"]).replace(minute=0, second=0, microsecond=0)
            final_price = (float(entry["hinta"]) + self.vMarginal) * self.vALV

            tag = "current_hour" if entry_time == now else ""
            self.tree.insert("", "end", values=(entry["aikaleima_suomi"], f"{final_price:.3f}"), tags=(tag,))

        self.tree.tag_configure("current_hour", background="#004a77")

        self.update_current_price(data)
        self.draw_chart(data)

        self.root.after(1200000, self.update_table)

    # ----------------------------------------------------------------------

    def draw_chart(self, data):
        self.ax.clear()

        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        # Etsi aktiivinen tunti
        active_index = None
        for i, entry in enumerate(data):
            entry_time = datetime.datetime.fromisoformat(entry["aikaleima_suomi"]).replace(minute=0, second=0, microsecond=0)
            if entry_time == now:
                active_index = i
                break

        # --- UUSI KORJAUS ---
        if active_index is None:
            # Käytä viimeistä tuntia "aktiivisena"
            active_index = len(data) - 1


        # Leikkaa 25h ikkuna
        start = max(0, active_index - 6)
        end = min(len(data), active_index + 12)
        window = data[start:end]

        times = [entry["aikaleima_suomi"][-5:] for entry in window]
        prices = [(float(entry["hinta"]) + self.vMarginal) * self.vALV for entry in window]

        bars = self.ax.bar(times, prices, color='#8c3800')

        # --- POIKKIVIIVAT ---
        import matplotlib.ticker as ticker
        self.ax.yaxis.set_major_locator(ticker.MultipleLocator(1.0))
        self.ax.grid(which='major', color='#333333', linestyle='-', linewidth=0.8, alpha=0.8)
        self.ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))
        self.ax.grid(which='minor', color='#333333', linestyle='-', linewidth=0.5, alpha=0.5)

        for bar, entry in zip(bars, window):
            height = bar.get_height()

            hourly_cost = (height / 100) * 1.5
            daily_cost = hourly_cost * 24

            entry_time = datetime.datetime.fromisoformat(entry["aikaleima_suomi"]).replace(minute=0, second=0, microsecond=0)
            is_active = (entry_time == now)

            inactive_color = "#6f6f6f"
            active_color = "#45c4ff"
            text_color = active_color if is_active else inactive_color

            self.ax.annotate(
                f'{height:.2f} snt/kWh\n{hourly_cost:.2f} €/h (1.5kw)\n{daily_cost:.2f} €/24h',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 5),
                textcoords="offset points",
                ha='center',
                va='bottom',
                fontsize=8,
                color=text_color
            )

            if is_active:
                bar.set_facecolor(active_color)

        self.ax.set_ylabel("Hinta (snt/kWh)", color="#7d7c7c")
        self.ax.set_title("Sähkön hinnat (24h näkymä)", color="#7d7c7c")
        self.ax.tick_params(axis='x', rotation=45, colors="#7d7c7c")
        self.ax.tick_params(axis='y', colors="#7d7c7c")

        self.figure.tight_layout()
        self.canvas.draw()

    # ----------------------------------------------------------------------

    def save_to_csv(self):

        data = [(self.tree.item(row)["values"][0],
                 self.tree.item(row)["values"][1])
                for row in self.tree.get_children()]

        try:
            with open("sahkohinnat.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Aikaleima", "Hinta (snt/kWh)"])
                writer.writerows(data)

            messagebox.showinfo("Tallennettu", "Tiedot tallennettu tiedostoon sahkohinnat.csv")

        except Exception as e:
            messagebox.showerror("Virhe", f"Virhe tallennettaessa tiedostoa: {e}")


# ----------------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = ElectricityPriceApp(root)
    root.mainloop()
