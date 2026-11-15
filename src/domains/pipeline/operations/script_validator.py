import ast
from typing import Tuple


def validate_python_script(script_content: str) -> Tuple[bool, str]:
    """
    Validates Python syntax using the AST parser without executing code.
    Returns: (is_valid: bool, error_message: str)
    """
    if not script_content or not script_content.strip():
        return False, "Script content cannot be empty."

    try:
        ast.parse(script_content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}, column {e.offset}: {e.msg}"
    except Exception as e:
        return False, f"Script validation error: {str(e)}"
