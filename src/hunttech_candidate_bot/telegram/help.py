"""
Help rendering — рендеринг справки по командам (из hunttech_bot_common.telegram).
"""
from hunttech_bot_common.telegram import CommandDef, CommandGroup, render_help_text

from hunttech_candidate_bot.telegram.commands.registry import (
    get_all_commands, get_commands_by_group, COMMON_GROUPS
)


def render_help_overview(is_admin: bool = False) -> str:
    """Рендеринг обзорной справки (/help без аргументов)."""
    groups_order = ["system", "candidate", "setup"]
    if is_admin:
        groups_order.append("admin")

    lines = ["📋 *Справка по командам*\n"]
    for group_key in groups_order:
        group = COMMON_GROUPS.get(group_key)
        if not group:
            continue
        cmds = get_commands_by_group(group_key, admin=is_admin)
        if not cmds:
            continue
        lines.append(f"{group.emoji} *{group.title}*")
        for cmd in cmds:
            admin_mark = " 👑" if cmd.admin else ""
            lines.append(f"  /{cmd.command} — {cmd.description}{admin_mark}")
        lines.append("")

    lines.append("💡 *Использование:*")
    lines.append("  `/help` — это сообщение")
    lines.append("  `/help <раздел>` — команды раздела (system, candidate, setup)")
    lines.append("  `/help <команда>` — детали команды")

    return "\n".join(lines)


def render_help_group(group_key: str, is_admin: bool = False) -> str | None:
    """Рендеринг справки по группе команд."""
    group = COMMON_GROUPS.get(group_key)
    if not group:
        return None

    cmds = get_commands_by_group(group_key, admin=is_admin)
    if not cmds:
        return None

    lines = [f"{group.emoji} *{group.title}*\n"]
    for cmd in cmds:
        admin_mark = " 👑" if cmd.admin else ""
        lines.append(f"/{cmd.command}{admin_mark} — {cmd.description}")
        if cmd.details:
            for line in cmd.details.split("\n"):
                lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines)


def render_command_help(command_name: str) -> str | None:
    """Рендеринг справки по конкретной команде."""
    from hunttech_candidate_bot.telegram.commands.registry import get_command

    cmd = get_command(command_name)
    if not cmd:
        return None

    lines = [f"{cmd.emoji} */{cmd.command}* — {cmd.description}\n"]
    lines.append(f"Синтаксис: `/{cmd.command} {cmd.syntax.split('/', 1)[-1] if '/' in cmd.syntax else ''}`")

    if cmd.aliases:
        lines.append(f"Алиасы: {', '.join(cmd.aliases)}")

    if cmd.details:
        lines.append(f"\n{cmd.details}")

    return "\n".join(lines)