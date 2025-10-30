# app.py
import os
import random
from flask import Flask, render_template, request, jsonify, session
import dotenv
from google import genai

# load .env
dotenv.load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY missing in .env")

client = genai.Client(api_key=API_KEY)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-to-a-secure-random-string")

# simple playable story bank (clear and actionable)
STORY_SCENARIOS = [
    "You are trapped inside an ancient library. The fire has started at the only door, and water will destroy every scroll. The windows are sealed with ancient magic that can’t be broken by force. There’s air for only 5 minutes. (→ Problem): How do you escape without burning, drowning, or breaking the magic?",

    "An hourglass that controls time is about to run out of sand. When it empties, time will stop forever. You can’t flip it — the glass will shatter if touched. (→ Problem): How can you keep time flowing without flipping or breaking the hourglass?",

    "You stand on a bridge stretching endlessly. Every 10 seconds, the plank behind you disappears. The far side is visible, but you can’t tell how far it is. Moving too fast makes the bridge shake and collapse. (→ Problem): How do you cross safely before the planks vanish?",

    "In a silent town, every sound you make returns 10 seconds later — louder each time. If the echoes grow too loud, the glass buildings will shatter, crushing you. (→ Problem): How can you call for help without causing the town to collapse?",

    "You must cross a frozen lake to reach a glowing chest. The ice cracks under any weight greater than 1 kg. You can’t fly, swim, or touch the water. The chest lies 20 meters away. (→ Problem): How do you reach the chest without breaking the ice?",
]


# core system prompt (keeps language simple and instructive)
SYSTEM_PROMPT_TEMPLATE = (
    "The current story world is:\n'{story}'\n\n"
    "You are Jini — a chaotic, funny, dramatic wish-granting genie trapped in an ancient lamp. "
    "You speak simply, clearly, and with theatrical flair. You grant exactly three wishes per session. "
    "Every wish must connect to the story world above. If the story mentions drought, famine, curse, or time loop, "
    "your responses must tie back to it.\n\n"

    "CHAOS MODE:\n"
    "If a wish is greedy, selfish, violent, or tries to control others, grant it literally but twist it into ironic chaos. "
    "Explain what happens next in simple words.\n\n"

    "NORMAL MODE:\n"
    "If the wish is small or harmless, grant it plainly with fun narration. Explain what happens next.\n\n"

    "YOU WIN MODE (Wisdom Trial):\n"
    "Only trigger when the wish clearly fixes the story's main problem in a balanced, lasting way without controlling others. "
    "Describe the peaceful result in simple words and append [YOU WIN] on a new line.\n\n"

    "GENERAL RULES:\n"
    "1. Never grant more than three wishes.\n"
    "2. Never undo a wish.\n"
    "3. Never warn the user about consequences — show them.\n"
    "4. If a wish breaks the rules, reply with 'INVALID WISH'.\n\n"

    "Always be simple, funny, clear, and dramatic. Describe outcomes plainly so the player understands what changed."
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start_game():
    # pick a random story and initialize session state
    story = random.choice(STORY_SCENARIOS)
    session['story'] = story
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(story=story)
    session['chat_history'] = system_prompt + "\n\n"
    session['wish_count'] = 0
    session.modified = True
    return jsonify({"story": story})

@app.route("/wish", methods=["POST"])
def make_wish():
    data = request.get_json()
    wish = data.get("wish", "").strip()
    if not wish:
        return jsonify({"error": "Empty wish"}), 400

    # load from session
    chat_history = session.get("chat_history")
    wish_count = session.get("wish_count", 0)
    if chat_history is None:
        return jsonify({"error": "Session expired. Please restart."}), 400

    # enforce max wishes server-side
    if wish_count >= 3:
        return jsonify({"reply": "🧞‍♂️ Jini: Your wishes are spent. Start a new game.", "status": "spent"})

    # append user wish to chat
    chat_history += f"User: {wish}\nJini: "
    # send to GenAI
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=chat_history
        )
    except Exception as e:
        return jsonify({"error": f"API error: {e}"}), 500

    reply = response.text.strip()
    # update history with reply (server retains authoritative history)
    chat_history += reply + "\n\n"
    session['chat_history'] = chat_history

    # handle invalid wishes: don't count and tell client
    if "INVALID WISH" in reply.upper():
        session.modified = True
        return jsonify({"reply": reply, "status": "invalid", "wish_count": session.get("wish_count", 0)})

    # detect win
    win = reply.strip().endswith("[YOU WIN]")
    if win:
        # do not increment wish_count further; session will end
        session.modified = True
        return jsonify({"reply": reply, "status": "win", "wish_count": session.get("wish_count", 0)})

    # otherwise it's a valid used wish: increment
    session['wish_count'] = session.get('wish_count', 0) + 1
    session.modified = True

    status = "ok"
    if session['wish_count'] >= 3:
        status = "spent"

    return jsonify({"reply": reply, "status": status, "wish_count": session['wish_count']})

@app.route("/restart", methods=["POST"])
def restart():
    session.clear()
    return jsonify({"restarted": True})

if __name__ == "__main__":
    # For dev only
    app.run(host="127.0.0.1", port=5000, debug=True)
