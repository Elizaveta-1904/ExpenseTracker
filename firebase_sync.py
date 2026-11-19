import json
from pathlib import Path
from threading import Thread

import requests
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput


def show_sync_popup(app):
    form = BoxLayout(orientation="vertical", padding=12, spacing=8)
    email = TextInput(hint_text="Электронная почта", multiline=False)
    password = TextInput(hint_text="Пароль", password=True, multiline=False)
    status = Label(text="")
    button = Button(text="Войти и синхронизировать")

    for widget in (email, password, status, button):
        form.add_widget(widget)

    popup = Popup(
        title="Синхронизация с Firebase",
        content=form,
        size_hint=(0.85, None),
        height=300,
    )

    def finish(downloaded, message):
        button.disabled = False
        popup.auto_dismiss = True
        if downloaded is None:
            status.text = message
            return

        for key, record in downloaded.items():
            if not app.store.exists(key):
                app.store.put(key, **record)

        app.refresh_history()
        popup.dismiss()
        app.status.text = message

    def sync(address, secret, local):
        downloaded = None
        stage = "вход"
        try:
            path = Path(__file__).with_name("firebase_config.json")
            config = json.loads(path.read_text(encoding="utf-8-sig"))

            login = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": config["apiKey"]},
                json={"email": address, "password": secret, "returnSecureToken": True},
                timeout=15,
            )
            login.raise_for_status()
            account = login.json()

            stage = "доступ к базе"
            base = config["databaseURL"].rstrip("/")
            url = f'{base}/users/{account["localId"]}/operations.json'
            params = {"auth": account["idToken"]}

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            remote = response.json() or {}

            new_records = {
                key: record for key, record in local.items() if key not in remote
            }
            if new_records:
                response = requests.patch(
                    url, params=params, json=new_records, timeout=15
                )
                response.raise_for_status()

            downloaded = {
                key: record for key, record in remote.items() if key not in local
            }
            message = (
                f"Отправлено: {len(new_records)}. "
                f"Загружено: {len(downloaded)}."
            )
        except requests.HTTPError as error:
            message = f"Firebase: {stage}, код {error.response.status_code}"
        except requests.RequestException:
            message = "Ошибка сети. Попробуй ещё раз."
        except (OSError, ValueError, KeyError):
            message = "Проверь файл firebase_config.json."

        Clock.schedule_once(lambda _dt: finish(downloaded, message))

    def start(_button):
        address = email.text.strip()
        secret = password.text
        if not address or not secret:
            status.text = "Введи почту и пароль"
            return

        local = {key: app.store.get(key) for key in app.store.keys()}
        password.text = ""
        button.disabled = True
        popup.auto_dismiss = False
        status.text = "Синхронизация…"
        Thread(target=sync, args=(address, secret, local), daemon=True).start()

    button.bind(on_release=start)
    popup.open()