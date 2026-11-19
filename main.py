import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


CATEGORIES = {
    "Расход": ("Офис", "Маркетинг", "Логистика", "Прочее"),
    "Доход": ("Продажи", "Услуги", "Прочие доходы"),
}


def format_money(kopecks):
    sign = "−" if kopecks < 0 else ""
    rubles, remainder = divmod(abs(kopecks), 100)
    return f"{sign}{rubles},{remainder:02d} руб."


class ExpenseTrackerApp(App):
    def build(self):
        self.title = "ExpenseTracker"
        self.store = JsonStore(str(Path(__file__).with_name("expenses.json")))

        layout = BoxLayout(orientation="vertical", padding=16, spacing=8)

        self.operation = Spinner(
            text="Расход",
            values=tuple(CATEGORIES),
            size_hint_y=None,
            height=44,
        )
        self.category = Spinner(
            text=CATEGORIES["Расход"][0],
            values=CATEGORIES["Расход"],
            size_hint_y=None,
            height=44,
        )
        self.operation.bind(text=self.change_categories)

        self.description = TextInput(
            hint_text="Описание операции",
            multiline=False,
            size_hint_y=None,
            height=44,
        )
        self.amount = TextInput(
            hint_text="Сумма в рублях",
            multiline=False,
            size_hint_y=None,
            height=44,
        )

        add_button = Button(
            text="Добавить операцию", size_hint_y=None, height=44
        )
        add_button.bind(on_release=self.add_operation)

        analytics_button = Button(
            text="Аналитика", size_hint_y=None, height=44
        )
        analytics_button.bind(on_release=self.show_analytics)

        self.status = Label(size_hint_y=None, height=32)
        self.total = Label(size_hint_y=None, height=68)
        self.history = BoxLayout(orientation="vertical", size_hint_y=None)
        self.history.bind(minimum_height=self.history.setter("height"))

        scroll = ScrollView()
        scroll.add_widget(self.history)

        for widget in (
            self.operation,
            self.category,
            self.description,
            self.amount,
            add_button,
            analytics_button,
            self.status,
            self.total,
            scroll,
        ):
            layout.add_widget(widget)

        self.refresh_history()
        from firebase_sync import show_sync_popup
        sync_button = Button(text="Синхронизировать", size_hint_y=None, height=44)
        sync_button.bind(on_release=lambda _button: show_sync_popup(self))
        layout.add_widget(sync_button)
        return layout

    def change_categories(self, _spinner, operation):
        self.category.values = CATEGORIES[operation]
        self.category.text = self.category.values[0]

    def add_operation(self, _button):
        description = self.description.text.strip()
        amount = self.amount.text.strip().replace(",", ".")

        if not description:
            self.status.text = "Введи описание операции"
            return

        if not re.fullmatch(r"[0-9]{1,12}(\.[0-9]{1,2})?", amount):
            self.status.text = "Введи сумму, например 500,50"
            return

        rubles, _, fraction = amount.partition(".")
        kopecks = int(rubles) * 100 + int(fraction.ljust(2, "0"))
        if kopecks == 0:
            self.status.text = "Сумма должна быть больше нуля"
            return

        self.store.put(
            uuid4().hex,
            operation=self.operation.text,
            category=self.category.text,
            description=description,
            kopecks=kopecks,
        )

        self.description.text = ""
        self.amount.text = ""
        self.status.text = "Операция сохранена"
        self.refresh_history()

    def refresh_history(self):
        self.history.clear_widgets()
        totals = Counter()

        for key in reversed(list(self.store.keys())):
            record = self.store.get(key)
            operation = record.get("operation", "Расход")
            kopecks = record["kopecks"]
            totals[operation] += kopecks

            self.history.add_widget(Label(
                text=(
                    f'{operation} — {record["category"]} — '
                    f'{record["description"]} — {format_money(kopecks)}'
                ),
                size_hint_y=None,
                height=36,
            ))

        income = totals["Доход"]
        expenses = totals["Расход"]
        self.total.text = (
            f"Доходы: {format_money(income)}\n"
            f"Расходы: {format_money(expenses)}\n"
            f"Баланс: {format_money(income - expenses)}"
        )

    def show_analytics(self, _button):
        totals = Counter()
        for key in self.store.keys():
            record = self.store.get(key)
            if record.get("operation", "Расход") == "Расход":
                totals[record["category"]] += record["kopecks"]

        content = BoxLayout(orientation="vertical", spacing=8, padding=8)
        popup = Popup(
            title="Расходы по категориям",
            content=content,
            size_hint=(0.9, 0.85),
        )

        if totals:
            categories, amounts = zip(*totals.most_common())
            figure = Figure(figsize=(8, 4), layout="constrained")
            axes = figure.add_subplot()
            bars = axes.barh(
                categories,
                [amount / 100 for amount in amounts],
                color="#8264c4",
            )
            axes.invert_yaxis()
            axes.set_xlabel("Сумма, руб.")
            axes.margins(x=0.3)
            axes.bar_label(
                bars,
                labels=[format_money(amount) for amount in amounts],
                padding=4,
            )

            buffer = BytesIO()
            FigureCanvasAgg(figure).print_png(buffer)
            buffer.seek(0)
            chart = CoreImage(buffer, ext="png")
            content.add_widget(Image(texture=chart.texture, fit_mode="contain"))
        else:
            content.add_widget(Label(text="Добавь расход, чтобы увидеть график"))

        close_button = Button(text="Закрыть", size_hint_y=None, height=44)
        close_button.bind(on_release=popup.dismiss)
        content.add_widget(close_button)
        popup.open()


if __name__ == "__main__":
    ExpenseTrackerApp().run()