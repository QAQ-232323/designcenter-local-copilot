"""MCP protocol behaviour: both framings, dispatch, and failure envelopes."""

from __future__ import annotations

import io
import json

import pytest

from nx_skill import server as srv


@pytest.fixture(autouse=True)
def reset_framing():
    """The framing mode is sticky by design; tests must not leak it."""
    srv._LSP_FRAMING = False
    yield
    srv._LSP_FRAMING = False


def _line(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8") + b"\n"


def _read_all(stream: io.BytesIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().decode("utf-8").splitlines() if line.strip()]


def test_newline_framing_round_trip():
    stream = io.BytesIO(_line({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
    message = srv.read_message(stream)
    assert message == {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert srv._LSP_FRAMING is False


def test_content_length_framing_is_still_accepted():
    body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}).encode("utf-8")
    stream = io.BytesIO(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    assert srv.read_message(stream)["id"] == 7
    assert srv._LSP_FRAMING is True


def test_blank_lines_are_skipped():
    stream = io.BytesIO(b"\n\n" + _line({"jsonrpc": "2.0", "id": 3, "method": "ping"}))
    assert srv.read_message(stream)["id"] == 3


def test_malformed_json_is_skipped_not_fatal():
    stream = io.BytesIO(b"{not json}\n" + _line({"jsonrpc": "2.0", "id": 4, "method": "ping"}))
    assert srv.read_message(stream)["id"] == 4


def test_end_of_input_returns_none():
    assert srv.read_message(io.BytesIO(b"")) is None


def test_reply_uses_the_clients_framing():
    srv._LSP_FRAMING = True
    out = io.BytesIO()
    srv.write_message({"jsonrpc": "2.0", "id": 1}, out)
    assert out.getvalue().startswith(b"Content-Length: ")

    srv._LSP_FRAMING = False
    out = io.BytesIO()
    srv.write_message({"jsonrpc": "2.0", "id": 1}, out)
    assert out.getvalue().endswith(b"\n")
    assert not out.getvalue().startswith(b"Content-Length")


@pytest.fixture()
def ctx(fake_install):
    install, settings = fake_install
    return srv.Context(settings=settings)


@pytest.fixture()
def ctx_without_nx(tmp_path, no_nx):
    from nx_skill.config import Settings

    settings = Settings(workspace=tmp_path / "ws", skip_global_search=True).with_overrides(nx_root=None)
    return srv.Context(settings=settings)


def test_initialize_announces_capabilities(ctx):
    response = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, ctx)
    assert response["result"]["serverInfo"]["name"] == "nx-skill"
    assert "tools" in response["result"]["capabilities"]
    assert "resources" in response["result"]["capabilities"]
    assert "prompts" in response["result"]["capabilities"]
    assert response["result"]["instructions"]


def test_workflow_resource_and_prompt_are_discoverable(ctx):
    resources = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, ctx)["result"]["resources"]
    uri = resources[0]["uri"]
    content = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": uri}}, ctx)
    assert "nx_live_verify" in content["result"]["contents"][0]["text"]
    prompt = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                         "params": {"name": "nx_model_task", "arguments": {"request": "Create a block"}}}, ctx)
    assert "Create a block" in prompt["result"]["messages"][0]["content"]["text"]


def test_live_verify_requires_real_observations():
    status = {"workPart": {"fullPath": "C:\\work\\part.prt"}, "model": {
        "available": True, "features": {"available": True, "count": 2,
                                         "names": ["01_Base", "02_Hole"]}}}
    verified = srv.verify_model_status(status, {"part_path": "c:\\WORK\\part.prt",
                                                "min_features": 2, "feature_names": ["02_Hole"]})
    assert verified["verified"] is True
    unavailable = srv.verify_model_status({"workPart": {}, "model": {"available": False}},
                                           {"min_features": 1})
    assert unavailable["verified"] is False


def test_notifications_get_no_reply(ctx):
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, ctx) is None


def test_tools_list_exposes_schemas(ctx):
    tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ctx)["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "nx_status" in names and "nx_docs_search" in names and "nx_live_run_steps" in names
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_unknown_method_is_an_error_not_a_crash(ctx):
    response = srv.handle({"jsonrpc": "2.0", "id": 9, "method": "no/such"}, ctx)
    assert response["error"]["code"] == -32601


def test_unknown_tool_returns_an_error_envelope(ctx):
    result = srv.handle(
        {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "nx_nope", "arguments": {}}},
        ctx,
    )["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "UNKNOWN_TOOL"
    assert "nx_status" in result["structuredContent"]["error"]["suggestion"]


def test_tools_call_rejects_bad_params(ctx):
    response = srv.handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"arguments": {}}}, ctx)
    assert response["error"]["code"] == -32602


