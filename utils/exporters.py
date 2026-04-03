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


# --- EXCEL GENERATION ---
def create_shift_excel(shift, is_admin=False):
    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)
    data = []

    for d in sorted_deliveries:
        diff = d.weight_fact - d.weight_plan  # Считаем разницу
        row = {
            "Садик": d.kindergarten.name,
            "Товар": d.product.name,
            "Ед.": d.product.unit,
            "План": d.weight_plan,
            "Факт": d.weight_fact,
            "Разница": diff,
            "Цена": d.p_sadik_fact,
            "Сумма": d.total_price_sadik
        }
        if is_admin:
            row["Закуп"] = d.p_zakup_fact
            row["Прибыль"] = d.net_profit
        data.append(row)

    df = pd.DataFrame(data)
    os.makedirs("temp", exist_ok=True)
    suffix = "ADMIN" if is_admin else "DRIVER"
    file_path = os.path.join("temp", f"Report_{suffix}_{shift.opened_at.strftime('%d_%m')}_{shift.id}.xlsx")

    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Отчет', startrow=4)
        ws = writer.sheets['Отчет']

        # Шапка
        ws.cell(row=1, column=1, value=f"ОТЧЕТ ({suffix}) ОТ {shift.opened_at.strftime('%d.%m.%Y')}")
        ws.cell(row=2, column=1, value=f"Водитель: {shift.driver.full_name}")
        ws.cell(row=3, column=1, value=f"Телефон: {shift.driver.phone}")

        # Итоги
        last_row = len(data) + 6
        total_rev = sum(d.total_price_sadik for d in shift.deliveries)
        fuel = shift.fuel_expense or 0

        ws.cell(row=last_row, column=1, value="ОБЩАЯ ВЫРУЧКА:")
        ws.cell(row=last_row, column=2, value=total_rev)
        ws.cell(row=last_row + 1, column=1, value="БЕНЗИН:")
        ws.cell(row=last_row + 1, column=2, value=fuel)

        if is_admin:
            total_cost = sum(d.total_cost_zakup for d in shift.deliveries)
            ws.cell(row=last_row + 2, column=1, value="ЧИСТАЯ ПРИБЫЛЬ:")
            ws.cell(row=last_row + 2, column=2, value=total_rev - total_cost - fuel)
        else:
            ws.cell(row=last_row + 2, column=1, value="ИТОГО К ВЫДАЧЕ:")
            ws.cell(row=last_row + 2, column=2, value=total_rev - fuel)

        # Ширина колонок
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 20

    return file_path


# --- PDF GENERATION ---
def create_shift_pdf(shift, is_admin=False):
    os.makedirs("temp", exist_ok=True)
    suffix = "ADMIN" if is_admin else "DRIVER"
    file_path = os.path.join("temp", f"Report_{suffix}_{shift.id}.pdf")

    doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)

    cell_style = ParagraphStyle('Cell', fontName=FONT_NAME, fontSize=7, leading=9, alignment=1)
    name_style = ParagraphStyle('Name', fontName=FONT_NAME, fontSize=7, leading=9, alignment=0)

    elements = []

    header_text = f"<b>ОТЧЕТ ({suffix}) ОТ {shift.opened_at.strftime('%d.%m.%Y')}</b><br/>"
    header_text += f"Водитель: {shift.driver.full_name} | Тел: {shift.driver.phone}"
    elements.append(Paragraph(header_text, ParagraphStyle('H', fontName=FONT_NAME, fontSize=10)))
    elements.append(Spacer(1, 15))

    # Заголовки (Добавили Разн.)
    header = ["Объект", "Товар", "Ед.", "План", "Факт", "Разн.", "Цена", "Сумма"]
    if is_admin:
        header += ["Закуп", "Прибыль"]

    table_data = [[Paragraph(h, cell_style) for h in header]]
    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)

    for d in sorted_deliveries:
        diff = d.weight_fact - d.weight_plan
        row = [
            Paragraph(d.kindergarten.name, name_style),
            Paragraph(d.product.name, name_style),
            Paragraph(d.product.unit, cell_style),
            Paragraph(str(d.weight_plan), cell_style),
            Paragraph(str(d.weight_fact), cell_style),
            Paragraph(f"{diff:+.2f}", cell_style),  # Формат +0.50 или -0.20
            Paragraph(f"{d.p_sadik_fact:,.0f}", cell_style),
            Paragraph(f"{d.total_price_sadik:,.0f}", cell_style)
        ]
        if is_admin:
            row += [
                Paragraph(f"{d.p_zakup_fact:,.0f}", cell_style),
                Paragraph(f"{d.net_profit:,.0f}", cell_style)
            ]
        table_data.append(row)

    # Ширина колонок (оптимизируем под A4)
    if not is_admin:
        col_widths = [115, 100, 30, 45, 45, 45, 60, 70]
    else:
        col_widths = [85, 80, 25, 40, 40, 40, 50, 60, 50, 60]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F4F4F")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 15))

    # Итоги
    total_rev = sum(d.total_price_sadik for d in shift.deliveries)
    fuel = shift.fuel_expense or 0
    res_text = f"ВЫРУЧКА: <b>{total_rev:,.0f}</b> | БЕНЗИН: <b>{fuel:,.0f}</b>"

    if is_admin:
        total_cost = sum(d.total_cost_zakup for d in shift.deliveries)
        res_text += f" | ПРИБЫЛЬ: <b>{total_rev - total_cost - fuel:,.0f} сум</b>"
    else:
        res_text += f" | ИТОГО: <b>{total_rev - fuel:,.0f} сум</b>"

    elements.append(Paragraph(res_text, ParagraphStyle('S', fontName=FONT_NAME, fontSize=9)))
    doc.build(elements)
    return file_path