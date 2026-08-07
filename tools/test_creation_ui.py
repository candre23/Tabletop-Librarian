#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jinja2 import Environment, FileSystemLoader

from app.characters.schema import load_character_schema
from app.characters.storage import create_character
import app.characters.web as character_web
from app.creation import (
    create_draft,
    delete_draft,
    list_drafts,
    load_creation_workflow,
    load_draft,
    save_draft,
)
from app.system_packs import load_system_pack


def _optional_http_test(pack, schema, temp: Path) -> bool:
    try:
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware
    except RuntimeError as exc:
        if "httpx2" in str(exc):
            print("SKIP: simulated HTTP wizard test (optional httpx2 test dependency not installed)")
            return False
        raise

    old_draft_root = character_web.DRAFT_ROOT
    old_character_root = character_web.CHARACTER_ROOT
    character_web.DRAFT_ROOT = temp / "http_drafts"
    character_web.CHARACTER_ROOT = temp / "http_characters"

    try:
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="creation-ui-test")

        @app.get("/_test_login")
        async def _test_login(request: Request):
            request.session["username"] = "http-test-user"
            request.session["role"] = "gm"
            return {"ok": True}

        app.include_router(character_web.router)
        client = TestClient(app)
        assert client.get("/_test_login").status_code == 200

        start = client.post(
            "/characters/create/start",
            data={"system_id": "ttl_test_minimal"},
            follow_redirects=False,
        )
        assert start.status_code == 303
        creation_url = start.headers["location"]
        draft_id = creation_url.rsplit("/", 1)[-1]

        first = client.get(creation_url)
        assert first.status_code == 200
        assert "Identity" in first.text

        next_one = client.post(
            f"/characters/create/{draft_id}/step",
            data={
                "field__name": "HTTP Wizard Test",
                "field__background": "traveler",
                "action": "next",
            },
            follow_redirects=False,
        )
        assert next_one.status_code == 303
        assert "Advancement" in client.get(creation_url).text

        evaluate = client.post(
            f"/characters/create/{draft_id}/evaluate",
            json={
                "values": {
                    "level": "3",
                    "archetype": "adventurer",
                    "skills": ["athletics", "lore"],
                }
            },
        )
        assert evaluate.status_code == 200
        assert evaluate.json()["calculated"]["power_score"] == 6

        next_two = client.post(
            f"/characters/create/{draft_id}/step",
            data={
                "field__level": "3",
                "field__archetype": "adventurer",
                "field__skills": ["athletics", "lore"],
                "action": "next",
            },
            follow_redirects=False,
        )
        assert next_two.status_code == 303
        assert "Notes" in client.get(creation_url).text

        finish = client.post(
            f"/characters/create/{draft_id}/step",
            data={
                "field__active": "on",
                "field__notes": "HTTP completion test",
                "action": "finish",
            },
            follow_redirects=False,
        )
        assert finish.status_code == 303
        assert finish.headers["location"].startswith("/characters/")
        assert "?created=1" in finish.headers["location"]
        assert list_drafts(
            "http-test-user",
            draft_root=character_web.DRAFT_ROOT,
        ) == []
    finally:
        character_web.DRAFT_ROOT = old_draft_root
        character_web.CHARACTER_ROOT = old_character_root

    print("PASS: simulated HTTP wizard lifecycle")
    return True


def main() -> int:
    pack_root = PROJECT_ROOT / "data" / "system_packs"
    pack = load_system_pack(pack_root / "ttl_test_minimal")
    assert pack.valid and pack.manifest is not None
    assert pack.manifest.creation

    schema, schema_issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    assert schema is not None, [issue.format() for issue in schema_issues]

    workflow, workflow_issues = load_creation_workflow(
        pack.root / pack.manifest.creation,
        schema=schema,
    )
    assert workflow is not None, [issue.format() for issue in workflow_issues]
    assert [step.id for step in workflow.steps] == [
        "identity",
        "advancement",
        "notes",
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        draft_root = temp / "drafts"
        character_root = temp / "characters"

        draft = create_draft(
            "test-user",
            pack.manifest.id,
            pack.manifest.version,
            schema.schema_version,
            initial_data=schema.default_data(),
            draft_root=draft_root,
        )
        draft.data["name"] = "Wizard Test"
        draft.data["background"] = "traveler"
        draft.current_step = 1
        save_draft(draft, draft_root=draft_root)

        resumed = load_draft(
            "test-user",
            draft.draft_id,
            draft_root=draft_root,
        )
        assert resumed.current_step == 1
        assert resumed.data["name"] == "Wizard Test"
        assert len(list_drafts("test-user", draft_root=draft_root)) == 1

        resumed.data["level"] = 4
        resumed.data["skills"] = ["athletics", "stealth"]
        resumed.data["active"] = True
        resumed.data["notes"] = "Created through draft lifecycle test."

        record = create_character(
            "test-user",
            pack.manifest.id,
            initial_data=resumed.data,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert record.data["name"] == "Wizard Test"
        assert record.data["background"] == "traveler"
        assert record.data["skills"] == ["athletics", "stealth"]
        assert record.data["power_score"] == 8

        delete_draft(
            "test-user",
            resumed.draft_id,
            draft_root=draft_root,
        )
        assert list_drafts("test-user", draft_root=draft_root) == []

        http_tested = _optional_http_test(pack, schema, temp)

    env = Environment(loader=FileSystemLoader(PROJECT_ROOT / "app" / "templates"))
    env.get_template("characters/create.html")
    env.get_template("characters/index.html")
    home_template = (PROJECT_ROOT / "app" / "templates" / "home.html").read_text()
    assert 'href="/characters"' in home_template

    create_template = (
        PROJECT_ROOT / "app" / "templates" / "characters" / "create.html"
    ).read_text()
    assert "field.type == \"multi_reference\"" in create_template
    assert "/evaluate" in create_template

    paths = {
        getattr(route_item, "path", None)
        for route_item in character_web.router.routes
    }
    expected = {
        "/characters/create/start",
        "/characters/create/{draft_id}",
        "/characters/create/{draft_id}/evaluate",
        "/characters/create/{draft_id}/step",
        "/characters/create/{draft_id}/delete",
    }
    assert expected <= paths, sorted(expected - paths)

    print("PASS: creation UI and draft lifecycle smoke test")
    print("  persistent/resumable drafts: OK")
    print("  final authoritative character creation: OK")
    print("  creation templates/routes: OK")
    print("  live evaluation wiring: OK")
    print("  multi-reference choices: OK")
    print("  home Character Manager link: OK")
    if not http_tested:
        print("  simulated HTTP wizard: SKIPPED (optional test dependency only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
