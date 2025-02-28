import { assertEquals } from "jsr:@std/assert";

import { joinStrings } from "./join.ts";

Deno.test("joinStrings concatenates with comma and space", () => {
  assertEquals(joinStrings("One", "Two"), "One, Two");
});