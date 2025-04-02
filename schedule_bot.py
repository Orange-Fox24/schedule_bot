import pandas as pd
import os
import re
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext, Filters
from telegram.error import TelegramError

# Константы
TELEGRAM_BOT_TOKEN = "7820826946:AAHrL2UCEu9K3jNXdagZ7IveqC5U4W9uFMw"
LOCAL_FILE_PATHS = {
    "1 курс": "data/1_course.xlsx",
    "2 курс": "data/2_course.xlsx",
    "3-4 курс": "data/3_4_course.xlsx"
}
DAYS_OF_WEEK = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']


def clean_group_name(group_name: str) -> str:
    """Очистка названия группы от лишних символов"""
    return group_name.strip().replace('"', '').replace("'", "")


def parse_lesson(lesson: str) -> str:
    """Парсинг информации о занятии с сохранением ДО"""
    if not lesson or pd.isna(lesson) or str(lesson).strip() == '':
        return ""

    # Удаляем номера пар (1,2 П) если они есть
    lesson = re.sub(r'^\d,\d\sП\s', '', str(lesson))

    # Разделяем дисциплину и преподавателя (сохраняем ДО)
    parts = [p.strip() for p in str(lesson).split(',')]

    if len(parts) >= 2:
        discipline = parts[0]
        teacher = ', '.join(parts[1:])  # Сохраняем все после первой запятой
        return f"{discipline} ({teacher})"
    return lesson


def load_schedule(excel_path: str):
    """Загрузка и обработка Excel файла"""
    try:
        # Читаем Excel, пропуская строку с "ОБЕД"
        df = pd.read_excel(excel_path)

        # Удаляем полностью пустые строки и столбцы
        df = df.dropna(how='all')
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

        # Обрабатываем названия групп
        df.columns = [clean_group_name(col) for col in df.columns]

        # Обрабатываем каждое занятие (сохраняем ДО)
        for col in df.columns[2:]:  # Пропускаем первые 2 колонки (День и Время)
            df[col] = df[col].apply(parse_lesson)

        return df
    except Exception as e:
        print(f"Ошибка загрузки Excel: {e}")
        return None


def get_schedule_for_day(df, group: str, day: str):
    """Получение расписания на конкретный день"""
    schedule = []
    current_day = ""

    for _, row in df.iterrows():
        row_day = str(row.iloc[0]).strip()
        time = str(row.iloc[1]).strip()

        if row_day != "":
            current_day = row_day

        if current_day.lower() == day.lower() and time.lower() != "обед":
            lesson = row[group] if group in df.columns else ""
            if lesson and str(lesson).strip() and not pd.isna(lesson):
                schedule.append(f"⏰ <b>{time}</b> ┆ {lesson}")

    return schedule


def get_full_schedule(df, group: str):
    """Получение полного расписания на неделю"""
    schedule = {}
    current_day = ""

    for _, row in df.iterrows():
        row_day = str(row.iloc[0]).strip()
        time = str(row.iloc[1]).strip()

        if row_day != "":
            current_day = row_day
            if current_day not in schedule:
                schedule[current_day] = []

        if time.lower() != "обед":
            lesson = row[group] if group in df.columns else ""
            if lesson and str(lesson).strip() and not pd.isna(lesson):
                schedule[current_day].append(f"⏰ <b>{time}</b> ┆ {lesson}")

    # Добавляем все дни недели, даже если их нет в расписании
    for day in DAYS_OF_WEEK:
        if day not in schedule:
            schedule[day] = []

    return schedule


def format_schedule(schedule, group: str, day: str = None):
    """Форматирование расписания для вывода с улучшенным визуальным оформлением"""
    if not schedule:
        return f"📭 Расписание для группы {group} не найдено."

    if day:
        response = [
            f"═══════════════\n"
            f"📚 <b>Группа:</b> {group}\n"
            f"📅 <b>День:</b> {day}\n"
            f"═══════════════"
        ]
        if schedule:
            response.append("\n".join(schedule))
        else:
            response.append("\n🍃 Нет занятий")
        response.append("\n═══════════════")
    else:
        response = [
            f"════════════════════\n"
            f"📚 <b>Группа:</b> {group}\n"
            f"🗓️ <b>Полное расписание</b>\n"
            f"════════════════════"
        ]
        for day_name in DAYS_OF_WEEK:
            day_schedule = schedule.get(day_name, [])
            response.append(
                f"\n━━━━━━━━━━━━━━━━\n"
                f"📌 <b>{day_name}</b>\n"
                f"━━━━━━━━━━━━━━━━"
            )
            response.extend(day_schedule if day_schedule else ["\n🍃 Нет занятий"])
        response.append("\n════════════════════")

    return "\n".join(response)


