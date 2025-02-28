import { expect, test } from "bun:test";

import { joinStrings } from "./join.ts";

test("joinStrings concatenates with comma and space", () => {
  expect(joinStrings("One", "Two")).toBe("One, Two");
});
