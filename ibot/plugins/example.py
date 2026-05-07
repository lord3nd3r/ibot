"""Example ibot/Sopel-compatible plugin.

Demonstrates how plugins work with the Sopel compatibility shim.
Drop this file into your plugins directory to test.
"""

from sopel import plugin


def setup(bot):
    """Called when the plugin is loaded."""
    print(f"[example] Plugin loaded!")


@plugin.command('hello')
def hello(bot, trigger):
    """Respond to .hello with a greeting."""
    bot.say(f"Hello, {trigger.nick}! 👋")


@plugin.command('about')
def about(bot, trigger):
    """Show bot info."""
    bot.say("I'm ibot — a Sopel-compatible IRC bot! 🤖")


@plugin.rule(r'(?i)^(hi|hey|hello)\b')
def greeting_rule(bot, trigger):
    """Respond to greetings."""
    bot.reply(f"Hey there! 😊")


@plugin.command('echo')
def echo(bot, trigger):
    """Echo back the user's message."""
    text = trigger.group(2)
    if text:
        bot.say(text)
    else:
        bot.reply("Echo what? Give me something to say!")


@plugin.command('whoami')
def whoami(bot, trigger):
    """Show information about the triggering user."""
    parts = [
        f"Nick: {trigger.nick}",
        f"Host: {trigger.host or 'unknown'}",
        f"Sender: {trigger.sender}",
    ]
    if trigger.admin:
        parts.append("Status: Admin ⭐")
    if trigger.owner:
        parts.append("Status: Owner 👑")
    if trigger.account:
        parts.append(f"Account: {trigger.account}")
    bot.say(' | '.join(parts))


@plugin.command('remember')
def remember(bot, trigger):
    """Store a note. Usage: .remember <text>"""
    text = trigger.group(2)
    if not text:
        bot.reply("Remember what? Usage: .remember <text>")
        return
    bot.db.set_nick_value(trigger.nick, 'note', text)
    bot.reply(f"Got it! I'll remember that. 📝")


@plugin.command('recall')
def recall(bot, trigger):
    """Recall your stored note."""
    note = bot.db.get_nick_value(trigger.nick, 'note')
    if note:
        bot.reply(f"Your note: {note}")
    else:
        bot.reply("You haven't stored anything yet. Use .remember <text>")


@plugin.require_admin
@plugin.command('admin')
def admin_only(bot, trigger):
    """Admin-only command."""
    bot.say(f"Welcome, admin {trigger.nick}! 🔑")


@plugin.event('JOIN')
@plugin.unblockable
def on_join(bot, trigger):
    """Log when someone joins."""
    pass  # Silently track; remove pass and add bot.say() to greet


def shutdown(bot):
    """Called when the plugin is unloaded."""
    print("[example] Plugin unloaded!")