def start(update: Update, context: CallbackContext) -> None:
    """Обработка команды /start"""
    keyboard = [["1 курс", "2 курс"], ["3-4 курс"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(
        "✨ Привет! Я бот с расписанием колледжа.\n"
        "👇 Выбери курс:",
        reply_markup=reply_markup
    )


def handle_course_selection(update: Update, context: CallbackContext) -> None:
    """Обработка выбора курса"""
    course = update.message.text
    if course not in LOCAL_FILE_PATHS:
        update.message.reply_text("⚠️ Выбери курс из списка.")
        return

    excel_path = LOCAL_FILE_PATHS[course]
    if not os.path.exists(excel_path):
        update.message.reply_text("❌ Файл расписания не найден.")
        return

    df = load_schedule(excel_path)
    if df is None:
        update.message.reply_text("❌ Ошибка чтения расписания.")
        return

    # Получаем список групп (игнорируем первые 2 колонки)
    groups = [col for col in df.columns[2:] if str(col).strip() != '']

    if not groups:
        update.message.reply_text("❌ Группы не найдены в расписании.")
        return

    # Сохраняем данные
    context.user_data['current_df'] = df
    context.user_data['current_course'] = course

    # Создаем клавиатуру с группами
    keyboard = [[group] for group in groups]
    keyboard.append(["⬅️ Назад"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        f"✅ Выбран <b>{course}</b>\n"
        "👇 Теперь выбери группу:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )


def handle_group_selection(update: Update, context: CallbackContext) -> None:
    """Обработка выбора группы"""
    user_input = update.message.text

    # Обработка кнопки "Назад"
    if user_input == "⬅️ Назад":
        start(update, context)
        return

    if 'current_df' not in context.user_data:
        update.message.reply_text("⚠️ Сначала выбери курс.")
        return

    df = context.user_data['current_df']
    group = user_input

    if group not in df.columns:
        update.message.reply_text(f"❌ Группа {group} не найдена в расписании.")
        return

    # Сохраняем выбранную группу
    context.user_data['current_group'] = group

    # Создаем меню выбора дня недели или полного расписания
    keyboard = [
        [KeyboardButton(day) for day in DAYS_OF_WEEK[:3]],
        [KeyboardButton(day) for day in DAYS_OF_WEEK[3:]],
        ["Полное расписание"],
        ["⬅️ Назад"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        f"✅ Группа: <b>{group}</b>\n"
        "👇 Выбери день или полное расписание:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )


def handle_day_selection(update: Update, context: CallbackContext) -> None:
    """Обработка выбора дня недели"""
    user_input = update.message.text

    # Обработка кнопки "Назад"
    if user_input == "⬅️ Назад":
        if 'current_course' in context.user_data:
            handle_course_selection(update, context)
        else:
            start(update, context)
        return

    if 'current_df' not in context.user_data or 'current_group' not in context.user_data:
        update.message.reply_text("⚠️ Сначала выбери курс и группу.")
        return

    df = context.user_data['current_df']
    group = context.user_data['current_group']

    if user_input == "Полное расписание":
        # Формируем полное расписание
        full_schedule = get_full_schedule(df, group)
        response = format_schedule(full_schedule, group)
    elif user_input in DAYS_OF_WEEK:
        # Формируем расписание на выбранный день
        day_schedule = get_schedule_for_day(df, group, user_input)
        response = format_schedule(day_schedule, group, user_input)
    else:
        update.message.reply_text("⚠️ Пожалуйста, выбери день недели из предложенных.")
        return

    # Добавляем кнопки для продолжения работы
    keyboard = [
        [KeyboardButton(day) for day in DAYS_OF_WEEK[:3]],
        [KeyboardButton(day) for day in DAYS_OF_WEEK[3:]],
        ["Полное расписание"],
        ["⬅️ Назад"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        response,
        parse_mode='HTML',
        reply_markup=reply_markup
    )


def main():
    """Запуск бота"""
    if not os.path.exists('data'):
        os.makedirs('data')

    try:
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(MessageHandler(Filters.regex(r'^(1 курс|2 курс|3-4 курс)$'), handle_course_selection))
        dispatcher.add_handler(
            MessageHandler(Filters.regex(r'^(Понедельник|Вторник|Среда|Четверг|Пятница|Полное расписание)$'),
                           handle_day_selection))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_group_selection))

        print("🤖 Бот запущен...")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")


if __name__ == '__main__':
    main()