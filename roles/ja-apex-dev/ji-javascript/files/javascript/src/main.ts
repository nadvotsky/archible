import { joinStrings } from "./util/join.ts";

if (import.meta.main) {
  console.info(joinStrings("Hello", "World!"));
}
