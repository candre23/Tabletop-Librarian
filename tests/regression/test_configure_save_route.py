#!/usr/bin/env python3
from pathlib import Path
import asyncio
import sys
import tempfile
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.requests import Request

from app.characters.storage import create_character, load_character
import app.characters.web as web


def make_request(body: bytes) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [
                (
                    b"content-type",
                    b"application/x-www-form-urlencoded",
                )
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "scheme": "http",
            "root_path": "",
        },
        receive,
    )


async def exercise_configure_save() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"
        pack_root = ROOT / "tests/fixtures/system_packs"

        record = create_character(
            "configure-test",
            "ttl_test_minimal",
            initial_data={
                "name": "Old Name",
                "level": 1,
            },
            character_root=character_root,
            pack_root=pack_root,
        )

        old_character_root = web.CHARACTER_ROOT
        old_pack_root = web.PACK_ROOT
        old_identity = web._identity_from_request

        web.CHARACTER_ROOT = character_root
        web.PACK_ROOT = pack_root
        web._identity_from_request = lambda request: ("configure-test", "GM")

        try:
            body = urlencode(
                {
                    "mode": "configure",
                    "field__name": "Sir New Name",
                    "field__level": "3",
                    "field__active": "on",
                    "field__inventory": "[]",
                    "field__notes": "",
                }
            ).encode("utf-8")

            response = await web.character_save(
                make_request(body),
                record.character_id,
            )
            assert response.status_code == 303

            reopened = load_character(
                "configure-test",
                record.character_id,
                character_root=character_root,
                pack_root=pack_root,
            )
            assert reopened.data["name"] == "Sir New Name"
            assert reopened.data["level"] == 3

        finally:
            web.CHARACTER_ROOT = old_character_root
            web.PACK_ROOT = old_pack_root
            web._identity_from_request = old_identity


def main() -> int:
    template = (
        ROOT / "app/templates/characters/edit.html"
    ).read_text()

    form_start = template.index('id="ttl-character-form"')
    form_end = template.index("</form>", form_start)
    main_form_body = template[form_start:form_end]

    assert "<form" not in main_form_body
    assert 'form="ttl-advancement-form-{{ action.id }}"' in template
    assert 'id="ttl-advancement-form-{{ action.id }}"' in template

    asyncio.run(exercise_configure_save())

    print("PASS: configure-save route regression test")
    print("  no nested forms in character editor: OK")
    print("  advancement actions use external forms: OK")
    print("  configure name save through real route: OK")
    print("  configure level save through real route: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
