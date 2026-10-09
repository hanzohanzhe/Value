// P1 W4b (spec 3): a message kept as a dictionary key until it is shown, so an
// error stored in state follows a later language switch, and effects that set
// it do not depend on the translate function. Text from the backend (error
// messages) stays as sent: spec 3 does not translate it.
import type { MessageKey, MessageValues, Translate } from "../../i18n/index.ts";

export type LocalizedMessage = { key: MessageKey; values?: MessageValues } | { text: string };

/** An Error whose message is a dictionary key (thrown inside effects and handlers). */
export class LocalizedError extends Error {
  readonly key: MessageKey;
  readonly values?: MessageValues;
  constructor(key: MessageKey, values?: MessageValues) {
    super(key);
    this.name = "LocalizedError";
    this.key = key;
    this.values = values;
  }
}

/** A caught value as a message: a LocalizedError keeps its key, any other Error its text, anything else the fallback key. */
export function messageOf(reason: unknown, fallback: MessageKey, values?: MessageValues): LocalizedMessage {
  if (reason instanceof LocalizedError) return { key: reason.key, values: reason.values };
  if (reason instanceof Error && reason.message) return { text: reason.message };
  return { key: fallback, values };
}

export function showMessage(t: Translate, message: LocalizedMessage | null | undefined): string {
  if (!message) return "";
  return "text" in message ? message.text : t(message.key, message.values);
}
