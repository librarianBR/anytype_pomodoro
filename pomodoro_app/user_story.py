"""História de usuário no formato usado em backlogs Scrum, gravada na
descrição da tarefa: "Como <quem>, quero <o quê> para <por quê>." mais os
critérios de aceitação."""
from __future__ import annotations

from typing import Iterable

PLACEHOLDERS = (
    "<tipo de usuário>", "<objetivo>", "<benefício>",
    "<contexto>", "<ação>", "<resultado esperado>",
)

HINT = "Como <tipo de usuário>, quero <objetivo> para <benefício>."

TEMPLATE = (
    f"{HINT}\n"
    "\n"
    "Critérios de aceitação:\n"
    "- Dado <contexto>, quando <ação>, então <resultado esperado>."
)


def has_placeholders(text: str) -> bool:
    """True se ainda sobrou algum campo do modelo sem preencher."""
    return any(p in (text or "") for p in PLACEHOLDERS)


def build_story(who: str, what: str, why: str = "", criteria: Iterable[str] = ()) -> str:
    """Monta a história a partir das respostas (usado pela linha de comando)."""
    story = f"Como {who.strip()}, quero {what.strip()}"
    story += f" para {why.strip()}." if why.strip() else "."
    items = [f"- {c.strip()}" for c in criteria if c.strip()]
    if items:
        story += "\n\nCritérios de aceitação:\n" + "\n".join(items)
    return story
