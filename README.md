# Electricity-prices-24h-ja-kw-h
Automatically working electricity price fetcher. Shows cents/kWh and € / h and € / 24h.

Script gets current stock electricity prices for the current moment and 24 hours after that.

<img width="2555" height="1433" alt="image" src="https://github.com/user-attachments/assets/6ee98ed0-ed3a-497d-8ffa-b9bff8b7fe55" />

It uses the public API "https://www.sahkohinta-api.fi/api/v1/halpa"

---

## 🖥️ Linux Autostart (systemd user service)

You can run the Python GUI automatically using a user‑level systemd service.

### 1. Create the directory
```bash  
  mkdir -p ~/.config/systemd/user
  mkdir -p ~/.config/systemd/user
  nano ~/.config/systemd/user/sahkon_seuranta.service
```
### 2. Add these inside the file:
```bash  
  [Unit]
  Description=Electricity prices watch GUI
  
  [Service]
  ExecStart=/usr/bin/python3 "/<path to script>/sahkohinnat_gui_laajennettu_v5.py"
  WorkingDirectory=/<path to script>
  Environment=DISPLAY=:0
  Environment=XAUTHORITY=/home/<user>/.Xauthority
  WantedBy=default.target
```
### 3. [Install]
  And enable & start service:
```bash  
  systemctl --user daemon-reload
  systemctl --user enable sahkon_seuranta.service
  systemctl --user start sahkon_seuranta.service
```
