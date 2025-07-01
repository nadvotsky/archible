#include <vector>
#include <string_view>
#include <fmt/base.h>

#include "util/util.h"

auto main() -> int {
  fmt::println("{}", Util::JoinStrings(std::vector<std::string_view>{"Hello", "World"}));
}
