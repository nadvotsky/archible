#include <vector>
#include <string_view>
#include <ranges>

#include "util.h"

namespace {
    const std::string_view kJoinStringsSep = ", ";
}

std::string Util::JoinStrings(const std::vector<std::string_view>& strings) {
  return std::ranges::to<std::string>(strings | std::views::join_with(kJoinStringsSep));
}
