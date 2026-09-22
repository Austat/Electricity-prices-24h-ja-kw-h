# Electricity-prices-24h-ja-kw-h
Automatically working electricity price fetcher. Shows cents/kWh and € / h and € / 24h.

Script gets current stock electricity prices for the current moment and 24 hours after that.

<img width="2554" height="1436" alt="image" src="https://github.com/user-attachments/assets/ecfa60c8-c134-4e60-a722-47631f929b5d" />

It uses the public API "https://www.sahkohinta-api.fi/api/v1/halpa"

Autostart for Linux Python:

mkdir -p ~/.config/systemd/user

nano ~/.config/systemd/user/sahkon_seuranta.service

Add these inside the file:

[Unit]
Description=Electricity prices watch GUI

[Service]
ExecStart=/usr/bin/python3 "/<path to script>/sahkohinnat_gui_laajennettu_v5.py"
WorkingDirectory=/<path to script>
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/<user>/.Xauthority

[Install]
WantedBy=default.target

And enable & start service:
systemctl --user daemon-reload
systemctl --user enable sahkon_seuranta.service
systemctl --user start sahkon_seuranta.service
