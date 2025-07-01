#include <iterator>
#include <vector>
#include <string>
#include <string_view>
#include <numeric>

#include "util.h"

namespace {
  constexpr std::string kJoinStringsSep{", "};
}

auto Util::JoinStrings(const std::vector<std::string_view>& strings) -> std::string {
  if (strings.empty()) {
    return std::string{};
  }

  return std::accumulate(
    std::next(strings.begin()),
    strings.end(),
    std::string(strings.front()),
    [](const std::string& acc, const std::string_view& next) {
      return acc + kJoinStringsSep + std::string{next};
    }
  );
}
