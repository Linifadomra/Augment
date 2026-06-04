#pragma once

#if defined(_MSC_VER)
  #define AUGTEST_EXPORT __declspec(dllexport)
  #define AUGMENT_NOINLINE __declspec(noinline)
  #define AUGMENT_FORCEINLINE __forceinline
  #define AUGMENT_EXPORT
#else
  #define AUGTEST_EXPORT
  #define AUGMENT_NOINLINE __attribute__((noinline))
  #define AUGMENT_FORCEINLINE __attribute__((always_inline))
  #define AUGMENT_EXPORT __attribute__((visibility("default")))
#endif