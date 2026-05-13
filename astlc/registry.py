"""
Skill and Adapter registries.

The registries are the central extension points for the platform.
Third-party plugins register skills and adapters here; the pipeline
discovers them by name at runtime.

Usage::

    from platform.registry import SkillRegistry, AdapterRegistry

    # Built-in registration (done automatically by skills/__init__.py)
    SkillRegistry.register("rca", RCASkill)

    # Plugin registration
    SkillRegistry.register("my_custom_skill", MySkill)

    # Lookup
    skill_cls = SkillRegistry.get("rca")
    instance  = skill_cls(config=cfg, context={})
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Type

if TYPE_CHECKING:
    pass


class SkillRegistry:
    """Registry for AgentSkill subclasses."""

    _registry: dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, skill_cls: Any) -> None:
        cls._registry[name] = skill_cls

    @classmethod
    def get(cls, name: str) -> Any:
        if name not in cls._registry:
            raise KeyError(f"Skill '{name}' not registered. Available: {list(cls._registry)}")
        return cls._registry[name]

    @classmethod
    def all_names(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def instantiate(cls, name: str, config: Any, context: dict | None = None) -> Any:
        skill_cls = cls.get(name)
        return skill_cls(config=config, context=context or {})


class AdapterRegistry:
    """Registry for adapter implementations keyed by (type, provider)."""

    _registry: dict[tuple[str, str], Any] = {}

    @classmethod
    def register(cls, adapter_type: str, provider: str, adapter_cls: Any) -> None:
        cls._registry[(adapter_type, provider)] = adapter_cls

    @classmethod
    def get(cls, adapter_type: str, provider: str) -> Any:
        key = (adapter_type, provider)
        if key not in cls._registry:
            raise KeyError(
                f"Adapter ({adapter_type}, {provider}) not registered. "
                f"Available: {[f'{t}/{p}' for t, p in cls._registry]}"
            )
        return cls._registry[key]

    @classmethod
    def instantiate(cls, adapter_type: str, provider: str, **kwargs: Any) -> Any:
        adapter_cls = cls.get(adapter_type, provider)
        return adapter_cls(**kwargs)

    @classmethod
    def all_keys(cls) -> list[str]:
        return [f"{t}/{p}" for t, p in sorted(cls._registry)]
