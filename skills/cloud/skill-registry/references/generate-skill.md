# Generate Skill

## Description

GenerateSkill automates the *initial* scaffolding of new agent skills by generating standardized documentation (`SKILL.md`) and directory structures based on user requirements. Note: This tool serves strictly as a starting point. It generates a foundational draft and requires human intervention to refine the logic, review the architecture, and ensure the final skill meets production-level quality standards.

**Use when:**

* Scaffolding a new agent skill from scratch.
* Establishing a standardized directory structure for a new tool.
* Drafting a properly formatted `SKILL.md` for a specific use case.

**Don't use when:**

* Executing an existing skill or performing a general query.
* Writing general code outside of a skill directory.

---

## Directory Structure

When generating a new skill, the following standardized architecture should be established:

* **`SKILL.md`**: The core documentation and instruction set for the skill *(Required)*.
* **`references/`**: Directory for storing heavy external documentation, API specs, or knowledge bases *(Optional)*.
* **`scripts/`**: Directory for executable scripts, helper functions, or setup files *(Optional)*. Offload complex code snippets, deterministic helper functions, or repetitive setup tasks into this directory to keep `SKILL.md` lean and focused entirely on high-level instructions and usage patterns.
* **`assets/`**: Directory for static files, templates, or media used by the skill *(Optional)*.

---

## Execution Workflow

To successfully generate and deliver a new skill draft, follow these sequential steps:

1. **Requirement Gathering:** Analyze the user's prompt to understand the purpose, inputs, outputs, and constraints of the desired skill.
2. **Drafting:** Generate the `SKILL.md` content based on the gathered requirements. Ensure the description is concise (under 300 words) and explicitly defines "Use when" and "Don't use when" conditions. Identify and map out necessary optional directories (`references/`, `scripts/`, `assets/`) if applicable, ensuring that any complex or repetitive code logic is offloaded into the `scripts/` directory.
3. **Validation:** Automatically parse and validate the drafted `SKILL.md` to ensure strictly valid Markdown formatting (e.g., correct header nesting, closed tags, proper list syntax). Fix any errors before proceeding.
4. **Review Request:** Present the generated `SKILL.md` and directory structure to the user. Explicitly request their review and manual revision, reiterating that human evaluation is required to finalize the draft for production.
