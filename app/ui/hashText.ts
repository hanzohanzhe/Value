export const HASH_PREFIX_LENGTH = 12;

/** The first 12 characters; a leading "sha256:" style prefix is kept. */
export function shortHash(value: string, length = HASH_PREFIX_LENGTH): string {
  const match = /^([a-z0-9]+:)(.*)$/i.exec(value);
  const [prefix, body] = match ? [match[1], match[2]] : ["", value];
  return body.length > length ? `${prefix}${body.slice(0, length)}…` : value;
}
