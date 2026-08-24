"""Deterministic compiler layer: IR -> MongoDB execution plans."""

from .mongodb import (
    MONGO_OPERATOR,
    CompiledPlan,
    CompileError,
    Step,
    compile_command,
    compile_operation,
    condition_to_filter,
)

__all__ = [
    "MONGO_OPERATOR",
    "CompiledPlan",
    "CompileError",
    "Step",
    "compile_command",
    "compile_operation",
    "condition_to_filter",
]
