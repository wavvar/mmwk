# MMWK Board Component

`mmwk_board` is the source-published board support component for the public MMWK
SDK. It provides board IO definitions and board-specific helpers used by
examples that link against the aggregated `mmwk_sdk` binary component.

The public SDK publishes this component as source so applications can select the
target board at build time:

```text
components/mmwk_board/
  CMakeLists.txt
  Kconfig.projbuild
  include/
  io_def/
  src/
```

Keep `CONFIG_COMPILER_OPTIMIZATION_SIZE=y` in SDK projects. The prebuilt
`mmwk_sdk` libraries are built with size optimization.
