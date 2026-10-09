import assert from "node:assert/strict";
import test from "node:test";
import { activeSection, stickyOffsetFrom } from "../../../app/features/shared/sectionNav.ts";
import { LocalizedError, messageOf, showMessage } from "../../../app/features/shared/localizedMessage.ts";
import { translator } from "../../../app/i18n/index.ts";

// P1 W4b (spec 6.4, R3-22): the sticky in-page navigation of long pages, and
// messages kept as dictionary keys until shown.
test("spec 6.4: the sticky page bar sits under what is stuck to the top, never under the side rail", () => {
  const topbar = { position: "sticky", top: 0, bottom: 92, width: 1040 };
  const rail = { position: "sticky", top: 0, bottom: 800, width: 240 };
  assert.equal(stickyOffsetFrom([topbar, rail], 1280), 92);
  assert.equal(stickyOffsetFrom([{ ...topbar, position: "static" }, { position: "sticky", top: 0, bottom: 56, width: 375 }], 375), 56, "narrow: the menu bar");
  assert.equal(stickyOffsetFrom([{ ...topbar, top: -100, bottom: -8 }], 1280), 0, "a bar scrolled away does not count");
  assert.equal(stickyOffsetFrom([{ ...topbar, top: 300, bottom: 392 }], 1280), 0, "nor one further down the page");
  assert.equal(activeSection([{ id: "a", top: -500 }, { id: "b", top: 40 }, { id: "c", top: 900 }], 120), "b");
  assert.equal(activeSection([{ id: "a", top: 300 }, { id: "b", top: 900 }], 120), "a", "before any section passes the line the first is current");
});

test("a message stays a key until shown, so it follows the interface language; backend text is kept as sent", () => {
  const keyed = messageOf(new LocalizedError("ui.close"), "ui.cancel");
  assert.deepEqual(keyed, { key: "ui.close", values: undefined });
  assert.equal(showMessage(translator("en"), keyed), "Close");
  assert.equal(showMessage(translator("zh"), keyed), "关闭");
  assert.deepEqual(messageOf(new Error("GF_X: backend said no"), "ui.cancel"), { text: "GF_X: backend said no" });
  assert.deepEqual(messageOf("not an error", "ui.cancel"), { key: "ui.cancel", values: undefined });
  assert.equal(showMessage(translator("en"), null), "");
});
