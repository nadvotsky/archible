cc_library(
    name = "util",
    srcs = ["util/util.cc"],
    hdrs = ["util/util.h"],
    visibility = ["//test:__subpackages__"]
)

cc_binary(
    name = "main",
    srcs = ["main.cc"],
    deps = [
        "@fmt//:fmt",
        ":util",
    ],
)
