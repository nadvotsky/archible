# cplusplus-cmake

## Recipes

**Presets**:

- default
- default-release-static
- default-release-dynamic
- clang
- clang-release-static
- clang-release-dynamic

**Initialize**:

- `cmake [--fresh] --preset @PRESET`
- `cmake [--fresh] -B build -DCMAKE_TOOLCHAIN_FILE=config/toolchains/clang/@PRESET`

**All-In-One**:

- `cmake --workflow --preset @PRESET`

**Build**:

- `cmake --build --preset @PRESET`
- `cmake --build build`
- `ninja -C build build.ninja`

**Clean**:

- `cmake --build --clean-first --preset @PRESET`
- `cmake --build build --target clean`
- `ninja -C build build.ninja clean`

**Test**:

- `ctest --preset @PRESET`
- `(cd build; ctest [-j 2] [-R 'TestName*'])`
- `ninja -C build build.ninja test`
- `./build/cmake-template-test`

**Lint**:

- `just lint`

**Format**:

- `just fmt`

**Package**:

- `cpack --preset @PRESET`
- `(cd build; cpack --config CPackConfig.cmake -G TGZ)`
- `ninja -C build build.ninja package`

## Links

### CMake

- Documentation: https://cmake.org/cmake/help/latest/index.html
- cmake-variables: https://cmake.org/cmake/help/latest/manual/cmake-variables.7.html
- cmake-presets: https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html
- BUILD_SHARED_LIB: https://cmake.org/cmake/help/latest/variable/BUILD_SHARED_LIBS.html
- INSTALL_RPATH: https://cmake.org/cmake/help/latest/prop_tgt/INSTALL_RPATH.html
- Install with archives: https://stackoverflow.com/a/55601955
- fPIC: https://cmake.org/cmake/help/latest/prop_tgt/POSITION_INDEPENDENT_CODE.html
- Archive generator: https://cmake.org/cmake/help/latest/cpack_gen/archive.html
- clang-tidy: https://discourse.cmake.org/t/how-to-prevent-clang-tidy-to-check-sources-added-with-fetchcontents/

### clang

- Reference: https://clang.llvm.org/docs/ClangCommandLineReference.html
- clang-format: https://clang.llvm.org/docs/ClangFormatStyleOptions.html
- clang-tidy: https://clang.llvm.org/extra/clang-tidy/checks/list.html
- run-clang-tidy: https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clang-tidy/tool/run-clang-tidy.py
- vfsoverlay: https://github.com/microsoft/clang-1/blob/master/test/VFS/Inputs/vfsoverlay.yaml

### gcc

- gcc: https://gcc.gnu.org/onlinedocs/gcc-3.2.2/gcc/Invoking-GCC.html

### GoogleTest

- GoogleTest: http://google.github.io/googletest

### Misc

- Package Managers: https://moderncppdevops.com/pkg-mngr-roundup/
