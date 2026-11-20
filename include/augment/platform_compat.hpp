/// \file
/// internal
/// \cond

#pragma once

#if defined(_MSC_VER)
  #define AUGTEST_EXPORT __declspec(dllexport)
  #define AUGMENT_EXPORT __declspec(dllexport)
  #define AUGMENT_NOINLINE __declspec(noinline)
  #define AUGMENT_FORCEINLINE __forceinline
#else
  #define AUGTEST_EXPORT
  #define AUGMENT_EXPORT __attribute__((visibility("default")))
  #if defined(__GNUC__) && !defined(__clang__)
    #define AUGMENT_NOINLINE __attribute__((noinline, noclone))
  #else
    #define AUGMENT_NOINLINE __attribute__((noinline))
  #endif
  #define AUGMENT_FORCEINLINE __attribute__((always_inline))
#endif

/// \endcond