def _call(ctx, name, arguments):
    result = srv.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        ctx,
    )["result"]
    return result["structuredContent"]


def test_status_reports_the_installation(ctx):
    payload = _call(ctx, "nx_status", {})
    assert payload["ok"] is True
    assert payload["result"]["nx"]["release"] == "2512"
    assert payload["result"]["docs"]["xmlDocFiles"] == 1


def test_status_still_succeeds_with_no_nx_installed(ctx_without_nx):
    """Diagnosability: the first tool call must explain the problem, not explode."""
    payload = _call(ctx_without_nx, "nx_status", {})
    assert payload["ok"] is True
    assert payload["result"]["nx"] is None
    assert payload["result"]["nxError"]["code"] == "NX_NOT_FOUND"


def test_docs_search(ctx):
    payload = _call(ctx, "nx_docs_search", {"query": "GetSession", "include_stubs": False})
    assert payload["ok"] is True
    assert payload["result"]["members"][0]["name"] == "NXOpen.Session.GetSession"


def test_docs_search_requires_a_query(ctx):
    payload = _call(ctx, "nx_docs_search", {"query": "  "})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_docs_member_not_found_is_actionable(ctx):
    payload = _call(ctx, "nx_docs_member", {"name": "NXOpen.Nope.Nothing"})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NX_DOCS_NOT_FOUND"
    assert payload["error"]["suggestion"]


def test_module_list_works_without_a_bridge(ctx):
    payload = _call(ctx, "nx_live_module_list", {})
    assert payload["ok"] is True
    assert payload["result"]["moduleCount"] >= 1
    assert payload["result"]["required"]["NXOpen.Features"] is True


def test_route_intent_tool(ctx):
    payload = _call(ctx, "nx_route_intent", {"prompt": "三视图建模"})
    assert payload["result"]["route"] == "modeling"
    assert payload["result"]["visualReference"] is True


def test_prepare_session_attaches_plan_and_workspace(ctx):
    payload = _call(ctx, "nx_prepare_session", {"prompt": "build a flange from this drawing"})
    assert payload["result"]["workspace"]
    assert "plan" in payload["result"]
    assert payload["result"]["intent"]["visualReference"] is True


def test_workspace_violation_is_reported_not_raised(ctx):
    payload = _call(ctx, "nx_create_part", {"part_path": r"C:\Windows\evil.prt"})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORKSPACE_VIOLATION"


def test_step_runner_rejects_smuggled_code(ctx):
    payload = _call(
        ctx,
        "nx_live_run_steps",
        {"steps": [{"operation": "create_block", "params": {"length": 1, "width": 1, "height": 1, "code": "x"}}]},
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert "run_python_inline" in payload["error"]["suggestion"]


def test_step_runner_rejects_unknown_operations(ctx):
    payload = _call(ctx, "nx_live_run_steps", {"steps": [{"operation": "rm_rf"}]})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_step_runner_requires_steps(ctx):
    payload = _call(ctx, "nx_live_run_steps", {"steps": []})
    assert payload["ok"] is False


def test_live_call_rejects_an_unknown_verb(ctx):
    """The client throws on anything it does not implement; reject it earlier."""
    payload = _call(ctx, "nx_live_call", {"command": "module-list"})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_serve_loop_processes_a_session(fake_install):
    install, settings = fake_install
    out = io.BytesIO()
    payload = _line({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    payload += _line({"jsonrpc": "2.0", "method": "notifications/initialized"})
    payload += _line({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    original_stdin, original_stdout = srv.sys.stdin, srv.sys.stdout

    class _Stdin:
        buffer = io.BytesIO(payload)

    class _Stdout:
        buffer = out

    srv.sys.stdin, srv.sys.stdout = _Stdin(), _Stdout()
    try:
        assert srv.serve(srv.Context(settings=settings)) == 0
    finally:
        srv.sys.stdin, srv.sys.stdout = original_stdin, original_stdout

    messages = _read_all(out)
    assert len(messages) == 2  # the notification produced no reply
    assert messages[0]["id"] == 1
    assert messages[1]["result"]["tools"]
