"""CHAIN leadership playbook — qualitative capability.

Deterministic port of the `liderazgo-chain` skill's scoring core: five
dimensions (Colaborativo, Holístico, Adaptable, Influyente, Narrativo), each
scored 0–4, yielding an archetype and a single priority lever. Radar chart,
written report and active directives live alongside (see Task 5 additions).

Síntesis original inspirada en el modelo CHAIN de "From Source to Sold"
(Palamariu & Alicke, 2022); no reproduce el texto del libro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DIMS: list[tuple[str, str]] = [
    ("C", "Colaborativo"),
    ("H", "Holístico"),
    ("A", "Adaptable"),
    ("I", "Influyente"),
    ("N", "Narrativo"),
]
LEVELS: dict[int, str] = {0: "Ausente", 1: "Incipiente", 2: "Funcional", 3: "Sólido", 4: "Distintivo"}
_CODES = [code for code, _ in DIMS]
_NAME = dict(DIMS)
_IMPACT_ORDER = ["I", "N", "A", "H", "C"]

# Filled in Task 5; empty here so directives are [] until then.
PRACTICES: dict[str, list[str]] = {code: [] for code in _CODES}
QUESTIONS: dict[str, list[str]] = {code: [] for code in _CODES}


def coerce_scores(value: object) -> dict[str, int] | None:
    """Parse 5 ints (0..4) from a list/tuple or a space/comma-separated string."""
    if value is None:
        return None
    if isinstance(value, str):
        parts: list = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return None
    if len(parts) != 5:
        return None
    try:
        nums = [int(x) for x in parts]
    except (TypeError, ValueError):
        return None
    if not all(0 <= n <= 4 for n in nums):
        return None
    return {code: n for code, n in zip(_CODES, nums)}


def _validate(scores: dict[str, int]) -> None:
    if set(scores) != set(_CODES):
        raise ValueError(f"scores must have exactly the dims {_CODES}, got {sorted(scores)}")
    for code in _CODES:
        v = scores[code]
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 4:
            raise ValueError(f"{code} must be an int in 0..4, got {v!r}")


def archetype(scores: dict[str, int]) -> tuple[str, str]:
    """(name, description). Rules in priority order — ports the skill's score.py."""
    C, H, A, I, N = scores["C"], scores["H"], scores["A"], scores["I"], scores["N"]  # noqa: E741

    if all(v >= 3 for v in scores.values()):
        return (
            "Líder integral",
            "Las cinco dimensiones sólidas o más. Perfil listo para roles de mayor "
            "alcance; el foco pasa de cubrir huecos a profundizar fortalezas.",
        )
    if all(v <= 1 for v in scores.values()):
        return (
            "En formación",
            "Falta base transversal. No repartir el esfuerzo: elegí UNA dimensión y "
            "construí consistencia ahí antes de abrir frentes.",
        )
    if I <= 1 and N <= 1 and min(C, H, A) >= 2:
        return (
            "Operador invisible",
            "Hace que todo funcione, pero no se ve ni inspira. Es el patrón exacto que "
            "frena el salto a director/CEO: competencia real, sin influencia ni relato.",
        )
    if A <= 1 and min(C, H, I, N) >= 2:
        return (
            "Optimizador frágil",
            "Excelente en régimen estable, expuesto en la próxima disrupción. El riesgo "
            "no se ve hasta que algo se rompe.",
        )
    if H <= 1 and min(C, A, I, N) >= 2:
        return (
            "Especialista de silo",
            "Fuerte en su función, ciego al end-to-end. Optimiza su tramo sin ver el "
            "costo aguas abajo.",
        )
    if C <= 1 and min(H, A, I, N) >= 2:
        return (
            "Llanero solitario",
            "Resuelve solo. Capaz, pero no construye red ni confianza, así que no "
            "escala más allá de lo que toca con sus manos.",
        )
    minimo = min(scores.values())
    flojas = [name for code, name in DIMS if scores[code] == minimo]
    return (
        "Perfil mixto",
        f"Sin un patrón único. La(s) dimensión(es) de menor desarrollo: "
        f"{', '.join(flojas)}. Priorizá la de mayor retorno en tu contexto.",
    )


def priority_lever(scores: dict[str, int]) -> tuple[str, str, int]:
    """The weakest, highest-return dimension: lowest score; ties broken by the
    career-jump impact order I, N, A, H, C."""
    minimo = min(scores.values())
    code = next(c for c in _IMPACT_ORDER if scores[c] == minimo)
    return code, _NAME[code], minimo


@dataclass(frozen=True)
class ChainProfile:
    scores: dict[str, int]
    evidence: dict[str, str]
    name: str | None
    average: float
    gap: int
    archetype: str
    archetype_desc: str
    lever_code: str
    lever_name: str
    lever_level: int
    directives: list[str] = field(default_factory=list)


def score_profile(
    scores: dict[str, int],
    *,
    evidence: dict[str, str] | None = None,
    name: str | None = None,
) -> ChainProfile:
    """Build a full CHAIN profile from validated scores."""
    _validate(scores)
    ev = {code: (evidence or {}).get(code, "") for code in _CODES}
    average = sum(scores.values()) / len(scores)
    gap = max(scores.values()) - min(scores.values())
    arch_name, arch_desc = archetype(scores)
    lever_code, lever_name, lever_level = priority_lever(scores)
    directives = list(PRACTICES.get(lever_code, []))
    return ChainProfile(
        scores=dict(scores),
        evidence=ev,
        name=name,
        average=average,
        gap=gap,
        archetype=arch_name,
        archetype_desc=arch_desc,
        lever_code=lever_code,
        lever_name=lever_name,
        lever_level=lever_level,
        directives=directives,
    )
