
import ast
import io
import logging
import math
import operator
import os
import re

import qrcode
from deep_translator import GoogleTranslator
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ==============================
# MAIN MENU
# ==============================

MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📝 Text Formatter", callback_data="tool:formatter"),
        InlineKeyboardButton("🔢 Word Counter", callback_data="tool:counter"),
    ],
    [
        InlineKeyboardButton("🌐 Text Translator", callback_data="tool:translator"),
        InlineKeyboardButton("🔳 QR Code Generator", callback_data="tool:qr"),
    ],
    [
        InlineKeyboardButton("🧮 Calculator", callback_data="tool:calculator"),
    ],
    [
        InlineKeyboardButton("ℹ️ Help", callback_data="tool:help"),
    ],
])


FORMAT_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("UPPERCASE", callback_data="format:upper"),
        InlineKeyboardButton("lowercase", callback_data="format:lower"),
    ],
    [
        InlineKeyboardButton("Title Case", callback_data="format:title"),
        InlineKeyboardButton("Clean Text", callback_data="format:clean"),
    ],
    [
        InlineKeyboardButton("↩️ Main Menu", callback_data="tool:home"),
    ],
])


# ==============================
# SAFE CALCULATOR
# ==============================

ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def calculate_safely(expression):

    if len(expression) > 100:
        raise ValueError("Please keep calculations under 100 characters.")

    tree = ast.parse(expression, mode="eval")

    def visit(node):

        if isinstance(node, ast.Expression):
            return visit(node.body)

        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value

        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:

            left = visit(node.left)
            right = visit(node.right)

            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("That power is too large.")

            result = ALLOWED_OPERATORS[type(node.op)](left, right)

            if not math.isfinite(float(result)) or abs(result) > 10**100:
                raise ValueError("The result is too large.")

            return result

        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[type(node.op)](visit(node.operand))

        raise ValueError(
            "Use numbers and basic operators only: + - * / // % **"
        )

    return visit(tree)


# ==============================
# START COMMAND
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "Welcome to Smart Tools Bot! 👋\n\n"
        "Choose a tool from the menu:\n\n"
        "📝 Format text\n"
        "🔢 Count words and characters\n"
        "🌐 Translate text\n"
        "🔳 Generate QR codes\n"
        "🧮 Calculate expressions\n\n"
        "Select a button to get started.",
        reply_markup=MENU,
    )


# ==============================
# HELP COMMAND
# ==============================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "HOW TO USE SMART TOOLS BOT\n\n"
        "1. Select a tool from the menu.\n"
        "2. Follow the instruction and send your text.\n"
        "3. Use /start to return to the main menu.\n"
        "4. Use /cancel to cancel the current task.\n\n"
        "Translator example:\n"
        "Spanish | Good morning\n\n"
        "Calculator example:\n"
        "(12 + 8) * 3",
        reply_markup=MENU,
    )


# ==============================
# CANCEL COMMAND
# ==============================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "Your current task has been cancelled.",
        reply_markup=MENU,
    )


# ==============================
# BUTTON HANDLER
# ==============================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    # Return to main menu
    if data == "tool:home":

        context.user_data.clear()

        await query.message.reply_text(
            "Choose a tool:",
            reply_markup=MENU,
        )
        return

    # Text formatting buttons
    if data.startswith("format:"):

        original = context.user_data.get("formatter_text")

        if not original:
            await query.message.reply_text(
                "Please select Text Formatter and send your text first.",
                reply_markup=MENU,
            )
            return

        action = data.split(":", 1)[1]

        if action == "upper":
            result = original.upper()

        elif action == "lower":
            result = original.lower()

        elif action == "title":
            result = original.title()

        elif action == "clean":

            result = "\n".join(
                re.sub(r"[ \t]+", " ", line.strip())
                for line in original.splitlines()
                if line.strip()
            )

        else:
            return

        context.user_data.pop("formatter_text", None)

        await query.message.reply_text(
            f"Formatted text:\n\n{result}",
            reply_markup=MENU,
        )
        return

    # Help button
    if data == "tool:help":

        await query.message.reply_text(
            "Choose a tool, follow its instruction, and send your input.\n"
            "Use /start to return to the main menu.",
            reply_markup=MENU,
        )
        return

    # Tool instructions
    prompts = {

        "tool:formatter": (
            "formatter",
            "Send the text you want to format."
        ),

        "tool:counter": (
            "counter",
            "Send the text you want counted."
        ),

        "tool:translator": (
            "translator",
            "Send the target language, then a vertical bar |, "
            "then your text.\n\n"
            "Example: French | Hello, how are you?"
        ),

        "tool:qr": (
            "qr",
            "Send the text or website address you want to turn into a QR code."
        ),

        "tool:calculator": (
            "calculator",
            "Send a calculation.\n\nExample: (25 + 5) * 2"
        ),

    }

    if data not in prompts:
        return

    mode, prompt = prompts[data]

    context.user_data.clear()
    context.user_data["mode"] = mode

    await query.message.reply_text(
        prompt,
        reply_markup=MENU,
    )


