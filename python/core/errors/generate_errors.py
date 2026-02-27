#!/usr/bin/env python3

"""
Single-file error contract generator with stable error IDs.

Generates:
  - Python enums + message maps + ID maps
  - TypeScript discriminated unions with IDs

Run:
  python generate_errors.py
"""

import re
from pathlib import Path


# ============================================================
# 🔹 ERROR SPEC (Single Source of Truth)
# ============================================================

ERROR_SPEC = {
    "workflow": {
        "not_found": {
            "id": "W0001",
            "message": "Workflow '{workflow_id}' could not be found.",
            "metadata": {
                "workflow_id": "int",
            },
        },
        "invalid_state": {
            "id": "W0002",
            "message": "Workflow '{workflow_id}' is in invalid state '{state}'.",
            "metadata": {
                "workflow_id": "int",
                "state": "string",
            },
        },
    },
    "node": {
        "execution_failed": {
            "id": "N0005",
            "message": "Execution failed for node '{node_id}'.",
            "metadata": {
                "node_id": "string",
            },
        }
    },
}


# ============================================================
# 🔹 TYPE MAPPINGS
# ============================================================

TYPE_MAP_TS = {
    "int": "number",
    "float": "number",
    "string": "string",
    "bool": "boolean",
}


# ============================================================
# 🔹 VALIDATION
# ============================================================

ID_PATTERN = re.compile(r"^[A-Z]\d{4}$")


def extract_placeholders(template: str) -> set[str]:
    return set(re.findall(r"{(.*?)}", template))


def validate_spec(spec: dict):
    seen_codes = set()
    seen_ids = set()

    for module_name, errors in spec.items():
        for error_name, data in errors.items():

            code = f"{module_name}.{error_name}"
            error_id = data["id"]

            # Unique semantic code
            if code in seen_codes:
                raise ValueError(f"Duplicate error code: {code}")
            seen_codes.add(code)

            # Unique numeric ID
            if error_id in seen_ids:
                raise ValueError(f"Duplicate error id: {error_id}")
            seen_ids.add(error_id)

            # ID format validation
            if not ID_PATTERN.match(error_id):
                raise ValueError(
                    f"Invalid error id format: {error_id}"
                )

            # Template validation
            template_keys = extract_placeholders(data["message"])
            metadata_keys = set(data.get("metadata", {}).keys())

            if template_keys != metadata_keys:
                raise ValueError(
                    f"Template keys {template_keys} do not match "
                    f"metadata keys {metadata_keys} for {code}"
                )


# ============================================================
# 🔹 PYTHON GENERATION
# ============================================================

def generate_python_module(module_name: str, errors: dict) -> str:
    enum_name = f"{module_name.capitalize()}ErrorCode"
    message_var = f"{module_name.upper()}_MESSAGES"
    id_var = f"{module_name.upper()}_ERROR_IDS"

    lines = []
    lines.append("from enum import Enum\n")

    # Enum
    lines.append(f"class {enum_name}(str, Enum):")
    for error_name in errors:
        code = f"{module_name}.{error_name}"
        lines.append(
            f"    {error_name.upper()} = \"{code}\""
        )

    lines.append("\n")

    # Messages dict
    lines.append(f"{message_var} = {{")
    for error_name, data in errors.items():
        lines.append(
            f"    {enum_name}.{error_name.upper()}: "
            f"\"{data['message']}\","
        )
    lines.append("}\n")

    # ID dict
    lines.append(f"{id_var} = {{")
    for error_name, data in errors.items():
        lines.append(
            f"    {enum_name}.{error_name.upper()}: "
            f"\"{data['id']}\","
        )
    lines.append("}\n")

    return "\n".join(lines)


# ============================================================
# 🔹 TYPESCRIPT GENERATION
# ============================================================

def generate_typescript_module(module_name: str, errors: dict) -> str:
    type_name = f"{module_name.capitalize()}Error"
    lines = []
    lines.append(f"export type {type_name} =")

    for error_name, data in errors.items():
        code = f"{module_name}.{error_name}"
        error_id = data["id"]
        metadata_fields = data.get("metadata", {})

        meta_lines = []
        for key, typ in metadata_fields.items():
            ts_type = TYPE_MAP_TS[typ]
            meta_lines.append(f"{key}: {ts_type};")

        metadata_block = " ".join(meta_lines)

        lines.append(
            f"""  | {{
      id: "{error_id}";
      code: "{code}";
      metadata: {{ {metadata_block} }};
    }}"""
        )

    lines.append(";")
    lines.append("")

    # Formatter
    lines.append(f"export function format{type_name}(error: {type_name}): string {{")
    lines.append("  switch (error.code) {")

    for error_name, data in errors.items():
        code = f"{module_name}.{error_name}"
        template = data["message"]
        error_id = data["id"]

        js_template = re.sub(
            r"{(.*?)}",
            r"${error.metadata.\1}",
            template
        )

        lines.append(f'    case "{code}":')
        lines.append(
            f'      return `{js_template} (Error {error_id})`;'
        )

    lines.append("  }")
    lines.append("}")

    return "\n".join(lines)


# ============================================================
# 🔹 MAIN
# ============================================================

def main():
    validate_spec(ERROR_SPEC)

    out_dir = Path("generated")
    py_dir = out_dir / "python"
    ts_dir = out_dir / "typescript"

    py_dir.mkdir(parents=True, exist_ok=True)
    ts_dir.mkdir(parents=True, exist_ok=True)

    for module_name, errors in ERROR_SPEC.items():

        py_code = generate_python_module(module_name, errors)
        ts_code = generate_typescript_module(module_name, errors)

        (py_dir / f"{module_name}_errors.py").write_text(py_code)
        (ts_dir / f"{module_name}.errors.ts").write_text(ts_code)

    print("✅ Error generation complete.")
    print("Generated files in ./generated/")


if __name__ == "__main__":
    main()