`python3 -m venv venv`

`source ./venv/bin/activate`

`pip install -r requirements.txt`

`sudo nano /lib/systemd/system/bot.service`

`sudo systemctl daemon-reload`

`sudo systemctl enable bot.service`

`sudo systemctl start bot.service`
