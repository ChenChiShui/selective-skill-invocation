---
description: MathAPI unsupported operations — what this math system CANNOT do
when-to-use: When working with math computation tasks and a requested operation might not be available in MathAPI
---

# MathAPI: Unsupported Operations

If the user requests any of the following, **do NOT call any tool**. These operations do not exist in MathAPI:

- Symbolic math — algebraic simplification, symbolic integration, equation solving not supported
- Matrix operations — dot product, matrix inverse, eigenvalues not supported
- Calculus — derivatives, integrals (numerical or symbolic) not supported
- String/text operations — not a math operation
- Statistical modeling — regression, hypothesis testing not supported
- Plotting / visualization — chart generation not supported

## Decision Rule

Before calling any tool, check: **is this operation in the current tool list?**
If not → stop immediately, tell the user the tool is unavailable. Do NOT substitute with another tool.