# ==============================
# TEXT HANDLER
# ==============================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = (update.message.text or "").strip()

    mode = context.user_data.get("mode")

    if not mode:

        await update.message.reply_text(
            "Please choose a tool from the menu or send /start.",
            reply_markup=MENU,
        )
        return

    # ==========================
    # TEXT FORMATTER
    # ==========================

    if mode == "formatter":

        context.user_data["formatter_text"] = user_text

        await update.message.reply_text(
            "Choose how you want to format your text:",
            reply_markup=FORMAT_MENU,
        )
        return

    context.user_data.pop("mode", None)

    try:

        # ======================
        # WORD COUNTER
        # ======================

        if mode == "counter":

            words = re.findall(
                r"\b[\w'-]+\b",
                user_text,
                flags=re.UNICODE
            )

            char_count = len(user_text)

            no_spaces = len(
                re.sub(r"\s", "", user_text)
            )

            line_count = len(user_text.splitlines())

            await update.message.reply_text(
                "📊 TEXT STATISTICS\n\n"
                f"Words: {len(words)}\n"
                f"Characters (with spaces): {char_count}\n"
                f"Characters (without spaces): {no_spaces}\n"
                f"Lines: {line_count}",
                reply_markup=MENU,
            )


        # ======================
        # TEXT TRANSLATOR
        # ======================

        elif mode == "translator":

            if "|" not in user_text:

                raise ValueError(
                    "Use this format:\n"
                    "Target language | Your text\n\n"
                    "Example: German | Good morning"
                )

            language, source_text = user_text.split("|", 1)

            language = language.strip()
            source_text = source_text.strip()

            if not language or not source_text:

                raise ValueError(
                    "Please enter both a language and text."
                )

            translated = GoogleTranslator(
                source="auto",
                target=language,
            ).translate(source_text)

            await update.message.reply_text(
                f"🌐 Translation ({language}):\n\n{translated}",
                reply_markup=MENU,
            )


        # ======================
        # QR CODE GENERATOR
        # ======================

        elif mode == "qr":

            if not user_text:
                raise ValueError("Please send text or a website address.")

            if len(user_text) > 1500:
                raise ValueError(
                    "Please keep the QR content under 1,500 characters."
                )

            qr = qrcode.QRCode(
                box_size=8,
                border=3,
            )

            qr.add_data(user_text)
            qr.make(fit=True)

            image = qr.make_image(
                fill_color="black",
                back_color="white",
            )

            image_file = io.BytesIO()
            image_file.name = "qr-code.png"

            image.save(
                image_file,
                format="PNG",
            )

            image_file.seek(0)

            await update.message.reply_photo(
                photo=image_file,
                caption="Your QR code is ready. ✅",
                reply_markup=MENU,
            )


        # ======================
        # CALCULATOR
        # ======================

        elif mode == "calculator":

            result = calculate_safely(user_text)

            await update.message.reply_text(
                f"🧮 Result: {result}",
                reply_markup=MENU,
            )


    except ZeroDivisionError:

        await update.message.reply_text(
            "You cannot divide by zero.",
            reply_markup=MENU,
        )

    except Exception as error:

        logger.warning(
            "Could not process user input: %s",
            error,
        )

        await update.message.reply_text(
            f"Sorry, I couldn't process that.\n\n{error}",
            reply_markup=MENU,
        )


# ==============================
# MAIN APPLICATION
# ==============================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is missing. Add your Telegram bot token "
            "in Railway > Variables."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("cancel", cancel)
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    logger.info("Smart Tools Bot is starting...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
