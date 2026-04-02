import pandas as pd
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- НАСТРОЙКА ШРИФТА ---
# Получаем путь к папке со шрифтом
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "arial.ttf")

# Регистрируем шрифт, чтобы PDF понимал русский язык
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('ArialCustom', FONT_PATH))
    FONT_NAME = 'ArialCustom'
else:
    # Если забыл положить шрифт, будет ошибка при генерации PDF с русскими буквами
    FONT_NAME = 'Helvetica'

def create_shift_excel(shift):
    """
    Генерирует Excel файл.
    Данные идут строго в том порядке, в котором их вводил водитель.
    """
    # 1. Сортируем отгрузки по ID (хронологический порядок ввода)
    # Это гарантирует, что товары в отчете идут так, как нажимал кнопки водитель
    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)

    # 2. Собираем данные для таблицы
    data = []
    for d in sorted_deliveries:
        data.append({
            "Садик": d.kindergarten.name,
            "Товар": d.product.name,
            "Ед. изм.": d.product.unit,
            "План": d.weight_plan,
            "Факт": d.weight_fact,
            "Цена": d.p_sadik_fact,
            "Сумма": d.total_price_sadik
        })

    df = pd.DataFrame(data)

    # 3. Настройка папки и имени файла
    os.makedirs("temp", exist_ok=True)
    file_name = f"Report_{shift.opened_at.strftime('%d_%m_%Y')}_{shift.id}.xlsx"
    file_path = os.path.join("temp", file_name)

    # 4. Запись в файл
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        # Основная таблица (начинаем с 5-й строки)
        df.to_excel(writer, index=False, sheet_name='Отчет', startrow=4)

        ws = writer.sheets['Отчет']

        # Шапка (инфо о смене и водителе)
        ws.cell(row=1, column=1, value=f"ОТЧЕТ ПО ДОСТАВКЕ: {shift.opened_at.strftime('%d.%m.%Y')}")
        ws.cell(row=2, column=1, value=f"Водитель: {shift.driver.full_name}")
        ws.cell(row=3, column=1, value=f"Телефон: {shift.driver.phone}")

        # Итоги внизу
        last_row = len(data) + 6
        total_sum = sum(d['Сумма'] for d in data)
        fuel = shift.fuel_expense or 0

        ws.cell(row=last_row, column=1, value="ОБЩАЯ ВЫРУЧКА:")
        ws.cell(row=last_row, column=2, value=total_sum)

        ws.cell(row=last_row + 1, column=1, value="БЕНЗИН:")
        ws.cell(row=last_row + 1, column=2, value=fuel)

        ws.cell(row=last_row + 2, column=1, value="ИТОГО К ВЫДАЧЕ:")
        ws.cell(row=last_row + 2, column=2, value=total_sum - fuel)

        # Немного расширим колонки для красоты (опционально)
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 20

    return file_path


def create_shift_pdf(shift, is_admin=False):
    os.makedirs("temp", exist_ok=True)
    suffix = "ADMIN" if is_admin else "DRIVER"
    file_path = os.path.join("temp", f"Report_{suffix}_{shift.id}.pdf")

    doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)

    # Стиль для текста в ячейках (чтобы работал перенос строк)
    cell_style = ParagraphStyle(
        'CellStyle',
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        alignment=1  # По центру
    )

    # Стиль для названий (выравнивание по левому краю для длинных имен)
    name_style = ParagraphStyle(
        'NameStyle',
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        alignment=0  # По левому краю
    )

    elements = []

    # 1. ШАПКА (как в Excel)
    header_text = f"<b>ОТЧЕТ ПО ДОСТАВКЕ ({suffix}) ОТ {shift.opened_at.strftime('%d.%m.%Y')}</b><br/>"
    header_text += f"Водитель: {shift.driver.full_name}<br/>"
    header_text += f"Телефон: {shift.driver.phone}<br/>"

    elements.append(Paragraph(header_text, ParagraphStyle('Header', fontName=FONT_NAME, fontSize=11, leading=14)))
    elements.append(Spacer(1, 15))

    # 2. ТАБЛИЦА (Добавляем План и Ед.изм)
    # Определяем заголовки
    header = ["Объект", "Товар", "Ед.", "План", "Факт", "Цена", "Сумма"]
    if is_admin:
        header += ["Закуп", "Прибыль"]

    table_data = [[Paragraph(h, cell_style) for h in header]]

    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)

    for d in sorted_deliveries:
        # Оборачиваем длинные названия в Paragraph для переноса
        row = [
            Paragraph(d.kindergarten.name, name_style),
            Paragraph(d.product.name, name_style),
            Paragraph(d.product.unit, cell_style),
            Paragraph(str(d.weight_plan), cell_style),
            Paragraph(str(d.weight_fact), cell_style),
            Paragraph(f"{d.p_sadik_fact:,.0f}", cell_style),
            Paragraph(f"{d.total_price_sadik:,.0f}", cell_style)
        ]
        if is_admin:
            row += [
                Paragraph(f"{d.p_zakup_fact:,.0f}", cell_style),
                Paragraph(f"{d.net_profit:,.0f}", cell_style)
            ]
        table_data.append(row)

    # 3. НАСТРОЙКА ШИРИНЫ КОЛОНОК (A4 ~ 540 точек ширины контента)
    if not is_admin:
        # Увеличили Объект и Товар
        col_widths = [130, 110, 40, 50, 50, 70, 80]
    else:
        # Для админа колонок больше, сжимаем второстепенные
        col_widths = [100, 90, 35, 45, 45, 55, 60, 55, 55]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F4F4F")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 15))

    # 4. ИТОГИ (как в Excel)
    total_rev = sum(d.total_price_sadik for d in shift.deliveries)
    fuel = shift.fuel_expense or 0

    summary_style = ParagraphStyle('Sum', fontName=FONT_NAME, fontSize=10, leading=14)

    res_text = f"ОБЩАЯ ВЫРУЧКА: <b>{total_rev:,.0f} сум</b><br/>"
    res_text += f"БЕНЗИН: <b>{fuel:,.0f} сум</b><br/>"

    if is_admin:
        total_cost = sum(d.total_cost_zakup for d in shift.deliveries)
        net_profit = total_rev - total_cost - fuel
        res_text += f"СЕБЕСТОИМОСТЬ ТОВАРА: <b>{total_cost:,.0f} сум</b><br/>"
        res_text += f"ЧИСТАЯ ПРИБЫЛЬ: <b>{net_profit:,.0f} сум</b>"
    else:
        res_text += f"ИТОГО К ВЫДАЧЕ: <b>{(total_rev - fuel):,.0f} сум</b>"

    elements.append(Paragraph(res_text, summary_style))

    doc.build(elements)
    return file_path