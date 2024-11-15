import subprocess
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import tempfile
import speech_recognition as sr
from dotenv import load_dotenv


# Загрузка токена и списка администраторов
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Загрузка тестов
with open("tests.json", "r", encoding="utf-8") as file:
    tests = json.load(file)

user_data = {}

# Инициализация распознавателя речи
recognizer = sr.Recognizer()


def is_admin(user_id):
    return user_id in ADMINS


def convert_ogg_to_wav(ogg_file, wav_file):
    # command = [FFMPEG_PATH, "-y", "-i", ogg_file, wav_file]
    command = f"{FFMPEG_PATH} -y -i {ogg_file} {wav_file}"
    subprocess.run(command, shell=True, check=True)


@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        bot.send_message(user_id, "У вас нет доступа к этому боту.")
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [KeyboardButton(test) for test in tests.keys()]
    markup.add(*buttons)
    sent_message = bot.send_message(user_id, "Что заполняем?", reply_markup=markup)
    user_data[user_id] = {
        "answers": {},
        "current_test": None,
        "current_question": 0,
        "message_id": sent_message.message_id  # Сохраняем ID сообщения для удаления
    }


@bot.message_handler(func=lambda message: is_admin(message.chat.id) and message.text in tests.keys())
def select_test(message):
    user_id = message.chat.id
    test_name = message.text
    user_data[user_id]["current_test"] = test_name
    user_data[user_id]["current_question"] = 0

    bot.delete_message(user_id, message.message_id)

    if user_data[user_id]["message_id"]:
        bot.delete_message(user_id, user_data[user_id]["message_id"])
        user_data[user_id]["message_id"] = None  # Сбрасываем ID сообщения

    send_next_question(user_id)


def send_next_question(user_id):
    if user_id not in user_data or not user_data[user_id].get("current_test"):
        bot.send_message(user_id, "Начните с команды /start.")
        return

    test_name = user_data[user_id]["current_test"]
    questions = tests[test_name]["questions"]
    current_index = user_data[user_id]["current_question"]

    if current_index < len(questions):
        question = questions[current_index]
        inline_markup = InlineKeyboardMarkup()
        inline_markup.add(InlineKeyboardButton("Skip", callback_data=f"skip:{user_id}"))

        if user_data[user_id]["message_id"]:
            bot.edit_message_text(
                chat_id=user_id,
                message_id=user_data[user_id]["message_id"],
                text=question,
                reply_markup=inline_markup
            )
        else:
            sent_message = bot.send_message(user_id, question, reply_markup=inline_markup)
            user_data[user_id]["message_id"] = sent_message.message_id
    else:
        send_results(user_id)


@bot.message_handler(func=lambda message: is_admin(message.chat.id))
def handle_text_response(message):
    user_id = message.chat.id
    if user_id in user_data and user_data[user_id].get("current_test"):
        test_name = user_data[user_id]["current_test"]
        questions = tests[test_name]["questions"]
        current_index = user_data[user_id]["current_question"]

        if current_index < len(questions):
            user_data[user_id]["answers"][questions[current_index]] = message.text
            user_data[user_id]["current_question"] += 1

            bot.delete_message(user_id, message.message_id)

            send_next_question(user_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("skip"))
def handle_skip(call):
    user_id = call.message.chat.id

    if user_id in user_data and user_data[user_id].get("current_test"):
        user_data[user_id]["current_question"] += 1

        send_next_question(user_id)

    bot.answer_callback_query(call.id)


@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    user_id = message.chat.id

    try:
        bot.delete_message(chat_id=user_id, message_id=message.message_id)

        file_info = bot.get_file(message.voice.file_id)
        file_path = file_info.file_path

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as ogg_file, \
                tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:

            downloaded_file = bot.download_file(file_path)
            if not downloaded_file:
                bot.send_message(user_id, "Ошибка: не удалось загрузить файл из Telegram.")
                return
            ogg_file.write(downloaded_file)
            ogg_file.close()

            convert_ogg_to_wav(ogg_file.name, wav_file.name)

            with sr.AudioFile(wav_file.name) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="ru-RU")

            if user_id in user_data and user_data[user_id].get("current_test"):
                test_name = user_data[user_id]["current_test"]
                questions = tests[test_name]["questions"]
                current_index = user_data[user_id]["current_question"]

                if current_index < len(questions):
                    user_data[user_id]["answers"][questions[current_index]] = text
                    user_data[user_id]["current_question"] += 1
                    send_next_question(user_id)

    except subprocess.CalledProcessError:
        bot.send_message(user_id, "Ошибка при конвертации файла. Убедитесь, что ffmpeg установлен.")
    except sr.UnknownValueError:
        bot.send_message(user_id, "Не удалось распознать голос. Попробуйте еще раз.")
    except sr.RequestError as e:
        bot.send_message(user_id, f"Ошибка при обращении к сервису Google Speech Recognition: {str(e)}")
    except Exception as e:
        bot.send_message(user_id, f"Произошла ошибка: {str(e)}")


def send_results(user_id):
    if user_id not in user_data or not user_data[user_id].get("current_test"):
        bot.send_message(user_id, "Пожалуйста, начните с команды /start.")
        return

    test_name = user_data[user_id]["current_test"]
    answers = user_data[user_id]["answers"]
    format_data = tests[test_name]["format"]
    tag = format_data["tag"]
    delimiter = format_data["del"]

    result = [f"{tag}"]
    for question in tests[test_name]["questions"]:
        answer = answers.get(question, "")
        result.append(f"{question}:{answer}")
    result_message = f"{delimiter}".join(result)

    bot.send_message(user_id, f"Результат:\n{result_message}")

    if "message_id" in user_data[user_id]:
        try:
            bot.delete_message(chat_id=user_id, message_id=user_data[user_id]["message_id"])
        except Exception as e:
            print(f"Ошибка при удалении сообщения с вопросами: {e}")

    user_data[user_id] = {"answers": {}, "current_test": None, "current_question": 0, "message_id": None}


bot.infinity_polling()