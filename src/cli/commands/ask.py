import json
import sys
import logging
import asyncio
import warnings
from typing import Optional

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google.genai.models").setLevel(logging.ERROR)


try:
    from src.cli.commands.login import require_cli_auth, verify_cli_token
    from src.domains.ai.facade.ai import AIFacade
    from src.domains.ai.models.contract.ai import AIQueryRequestContract
except ImportError:
    from cli.commands.login import require_cli_auth, verify_cli_token
    from domains.ai.facade.ai import AIFacade
    from domains.ai.models.contract.ai import AIQueryRequestContract

logger = logging.getLogger(__name__)


def run_ask(prompt: str, user_id: str = "analyst", json_mode: bool = False, cache_ttl: Optional[str] = None) -> int:
    """CLI handler for `artemis ask <prompt>` via AIFacade."""
    require_cli_auth(json_mode=json_mode)
    token_payload = verify_cli_token()
    resolved_user = token_payload.get("username", user_id) if token_payload else user_id

    try:
        user_ctx = token_payload or {"sub": resolved_user, "username": resolved_user, "roles": ["admin", "analyst"] if resolved_user == "admin" else ["user"]}
        facade = AIFacade(user=user_ctx)
        request = AIQueryRequestContract(prompt=prompt, user_id=resolved_user)
        result = asyncio.run(facade.ask(request))

        if cache_ttl:
            try:
                from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
                QueryArtifactManager().register_ai_cache_entry(
                    project_id=None,
                    prompt=prompt,
                    response_text=result.response,
                    explicit_ttl_expression=cache_ttl,
                )
            except Exception as ce:
                logger.debug(f"AI cache TTL artifact registration notice: {ce}")

        if json_mode:
            print(result.model_dump_json(indent=2))
        else:
            print(f"\n{result.response}\n")
            cache_tag = " [CACHED]" if result.cached else ""
            sources = ", ".join(s.upper() for s in result.databases_consulted) if result.databases_consulted else "None"
            tools_summary = ", ".join(tc.tool_name for tc in result.tool_calls) if result.tool_calls else "Direct"
            print(
                f"---\n"
                f"Consulted: {sources} | Tools: {tools_summary}\n"
                f"Model: {result.model_used} | Latency: {result.duration_ms}ms{cache_tag} | Query ID: {result.query_id}\n"
            )
        return 0

    except PermissionError as pe:
        if json_mode:
            print(json.dumps({"error": str(pe), "code": "RATE_LIMITED"}, indent=2))
        else:
            print(f"Rate limit exceeded: {pe}", file=sys.stderr)
        return 1

    except ConnectionError as ce:
        if json_mode:
            print(json.dumps({"error": str(ce), "code": "GRAPH_ERROR"}, indent=2))
        else:
            print(f"Graph database error: {ce}", file=sys.stderr)
        return 2

    except Exception as e:
        if json_mode:
            print(json.dumps({"error": str(e), "code": "GENERAL_ERROR"}, indent=2))
        else:
            print(f"Error querying Artemis AI: {e}", file=sys.stderr)
        return 1
