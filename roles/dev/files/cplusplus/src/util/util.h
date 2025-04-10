#ifndef UTIL_H
#define UTIL_H

#include <vector>
#include <string>
#include <string_view>

class Util {
 public:
  static auto JoinStrings(const std::vector<std::string_view>& strings) -> std::string;
};

#endif
