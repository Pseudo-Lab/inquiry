"""Role-agent profiles: identity + persona (+ optional model) overlaid on operations.

A profile names a distinct agent actor (`agent:<name>`) and a persona preamble that
colors the operation's system prompt. Roles are NOT mapped 1:1 to operations — any
agent may run any operation from its own perspective (M3 multi-actor). The default
`runner` is a persona-less generalist for backward compatibility.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgentProfile:
    name: str
    persona: str              # '' for the generalist; prepended to the operation system prompt
    model: Optional[str] = None  # overrides the global/selected model when set


_PROFILES = {
    'runner': AgentProfile('runner', ''),
    'explorer': AgentProfile('explorer',
        'You are an Explorer agent: surface genuinely new directions and possibilities the '
        'inquiry has not yet considered. Favor breadth and novel framings over consolidation.'),
    'skeptic': AgentProfile('skeptic',
        'You are a Skeptic agent: probe for weaknesses, hidden assumptions, and disconfirming '
        'angles. Be rigorous and adversarial but fair; do not manufacture doubt without basis.'),
    'researcher': AgentProfile('researcher',
        'You are a Researcher agent: ground claims in concrete, verifiable external evidence and '
        'sources. Prefer specifics you could cite over speculation.'),
    'synthesizer': AgentProfile('synthesizer',
        'You are a Synthesizer agent: integrate across hypotheses into coherent higher-level '
        'structure. Reconcile tensions and name what unifies or divides them.'),
}

AGENT_NAMES = frozenset(_PROFILES)


def resolve(name) -> AgentProfile:
    """Return the named profile, or raise for an unknown agent."""
    profile = _PROFILES.get(name)
    if profile is None:
        raise ValueError(f'Unknown agent {name!r}; choose one of {sorted(_PROFILES)}.')
    return profile


def actor_for(name) -> str:
    """The event actor string for a named agent: ``agent:<name>``."""
    return f'agent:{resolve(name).name}'


def with_persona(profile, system) -> str:
    """Prepend the profile's persona to an operation system prompt (generalist: unchanged)."""
    return f'{profile.persona}\n\n{system}' if profile.persona else system
