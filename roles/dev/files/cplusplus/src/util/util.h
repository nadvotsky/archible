#ifndef UTIL_H
#define UTIL_H

#include <vector>
#include <string_view>

class Util {
 public:
  static std::string JoinStrings(const std::vector<std::string_view>& strings);
};

#endif
