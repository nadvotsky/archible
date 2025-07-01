#include <gtest/gtest.h>

#include <vector>
#include <string_view>

#include "util/util.h"

TEST(UtilTest, JoinStringsConcatenatesWithCommaSeparator) {
  const auto inputs = std::vector<std::string_view>{"one", "two"};
  EXPECT_EQ(Util::JoinStrings(inputs), "one, two");
}

TEST(UtilTest, JoinStringsReturnEmptyStringForEmptyStrings) {
  EXPECT_EQ(Util::JoinStrings(std::vector<std::string_view>{}), "");
}

