"""
Command registry — единый реестр команд бота кандидатов.
"""
from typing import Optional

from hunttech_bot_common.telegram import CommandDef, CommandGroup

# ── Группы команд ─────────────────────────────────────────────────────────

COMMON_GROUPS: dict[str, CommandGroup] = {
    "system": CommandGroup(
        key="system", emoji="🚀", title="Система",
        description="Запуск, справка, отмена", order=10,
    ),
    "candidate": CommandGroup(
        key="candidate", emoji="👤", title="Кандидаты",
        description="Создание и проверка кандидатов", order=20,
    ),
    "setup": CommandGroup(
        key="setup", emoji="🔧", title="Настройка",
        description="Настройка подключений и просмотр статуса", order=30,
    ),
    "admin": CommandGroup(
        key="admin", emoji="👑", title="Администрирование",
        description="Управление пользователями и доступом", order=40,
    ),
}

_COMMANDS: dict[str, CommandDef] = {}

_STANDARD_COMMANDS: list[CommandDef] = [
    CommandDef(
        command="start", title="Старт", emoji="🚀",
        description="Начать работу с ботом",
        syntax="/start", group="system",
        details="При первом запуске показывает приветствие и инструкцию.",
        handler_name="cmd_start", order=10,
    ),
    CommandDef(
        command="help", title="Справка", emoji="❓",
        description="Справка по командам",
        syntax="/help [раздел]", group="system",
        aliases=["помощь", "commands"],
        details="/help — список разделов.\n/help <раздел> — команды раздела.",
        handler_name="cmd_help", order=20,
    ),
    CommandDef(
        command="cancel", title="Отмена", emoji="❌",
        description="Отменить текущую операцию",
        syntax="/cancel", group="system",
        handler_name="cmd_cancel", order=50,
    ),
    CommandDef(
        command="candidate", title="Кандидаты", emoji="👤",
        description="Работа с кандидатами: создание, проверка дублей, список",
        syntax="/candidate create|check|list", group="candidate",
        details="/candidate create — мастер создания кандидата из резюме\n"
                "/candidate check — проверить дубли по ФИО/контактам\n"
                "/candidate list — список недавно созданных кандидатов",
        handler_name="cmd_candidate", order=10,
    ),
    CommandDef(
        command="setup", title="Настройки", emoji="🔧",
        description="Настройка AI и БД, просмотр статуса (только админ)",
        syntax="/setup [подкоманда]", group="setup",
        admin=True,
        details="/setup ai — мастер настройки AI-провайдера\n"
                "/setup ai test — проверить подключение к AI\n"
                "/setup ai show — показать настройки AI\n"
                "/setup db — мастер настройки PostgreSQL\n"
                "/setup db test — проверить подключение к БД\n"
                "/setup db show — показать конфигурацию БД\n"
                "/setup user — доступ рекрутеров (выдать/отозвать)\n"
                "/setup status — статистика работы бота\n"
                "/setup show — текущие настройки бота",
        handler_name="cmd_setup", order=10,
    ),
    CommandDef(
        command="user", title="Управление доступом", emoji="👤",
        description="Управление доступом пользователей (только админ)",
        syntax="/user add|delete|list", group="system",
        admin=True, hidden=True,
        details="/user add <username> — добавить пользователя\n"
                "/user delete <username> — удалить пользователя\n"
                "/user list — список разрешённых пользователей",
        handler_name="cmd_user", order=40,
    ),
    CommandDef(
        command="request_access", title="Запросить доступ", emoji="📨",
        description="Отправить запрос на доступ к боту",
        syntax="/request_access", group="system",
        hidden=True,
        handler_name="cmd_request_access", order=5,
    ),
    CommandDef(
        command="usage", title="Расходы на нейросеть", emoji="💰",
        description="Расходы на нейросеть (только админ)",
        syntax="/usage [день|week|month|all|N]", group="system",
        admin=True,
        details="/usage — расходы за сегодня.\n"
                "/usage week — за 7 дней.\n"
                "/usage month — за 30 дней.\n"
                "/usage all — за всё время.\n"
                "/usage N — за N дней.",
        handler_name="cmd_usage", order=200,
    ),
]


def register_command(cmd: CommandDef):
    _COMMANDS[cmd.command] = cmd


def register_commands(cmds: list[CommandDef]):
    for cmd in cmds:
        register_command(cmd)


def get_command(name: str) -> Optional[CommandDef]:
    clean = name.lstrip("/").lower()
    if clean in _COMMANDS:
        return _COMMANDS[clean]
    for cmd in _COMMANDS.values():
        if clean in [a.lstrip("/").lower() for a in cmd.aliases]:
            return cmd
    return None


def get_all_commands() -> list[CommandDef]:
    return sorted(_COMMANDS.values(), key=lambda c: c.order)


def get_commands_by_group(group: str, admin: bool = False) -> list[CommandDef]:
    return [
        c for c in get_all_commands()
        if c.group == group and (admin or not c.admin)
    ]


def init_standard_commands():
    for cmd in _STANDARD_COMMANDS:
        if cmd.command not in _COMMANDS:
            register_command(cmd)


def register_all_commands():
    """Register all commands (called at startup)."""
    init_standard_commands()