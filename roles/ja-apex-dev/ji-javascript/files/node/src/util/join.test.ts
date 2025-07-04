import { expect, test } from "vitest";

import { joinStrings } from "./join.js";

test("joinStrings concatenates with comma and space", () => {
  expect(joinStrings("One", "Two")).toBe("One, Two");
});
